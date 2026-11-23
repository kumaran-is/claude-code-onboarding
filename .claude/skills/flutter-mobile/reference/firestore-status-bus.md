# Firestore Real-Time Status Bus — Flutter Consumer Pattern

A pattern for consuming backend-owned Firestore collections in real-time from Flutter.
Applies when: the backend writes canonical state (orders, tasks, notifications) to a
Firestore subcollection and Flutter needs to display live updates without polling.

**Core boundary:** Flutter READS. The backend WRITES. Never swap.

---

## Quick Rules

- **ALWAYS** use `.snapshots()` for live status — never `.get()`
- **NEVER** write to Firestore from Flutter — the backend owns all writes
- **ALWAYS** wire through a Riverpod stream provider — never a raw `StreamBuilder`
- Firestore failures are **non-fatal but visible** — keep the last known value and mark it stale ("live updates paused"); never a silent fallback that looks live

---

## Why Firestore (Not Polling or WebSocket)

Pub/Sub has no mobile SDK — it's a server-to-server bus. Polling adds latency and drains
battery. Firestore's `.snapshots()` maintains a persistent WebSocket connection, delivers
sub-second updates without polling, and handles offline reconnection automatically. The
backend writes to PostgreSQL (canonical state), then fires a non-blocking async task to
write the status event to Firestore — Flutter receives the update within milliseconds.

---

## Riverpod Stream Provider Pattern

cloud_firestore 7.2.0, flutter_riverpod 3.5.0, riverpod_generator 4.0.10, freezed 4.0.3, material_ui 1.11.1. Compiled, generated and tested on Flutter 3.50.1 / Dart 3.14.0 with `fake_cloud_firestore` 4.5.0 (latest event streams and updates live). The security rules behind it were checked on the Firestore emulator with a `demo-*` project: owner read/write 200, signed-out and other-user reads 403; a permissive rule (`if true`) fails the check.

```dart
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'status_providers.freezed.dart';
part 'status_providers.g.dart';

@freezed
abstract class StatusEvent with _$StatusEvent { // freezed 3+: abstract (or sealed)
  const factory StatusEvent({
    required String status,
    required String previousStatus,
    String? actorId,
    required String actorType,
    required DateTime timestamp,
  }) = _StatusEvent;

  /// Backend writes a Firestore Timestamp. A malformed document throws a
  /// FormatException so the stream surfaces an error, never a fake value.
  factory StatusEvent.fromFirestore(Map<String, dynamic> data) {
    final ts = data['timestamp'];
    if (ts is! Timestamp) {
      throw const FormatException('status_event.timestamp is not a Timestamp');
    }
    return StatusEvent(
      status: data['status'] as String,
      previousStatus: data['previous_status'] as String,
      actorId: data['actor_id'] as String?,
      actorType: data['actor_type'] as String,
      timestamp: ts.toDate().toUtc(), // toDate() is local time
    );
  }
}

/// Override in tests with FakeFirebaseFirestore.
@Riverpod(keepAlive: true)
FirebaseFirestore firestore(Ref ref) => FirebaseFirestore.instance;

CollectionReference<Map<String, dynamic>> _events(Ref ref, String entityId) =>
    ref
        .watch(firestoreProvider)
        .collection('your_collection')
        .doc(entityId)
        .collection('status_events');

/// Riverpod 3 retries every failed provider by default. Retry only what can
/// heal: a permission denial or a malformed document will not, and must
/// surface as AsyncError at once.
Duration? statusRetry(int retryCount, Object error) {
  if (retryCount >= 5) return null;
  return switch (error) {
    FirebaseException(code: 'unavailable' || 'deadline-exceeded') => Duration(
      milliseconds: 500 * (1 << retryCount),
    ),
    _ => null,
  };
}

/// Latest status. The backend writes; the app only listens.
@Riverpod(retry: statusRetry)
Stream<StatusEvent?> entityStatus(Ref ref, String entityId) =>
    _events(ref, entityId)
        .orderBy('timestamp', descending: true)
        .limit(1)
        .snapshots()
        .map(
          (s) => s.docs.isEmpty
              ? null
              : StatusEvent.fromFirestore(s.docs.first.data()),
        );
```

Riverpod 3 passes a plain `Ref` (the generated `EntityStatusStreamRef`-style types are gone), and `@riverpod` providers are auto-dispose: the listener detaches when no widget watches it.

---

## Consuming the Stream in a Widget

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logging/logging.dart';
import 'package:material_ui/material_ui.dart';

final _log = Logger('StatusBadge');

class StatusBadge extends ConsumerWidget {
  const StatusBadge({required this.entityId, super.key});

  final String entityId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(entityStatusProvider(entityId));
    return switch (status) {
      AsyncData(value: null) => const SizedBox.shrink(),
      AsyncData(:final value?) => Chip(label: Text(value.status)),
      // Live updates stopped: keep the last value if we have one, but say so.
      AsyncError(:final error) => _staleOrUnavailable(status.value, error),
      _ => const SizedBox.shrink(),
    };
  }

  Widget _staleOrUnavailable(StatusEvent? last, Object error) {
    _log.warning('status stream failed (${error.runtimeType})');
    return Chip(
      avatar: const Icon(
        Icons.sync_problem,
        semanticLabel: 'Live updates paused',
      ),
      label: Text(last?.status ?? 'Status unavailable'),
    );
  }
}
```

```dart
// ❌ WRONG — raw StreamBuilder bypasses Riverpod wiring, retry policy and test overrides
StreamBuilder<QuerySnapshot>(
  stream: FirebaseFirestore.instance
      .collection('your_collection')
      .doc(entityId)
      .collection('status_events')
      .snapshots(),
  builder: (_, snap) { ... },
)

// ❌ WRONG — .get() is a one-shot fetch, not real-time
final snap = await FirebaseFirestore.instance
    .collection('your_collection')
    .doc(entityId)
    .collection('status_events')
    .get(); // misses all future updates
```

---

## Status Timeline / History Feed

```dart
/// Chronological history for a timeline screen.
@Riverpod(retry: statusRetry)
Stream<List<StatusEvent>> entityStatusHistory(Ref ref, String entityId) =>
    _events(ref, entityId)
        .orderBy('timestamp')
        .snapshots()
        .map(
          (s) => [for (final d in s.docs) StatusEvent.fromFirestore(d.data())],
        );
```

---

## Tests

```dart
// Override the Firestore provider with a fake; no network, no emulator.
final db = FakeFirebaseFirestore();
final container = ProviderContainer(
  overrides: [firestoreProvider.overrideWithValue(db)],
);
addTearDown(container.dispose);
```

For security rules, run the Firestore emulator with a `demo-*` project id (no real project, no credentials): `npx -y firebase-tools@15.37.0 emulators:exec --only firestore --project demo-yourapp ./rules_check.sh`, where the script asserts owner 200 and signed-out/other-user 403, and plant a permissive rule once to prove the check can fail.

---

## Hard Rules

| Rule | Applies to |
|---|---|
| **NEVER** write to Firestore from Flutter | All Flutter screens and providers |
| **NEVER** use `.get()` for live status display — use `.snapshots()` | All status widgets |
| **NEVER** use a raw `StreamBuilder` for status events — wire through Riverpod | All status widgets |
| **NEVER** hide a Firestore stream failure — log the error type, keep the last value and mark it stale | Error handlers |
| **ALWAYS** order by `timestamp descending, limit 1` for current status badge | Badge widgets |
| **ALWAYS** order by `timestamp ascending` for history/timeline screens | Timeline widgets |

---

## Adding Real-Time Status to a New Screen — Checklist

```
□ Define a @freezed model for the status event shape
□ Create a @Riverpod(retry: ...) Stream<StatusEvent?> provider using .snapshots(); retry only transient codes
□ Parse Timestamp fields as Timestamp and convert with .toDate().toUtc(); a malformed document is an error, never a default
□ Consume with a switch over AsyncValue; AsyncError keeps the last value and marks it stale
□ Security rules tested on the emulator (demo-* project) with a permissive-rule negative
□ No .get() calls for live status anywhere in the file
□ No Firestore writes (set, update, add) anywhere in the Flutter code
□ grep -rn "\.set(\|\.update(\|\.add(" lib/ | grep firestore → must return 0
```

# Firestore Real-Time Status Bus — Flutter Consumer Pattern

A pattern for consuming backend-owned Firestore collections in real-time from Flutter.
Applies when: the backend writes canonical state (orders, tasks, notifications) to a
Firestore subcollection and Flutter needs to display live updates without polling.

**Core boundary:** Flutter READS. The backend WRITES. Never swap.

---

## Quick Rules

- **ALWAYS** use `.snapshots()` for live status — never `.get()`
- **NEVER** write to Firestore from Flutter — the backend owns all writes
- **ALWAYS** wire through a Riverpod `StreamNotifier` — never a raw `StreamBuilder`
- Firestore failures are **non-fatal** — show last known state, not an error widget

---

## Why Firestore (Not Polling or WebSocket)

Pub/Sub has no mobile SDK — it's a server-to-server bus. Polling adds latency and drains
battery. Firestore's `.snapshots()` maintains a persistent WebSocket connection, delivers
sub-second updates without polling, and handles offline reconnection automatically. The
backend writes to PostgreSQL (canonical state), then fires a non-blocking async task to
write the status event to Firestore — Flutter receives the update within milliseconds.

---

## Riverpod StreamNotifier Pattern

```dart
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'status_provider.freezed.dart';
part 'status_provider.g.dart';

@freezed
class StatusEvent with _$StatusEvent {
  const factory StatusEvent({
    required String status,
    required String previousStatus,
    String? actorId,
    required String actorType,
    required DateTime timestamp,
  }) = _StatusEvent;
}

// Stream the latest status event for a given entity.
// The backend writes; Flutter reads via .snapshots() — never .get().
@riverpod
Stream<StatusEvent?> entityStatusStream(
  EntityStatusStreamRef ref,
  String entityId,
) {
  return FirebaseFirestore.instance
      .collection('your_collection')
      .doc(entityId)
      .collection('status_events')
      .orderBy('timestamp', descending: true)
      .limit(1)
      .snapshots()
      .map((snapshot) {
    if (snapshot.docs.isEmpty) return null;
    final data = snapshot.docs.first.data();
    return StatusEvent(
      status: data['status'] as String,
      previousStatus: data['previous_status'] as String,
      actorId: data['actor_id'] as String?,
      actorType: data['actor_type'] as String,
      timestamp: DateTime.parse(data['timestamp'] as String),
    );
  });
}
```

---

## Consuming the Stream in a Widget

```dart
// ✅ CORRECT — ConsumerWidget watching the stream provider
class StatusBadge extends ConsumerWidget {
  const StatusBadge({required this.entityId, super.key});

  final String entityId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(entityStatusStreamProvider(entityId));

    return statusAsync.when(
      data: (event) {
        if (event == null) return const SizedBox.shrink();
        return _StatusChip(status: event.status);
      },
      loading: () => const SizedBox.shrink(), // or skeleton widget
      error: (e, _) {
        // Firestore failure is non-fatal — canonical state is in the database.
        // A read failure means the UI misses a live update, not that data is lost.
        // Log for observability, never surface an error widget to the user.
        debugPrint('[firestore_status_bus] stream error for $entityId: $e');
        return const _StatusChip(status: 'Unknown'); // neutral fallback
      },
    );
  }
}

// ❌ WRONG — raw StreamBuilder bypasses Riverpod wiring
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

For screens that show the full status history (audit trail, event log):

```dart
@riverpod
Stream<List<StatusEvent>> entityStatusHistory(
  EntityStatusHistoryRef ref,
  String entityId,
) {
  return FirebaseFirestore.instance
      .collection('your_collection')
      .doc(entityId)
      .collection('status_events')
      .orderBy('timestamp', descending: false) // chronological for timeline
      .snapshots()
      .map((snapshot) => snapshot.docs.map((doc) {
            final data = doc.data();
            return StatusEvent(
              status: data['status'] as String,
              previousStatus: data['previous_status'] as String,
              actorId: data['actor_id'] as String?,
              actorType: data['actor_type'] as String,
              timestamp: DateTime.parse(data['timestamp'] as String),
            );
          }).toList());
}
```

---

## Hard Rules

| Rule | Applies to |
|---|---|
| **NEVER** write to Firestore from Flutter | All Flutter screens and providers |
| **NEVER** use `.get()` for live status display — use `.snapshots()` | All status widgets |
| **NEVER** use a raw `StreamBuilder` for status events — wire through Riverpod | All status widgets |
| **NEVER** show a Firestore error widget to the user — log and fall back neutrally | Error handlers |
| **ALWAYS** order by `timestamp descending, limit 1` for current status badge | Badge widgets |
| **ALWAYS** order by `timestamp ascending` for history/timeline screens | Timeline widgets |

---

## Adding Real-Time Status to a New Screen — Checklist

```
□ Define a @freezed model for the status event shape
□ Create a @riverpod Stream<StatusEvent?> provider using .snapshots()
□ Consume via ref.watch(...).when(data: ..., loading: ..., error: ...)
□ Error handler: log + neutral fallback, never ErrorWidget
□ No .get() calls for live status anywhere in the file
□ No Firestore writes (set, update, add) anywhere in the Flutter code
□ grep -rn "\.set(\|\.update(\|\.add(" lib/ | grep firestore → must return 0
```

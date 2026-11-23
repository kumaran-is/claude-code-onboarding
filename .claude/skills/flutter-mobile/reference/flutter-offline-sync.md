# Flutter Offline Sync Patterns

Patterns for building offline-first Flutter apps: durable local queue, classified retry, conflict resolution, and connectivity-triggered sync. Read this first for the model and the basic loop; read [flutter-offline-reliability.md](flutter-offline-reliability.md) for engine hardening (idempotency, leases, uploads, review checklist) and [flutter-offline-cache-and-reads.md](flutter-offline-cache-and-reads.md) for the read side (cache, refresh, migrations, sign-out).

**Backend agnostic and storage neutral** — the queue logic and sync manager are pure Dart. The local store and the remote data source are your choices (see "Choosing the local store").

---

## 0. Decide the tier first

| Tier | Behaviour | Examples |
|------|-----------|----------|
| **T1 read + write** | Reads from local store; writes go through the queue | create/edit a note, send a message, attach a document |
| **T2 read-only cache** | Cached reads; writes disabled or online-only | catalogue, history lists |
| **T3 online-only** | Never queued, never cached | payments, sign-in, anything needing live server validation |

T3 still needs a designed offline path: check connectivity before the request, show offline copy, send nothing. Never queue money movement. Never cache secrets or raw document bodies you do not need offline.

---

## How it works

```
User acts (offline)
   │
   ▼
ONE local transaction: write optimistic data + queue entry   ← durable before UI shows success
   │
   ▼
Drain triggers: connectivity regained · app foreground · after enqueue (if online) · safety timer
   │
   ▼
Dispatch entry ──► success: delete entry, patch local data with server result
              ├─► transport failure (no server answer): keep pending, do NOT count
              ├─► server transient (5xx/429): count, back off
              └─► permanent (4xx): mark failed, keep payload, tell the user
```

---

## 1. Queue entry model

A queue entry is a persisted state machine, not a retry counter.

```dart
enum OpStatus { pending, inFlight, blocked, failed, dead }

class QueuedOp {
  const QueuedOp({
    required this.id, // client UUID: the handle for everything
    required this.type, // e.g. 'document.create'
    required this.payload, // request body, JSON-encodable
    required this.idempotencyKey, // minted ONCE at enqueue, reused on every attempt
    required this.ownerUserId, // who enqueued it
    required this.createdAt,
    this.status = OpStatus.pending,
    this.attempts = 0, // server-answered failures only
    this.firstServerFailureAt, // starts the retry window
    this.dependsOnOpId, // chain edge: blocked while that row exists
    this.entityTempId, // client id of the entity this op creates/changes
    this.lastError,
  });

  final String id, type, idempotencyKey, ownerUserId;
  final Map<String, Object?> payload;
  final DateTime createdAt;
  final OpStatus status;
  final int attempts;
  final DateTime? firstServerFailureAt;
  final String? dependsOnOpId, entityTempId, lastError;

  /// Never takes an idempotency key: the key is fixed at enqueue.
  QueuedOp copyWith({OpStatus? status, String? lastError}) => QueuedOp(
    id: id,
    type: type,
    payload: payload,
    idempotencyKey: idempotencyKey,
    ownerUserId: ownerUserId,
    createdAt: createdAt,
    status: status ?? this.status,
    attempts: attempts,
    firstServerFailureAt: firstServerFailureAt,
    dependsOnOpId: dependsOnOpId,
    entityTempId: entityTempId,
    lastError: lastError ?? this.lastError,
  );

  /// 5xx/429/unexpected: count it and start the retry window once.
  QueuedOp recordServerFailure(DateTime now, String error) => QueuedOp(
    id: id,
    type: type,
    payload: payload,
    idempotencyKey: idempotencyKey,
    ownerUserId: ownerUserId,
    createdAt: createdAt,
    status: status,
    attempts: attempts + 1,
    firstServerFailureAt: firstServerFailureAt ?? now,
    dependsOnOpId: dependsOnOpId,
    entityTempId: entityTempId,
    lastError: error,
  );
}
```

- **Success deletes the entry.** Never mark "done" with a sentinel such as a far-future retry date — it breaks on clock changes and leaves rows behind.
- `failed` and `dead` entries are kept with their payload until the user acts; never drop user intent silently.
- Full state-machine rules, idempotency, leases and chains: [flutter-offline-reliability.md](flutter-offline-reliability.md).

---

## 2. Store abstraction

```dart
class RemoteResult {
  const RemoteResult(this.body); // the server's answer, e.g. the created row
  final Map<String, Object?> body;
}

/// Thrown by [RemoteDataSource.dispatch]; mapped ONCE from your HTTP client's errors.
sealed class SyncFailure implements Exception {
  const SyncFailure(this.message);
  final String message;
  @override
  String toString() => '$runtimeType: $message';
}

/// No server answer (timeout, socket/DNS drop). Does not count.
final class TransportFailure extends SyncFailure {
  const TransportFailure(super.message);
}

/// 5xx/429: counted against the retry window.
final class ServerTransientFailure extends SyncFailure {
  const ServerTransientFailure(this.status, super.message);
  final int status;
}

/// 4xx validation/forbidden: never retried automatically.
final class PermanentFailure extends SyncFailure {
  const PermanentFailure(this.status, super.message);
  final int status;
}

/// 409 with the server's current row.
final class ConflictFailure extends SyncFailure {
  const ConflictFailure(this.serverVersion) : super('409 conflict');
  final Map<String, Object?> serverVersion;
}

abstract interface class QueueStore {
  /// Writes the optimistic data change and the queue entry in ONE transaction.
  Future<void> enqueueAtomically(
    Future<void> Function() writeLocalData,
    QueuedOp op,
  );
  Future<List<QueuedOp>> dispatchable(String ownerUserId);
  Future<void> update(QueuedOp op);

  /// Deletes the entry and patches local data with the server result, in ONE transaction.
  Future<void> applySuccess(QueuedOp op, RemoteResult result);

  /// Applies the entity type's conflict strategy, in ONE transaction.
  Future<void> resolveConflict(QueuedOp op, Map<String, Object?> serverVersion);
}

abstract interface class RemoteDataSource {
  /// Must send [QueuedOp.idempotencyKey] with the request.
  Future<RemoteResult> dispatch(QueuedOp op);
}
```

Implement `QueueStore` on a store that supports multi-statement transactions and conditional updates. A key-value box cannot make "data + queue entry" atomic, and cannot claim an entry atomically (needed once a background isolate can drain too).

---

## 3. Sync manager (core loop)

```dart
class SyncManager {
  SyncManager(
    this._store,
    this._remote, {
    required this._isOnlineHint, // private named parameter (Dart >= 3.12): callers pass `isOnlineHint:`
    required this._ownerUserId,
    DateTime Function()? now,
    this.retryWindow = const Duration(hours: 72),
  }) : _now = now ?? DateTime.now;

  final QueueStore _store;
  final RemoteDataSource _remote;
  final bool Function() _isOnlineHint; // a hint, not proof of reachability
  final String? Function() _ownerUserId;
  final DateTime Function() _now; // injected for retry-window tests
  final Duration retryWindow; // product decision
  bool _draining = false;

  Future<void> drain() async {
    final owner = _ownerUserId();
    if (_draining || !_isOnlineHint() || owner == null) {
      return; // never drain signed-out
    }
    _draining = true;
    try {
      for (final op in await _store.dispatchable(owner)) {
        try {
          final result = await _remote.dispatch(op);
          // delete entry + patch local data, one transaction
          await _store.applySuccess(op, result);
        } on TransportFailure {
          break; // no server answer: leave pending, attempts unchanged, retry on next trigger
        } on ConflictFailure catch (e) {
          // strategy per entity type
          await _store.resolveConflict(op, e.serverVersion);
        } on PermanentFailure catch (e) {
          await _store.update(
            op.copyWith(status: OpStatus.failed, lastError: '$e'),
          );
        } on Object catch (e) {
          // 5xx/429/unexpected
          final counted = op.recordServerFailure(_now(), '$e');
          final exhausted =
              _now().difference(counted.firstServerFailureAt!) >= retryWindow;
          await _store.update(
            exhausted ? counted.copyWith(status: OpStatus.failed) : counted,
          );
        }
      }
    } finally {
      _draining = false;
    }
  }
}
```

`copyWith` never takes a key, so no code path can regenerate it; `recordServerFailure` sets `firstServerFailureAt` once and increments `attempts`; an entry whose retry window is exhausted becomes `failed` and keeps its payload. Failure classes come from ONE mapping function around your HTTP client (Dio version in the reliability reference §4). Inject `now` in tests.

Triggers: connectivity regained, app foreground, right after enqueue when online, and a periodic timer as a safety net only.

---

## 4. Enqueue from the repository

```dart
Future<String> createDocument(DocumentDraft draft, String ownerUserId) async {
  final localId = _uuid.v4(); // const _uuid = Uuid(); (package:uuid)
  await _store.enqueueAtomically(
    // user sees it immediately
    () => _localDocuments.insertOptimistic(localId, draft),
    QueuedOp(
      id: _uuid.v4(),
      type: 'document.create',
      payload: {'localId': localId, ...draft.toJson()},
      idempotencyKey: _uuid.v4(), // generated once, here
      ownerUserId: ownerUserId,
      entityTempId: localId,
      createdAt: DateTime.now(),
    ),
  );
  return localId;
}
```

```dart
// WRONG — two separate writes; a crash between them loses the sync or leaves an orphan
await _localDocuments.insert(draft);
await _queue.add(op);
```

Wire the manager as one keep-alive instance (e.g. a Riverpod `keepAlive` provider) and feed `isOnlineHint` from one connectivity provider.

---

## Choosing the local store

| Option | Fit for the queue |
|--------|-------------------|
| SQLite via Drift (default) | Good: transactions, conditional updates, typed migrations, optional encryption |
| Object stores (Isar community fork, Realm, ObjectBox) | Works if you use their transaction API; check each package's maintenance and migration story |
| Key-value boxes (Hive CE, shared_preferences) | OK for small caches and settings; weak for the queue: no multi-row transaction or conditional claim |

The original `hive` (last release 2022) and `isar` 3.1.0+1 (2023) are stale; prefer the maintained forks `hive_ce` and `isar_community`.

### Drift on Flutter 3.50 (verified set)

Resolved together on Flutter 3.50.1 / Dart 3.14.0 (pub get, codegen, analyze, tests, debug apk and iOS simulator build all exit 0):

```yaml
environment:
  sdk: ^3.14.0

dependencies:
  drift: 2.35.4
  drift_flutter: 0.3.1        # driftDatabase(): documents dir + background isolate
  sqlite3: 3.9.2              # direct dependency so the hook user-define below applies to it
  connectivity_plus: 7.3.2
  workmanager: 0.10.10        # optional: background drain bonus only
  uuid: 4.6.0
  flutter_secure_storage: 11.2.0
  path_provider: 2.1.6

dev_dependencies:
  drift_dev: 2.35.3
  build_runner: 2.17.1

# Encrypted builds only (see "Encryption at rest").
hooks:
  user_defines:
    sqlite3:
      source: sqlite3mc
```

**`sqlite3_flutter_libs` and `sqlcipher_flutter_libs` are end-of-life.** Since `sqlite3` 3.0.0 the native library ships through Dart build hooks: on `flutter build`/`flutter test` the `sqlite3` hook downloads a prebuilt binary for the target from the package's GitHub release and checks it against a sha256 pinned in the published package. `drift` moved to `sqlite3` 3.x in 2.32.0.

Migrating from a 2.x setup:

1. Remove `sqlite3_flutter_libs`, `sqlcipher_flutter_libs` and `sqlite3_native_assets` from `pubspec.yaml` (`drift_flutter` 0.3.1 still pulls `sqlite3_flutter_libs 0.6.0+eol` transitively: that version is an empty stub and needs no action).
2. Delete any `open.overrideFor(...)`/`DynamicLibrary` loading code: the library is chosen only through `hooks.user_defines.sqlite3` (`source: sqlite3` default, `sqlite3mc`, `sqlcipher`, `system`, `process`, `executable`, or `source` with your own `sqlite3.c`).
3. Air-gapped CI cannot reach GitHub releases: set `url_pattern` in the same user-defines block to an internal mirror.
4. An existing **SQLCipher-encrypted** file opened with SQLite3MultipleCiphers needs extra compatibility pragmas (drift 2.32.0 changelog); test the upgrade on a copy of a real v2 file before shipping, or keep `source: sqlcipher`.

### Encryption at rest

Choose `source: sqlite3mc` (SQLite3MultipleCiphers; default cipher reported on device: `chacha20`). `sqlcipher` is also bundled but links OpenSSL on Android and may lag the SQLite version; both have their own licences (check them).

```dart
import 'dart:math';

import 'package:drift_flutter/drift_flutter.dart';
import 'package:sqlite3/common.dart';

/// Never fall back to plaintext.
final class EncryptionUnavailableException implements Exception {
  const EncryptionUnavailableException();
}

final _hexKey = RegExp(r'^[0-9a-f]{64}$');
final _safeUserId = RegExp(r'^[A-Za-z0-9_-]{1,128}$');

/// 256-bit random key as hex. Store it in secure storage only; never log it.
String generateDatabaseKey() {
  final random = Random.secure();
  return List.generate(
    32,
    (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
}

/// Runs on the raw connection before drift touches it. Fails closed.
void applyCipherKey(CommonDatabase db, String hexKey) {
  if (!_hexKey.hasMatch(hexKey)) {
    throw ArgumentError('database key must be 64 lowercase hex characters');
  }
  // Plain SQLite ignores unknown pragmas and returns no row.
  if (db.select('PRAGMA cipher').isEmpty) {
    throw const EncryptionUnavailableException();
  }
  db.execute("PRAGMA hexkey = '$hexKey'"); // safe: validated hex only
  // Wrong key or a plaintext file => SqliteException(26, 'file is not a database').
  db.select('SELECT count(*) FROM sqlite_master');
  db.execute('PRAGMA busy_timeout = 5000');
}

/// One database file per signed-in user: user B never opens user A's file.
String databaseNameFor(String userId) {
  if (!_safeUserId.hasMatch(userId)) {
    throw ArgumentError.value(userId, 'userId', 'unsafe file name');
  }
  return 'app_$userId';
}

AppDatabase openUserDatabase({
  required String userId,
  required String hexKey,
}) => AppDatabase(
  driftDatabase(
    name: databaseNameFor(userId),
    native: DriftNativeOptions(setup: (db) => applyCipherKey(db, hexKey)),
  ),
);
```

- The key is per user, generated on first open with `Random.secure()`, stored with `flutter_secure_storage` under a per-user slot, read-only in background isolates (never mint a key there), and deleted on real sign-out. Never derive it from credentials, never hardcode, log or send it.
- The `PRAGMA cipher` guard is what stops a build that lost the user-define from silently writing plaintext: keep it, and keep a test that asserts it.
- Tests run against the same hook-built library (`flutter test` compiles it for the host), so encryption is testable without a device: key applied, file header is not `SQLite format 3` and contains no plaintext, wrong key and no key fail, an existing plaintext file is refused, `PRAGMA integrity_check` returns `ok`. Test list: [flutter-offline-reliability.md](flutter-offline-reliability.md) §12.

### Migrations with Drift

Use step-by-step migrations and drift's schema tooling: commit a schema snapshot per version and generate the steps and test helpers.

```yaml
# build.yaml
targets:
  $default:
    builders:
      drift_dev:
        options:
          databases:
            app_db: lib/db/app_database.dart
          schema_dir: drift_schemas/
          test_dir: test/drift/
```

```dart
@override
MigrationStrategy get migration => MigrationStrategy(
  onCreate: (m) => m.createAll(),
  onUpgrade: stepByStep(
    from1To2: (m, schema) async {
      await m.addColumn(schema.notes, schema.notes.body); // new column is nullable
      await m.createIndex(schema.queueOwnerStatus);
    },
  ),
);
```

Run `dart run drift_dev make-migrations` after each schema bump: it writes the snapshot, `app_database.steps.dart` and a `SchemaVerifier` test (`test/drift/app_db/migration_test.dart`) that migrates every old version and checks rows survive. Drift's `stepByStep` refuses a downgrade with an error (drift 2.31.0).

## Rules

- **Save locally and enqueue in one transaction** — never "save, then enqueue" as two writes.
- **`enqueue()` is called by the repository**, never directly by widgets.
- **Mint the idempotency key at enqueue**; never regenerate it.
- **Classify failures** — transport errors do not burn retry budget; 4xx is permanent and surfaced.
- **Bound retries by time, not attempt count** (policy and numbers in the reliability reference); exhausted entries become `failed` and keep user data.
- **Ordering comes from dependencies**, not from "deletes first": a delete must not run before an earlier create of the same entity has completed.
- **One `SyncManager` per process**; a background isolate must claim entries atomically (lease).
- **Do not enqueue the same `localId` + operation twice** — look for an existing pending entry first.

---

## 5. Pointers

- Failure classification, backoff, lease, upload staging, test strategy, review checklist → [flutter-offline-reliability.md](flutter-offline-reliability.md)
- Queued-write read model, temp-id aliasing, refresh/reconciliation, migrations, sign-out → [flutter-offline-cache-and-reads.md](flutter-offline-cache-and-reads.md)
- Timeouts, circuit breaker → [flutter-network-resilience.md](flutter-network-resilience.md)

---

## 6. Conflict Resolution

When the same record is modified both locally (offline) and on the server (by another device or user), the sync manager needs a strategy to resolve the conflict.

### Strategy selection

| Strategy | When to use | Tradeoff |
|----------|-------------|----------|
| **Server wins** | Server is authoritative (financial records, inventory) | Simple; local edit is silently lost |
| **Last write wins** | User-owned data (notes, preferences) | Simple; requires `updatedAt` timestamps on both sides |
| **Client wins** | Rare — only if local is always more current | Risk of overwriting legitimate server changes |
| **User prompt** | High-value data where silent loss is unacceptable (documents, schedules) | Best UX; requires UI to surface the conflict |

---

### Strategy 1 — Last Write Wins (timestamp comparison)

Attach a client-side `updatedAt` timestamp to every sync operation payload. The server rejects stale writes.

```dart
// Add to the queue entry payload when enqueuing an update
Future<void> updateEntry(JournalEntry entry, String ownerUserId) =>
    _store.enqueueAtomically(
      () => _localRepo.update(entry),
      QueuedOp(
        id: _uuid.v4(),
        type: 'entry.update',
        idempotencyKey: _uuid.v4(),
        ownerUserId: ownerUserId,
        createdAt: DateTime.now(),
        payload: {
          ...entry.toJson(),
          // ISO-8601 UTC: the server compares it with its own updatedAt
          'client_updated_at': DateTime.now().toUtc().toIso8601String(),
        },
      ),
    );
```

Server logic (pseudo-code — backend responsibility):
```
if request.client_updated_at > server_record.updated_at:
    apply update
    return 200
else:
    return 409 Conflict { "server_version": server_record }
```

The 409 reaches `SyncManager.drain()` as `ConflictFailure`, which calls `QueueStore.resolveConflict`: for last-write-wins it writes the server version and deletes the entry in ONE transaction.

---

### Strategy 2 — User Prompt (for high-value data)

Surface the conflict to the user when silent loss is unacceptable. The queue row stays `failed` (payload kept) until the user decides; the decision is applied by the store in one transaction.

```dart
final class SyncConflict {
  const SyncConflict({
    required this.opId, // the queue row kept as `failed` until the user decides
    required this.entityId,
    required this.localVersion,
    required this.serverVersion,
  });
  final String opId, entityId;
  final Map<String, Object?> localVersion, serverVersion;
}

enum ConflictResolution { keepLocal, keepServer, keepBoth }

/// Applies one decision in ONE store transaction (patch local data + re-enqueue or delete the op).
abstract interface class ConflictResolver {
  Future<void> apply(SyncConflict conflict, ConflictResolution resolution);
}

final conflictResolverProvider = Provider<ConflictResolver>(
  (ref) => throw UnimplementedError('override with the app store'),
);

class ConflictQueue extends Notifier<List<SyncConflict>> {
  @override
  List<SyncConflict> build() => const [];

  void add(SyncConflict conflict) => state = [...state, conflict];

  Future<void> resolve(String entityId, ConflictResolution resolution) async {
    final conflict = state.firstWhere((c) => c.entityId == entityId);
    await ref.read(conflictResolverProvider).apply(conflict, resolution);
    state = [
      for (final c in state)
        if (c.entityId != entityId) c,
    ];
  }
}

final conflictQueueProvider =
    NotifierProvider<ConflictQueue, List<SyncConflict>>(ConflictQueue.new);

/// Mount once per shell; the count keeps unresolved conflicts visible.
class ConflictBanner extends ConsumerWidget {
  const ConflictBanner({super.key, required this.onResolve});
  final VoidCallback onResolve; // e.g. () => context.push('/conflicts')

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(conflictQueueProvider).length;
    if (count == 0) return const SizedBox.shrink();
    return MaterialBanner(
      content: Text('$count edit conflict(s) need your attention'),
      actions: [TextButton(onPressed: onResolve, child: const Text('Resolve'))],
    );
  }
}
```

Imports: `package:flutter_riverpod/flutter_riverpod.dart` (3.5.0) and `package:material_ui/material_ui.dart` (1.11.1). `keepLocal` is a new intent: enqueue a new op with a new idempotency key based on the server version, then delete the failed op, in one transaction. `keepBoth` duplicates the record (app-specific).

---

### Integration with SyncManager

`SyncManager.drain()` above already routes `ConflictFailure` to `QueueStore.resolveConflict`, which applies the entity type's strategy:

- Strategy 1 (last write wins / server wins): write the server row and delete the entry in one transaction.
- Strategy 2 (user prompt): mark the entry `failed` (payload kept) and add a `SyncConflict` to the conflict provider.

---

### Rules

- **Choose one strategy per entity type** — mixing strategies in the same feature creates unpredictable behaviour
- **Always include `updatedAt` in sync payloads** — without it, last-write-wins is impossible to implement correctly
- **Never silently drop user edits for high-value data** (documents, schedules, financial entries) — use user prompt strategy
- **`keepBoth` is a last resort** — it creates data duplication; prefer last-write-wins or user prompt
- **Conflicts must be surfaced, not suppressed** — if using user prompt strategy, show a badge/banner count in the UI so users know action is needed
- **A rejected write is never silently rolled back** — keep it as `failed` with its payload; refreshes must not overwrite a row that still has a queued or failed entry (see [flutter-offline-cache-and-reads.md](flutter-offline-cache-and-reads.md)). Convergence of two clients is user-resolved, not automatic.
- **A write queued offline is a request, not an authorization** — for consequential or money-related decisions the server re-reads current state on replay and may reject; revalidate (GET before POST) and fail loudly rather than auto-resolve.

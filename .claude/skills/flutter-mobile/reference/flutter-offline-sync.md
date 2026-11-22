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
    required this.id,               // client UUID — the handle for everything
    required this.type,             // e.g. 'document.create'
    required this.payload,          // request body, JSON-encodable
    required this.idempotencyKey,   // minted ONCE at enqueue, reused on every attempt
    required this.ownerUserId,      // who enqueued it
    required this.createdAt,
    this.status = OpStatus.pending,
    this.attempts = 0,              // server-answered failures only (telemetry)
    this.firstServerFailureAt,      // starts the retry window
    this.dependsOnOpId,             // chain edge
    this.entityTempId,
    this.lastError,
  });

  final String id, type, idempotencyKey, ownerUserId;
  final Map<String, Object?> payload;
  final DateTime createdAt;
  final OpStatus status;
  final int attempts;
  final DateTime? firstServerFailureAt;
  final String? dependsOnOpId, entityTempId, lastError;
}
```

- **Success deletes the entry.** Never mark "done" with a sentinel such as a far-future retry date — it breaks on clock changes and leaves rows behind.
- `failed` and `dead` entries are kept with their payload until the user acts; never drop user intent silently.
- Full state-machine rules, idempotency, leases and chains: [flutter-offline-reliability.md](flutter-offline-reliability.md).

---

## 2. Store abstraction

```dart
abstract interface class QueueStore {
  /// Writes the optimistic data change and the queue entry in ONE transaction.
  Future<void> enqueueAtomically(Future<void> Function() writeLocalData, QueuedOp op);
  Future<List<QueuedOp>> dispatchable(String ownerUserId);
  Future<void> update(QueuedOp op);
  Future<void> delete(String id);

  /// Deletes the entry and patches the optimistic local data with the server result, in ONE transaction.
  Future<void> applySuccess(QueuedOp op, RemoteResult result);
}

abstract interface class RemoteDataSource {
  /// Must send [op.idempotencyKey] with the request.
  Future<RemoteResult> dispatch(QueuedOp op);
}
```

Implement `QueueStore` on a store that supports multi-statement transactions and conditional updates. A key-value box cannot make "data + queue entry" atomic, and cannot claim an entry atomically (needed once a background isolate can drain too).

---

## 3. Sync manager (core loop)

```dart
class SyncManager {
  SyncManager(this._store, this._remote, this._isOnlineHint, this._ownerUserId);
  final QueueStore _store;
  final RemoteDataSource _remote;
  final bool Function() _isOnlineHint; // a hint, not proof of reachability
  final String? Function() _ownerUserId;
  bool _draining = false;

  Future<void> drain() async {
    final owner = _ownerUserId();
    if (_draining || !_isOnlineHint() || owner == null) return; // never drain signed-out
    _draining = true;
    try {
      for (final op in await _store.dispatchable(owner)) {
        try {
          final result = await _remote.dispatch(op);
          await _store.applySuccess(op, result); // delete entry + patch local data, one transaction
        } on TransportFailure {
          break; // no server answer: leave pending, attempts unchanged, retry on next trigger
        } on PermanentFailure catch (e) {
          await _store.update(op.copyWith(status: OpStatus.failed, lastError: '$e'));
        } on Object catch (e) {
          await _store.update(op.recordServerFailure(DateTime.now(), '$e')); // 5xx/429/unexpected
        }
      }
    } finally {
      _draining = false;
    }
  }
}
```

`copyWith`/`recordServerFailure` are small helpers on the model (`copyWith` must keep `idempotencyKey`; `recordServerFailure` sets `firstServerFailureAt` once and increments `attempts`); after recording, compare `now - firstServerFailureAt` with the retry window and mark the entry `failed` when it is exceeded (reliability reference). Failure classes (`TransportFailure`, `PermanentFailure`) come from one mapping function around your HTTP client — see classification table in the reliability reference.

Triggers: connectivity regained, app foreground, right after enqueue when online, and a periodic timer as a safety net only.

---

## 4. Enqueue from the repository

```dart
Future<String> createDocument(DocumentDraft draft, String ownerUserId) async {
  final localId = newUuid();
  await _store.enqueueAtomically(
    () => _localDocuments.insertOptimistic(localId, draft), // user sees it immediately
    QueuedOp(
      id: newUuid(),
      type: 'document.create',
      payload: draft.toJson(),
      idempotencyKey: newUuid(), // generated once, here
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
| SQLite-based (Drift 2.35.4, sqflite 2.4.6, …) | Good: transactions, conditional updates, migrations |
| Object stores (Isar community fork, Realm, ObjectBox) | Works if you use their transaction API; check each package's maintenance and migration story |
| Key-value boxes (Hive CE 2.24.0, shared_preferences) | OK for small caches and settings; weak for the queue — no multi-row transaction/conditional claim |

Versions checked on pub.dev 2026-11-21; re-check before pinning. The original `hive` package last released 2022 and `isar` 3.1.0+1 in 2023 (both flagged by the community as stale; the maintained forks are `hive_ce` and `isar_community`) — prefer a maintained fork over the originals.

Pin exact versions in `pubspec.yaml` when you add dependencies (verify with `flutter pub add` / pub.dev; do not copy a caret range).

---

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
        id: newUuid(),
        type: 'entry.update',
        idempotencyKey: newUuid(),
        ownerUserId: ownerUserId,
        createdAt: DateTime.now(),
        payload: {
          ...entry.toJson(),
          // ISO-8601 — server compares against its own updatedAt
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

Handle the 409 in the dispatch loop of `SyncManager.drain()`:
```dart
on ConflictException catch (e) {
  // Last-write-wins: server data is fresher — accept it, in ONE transaction
  await _store.resolveWithServerVersion(op, e.serverVersion); // patch local data + delete entry
}
```

---

### Strategy 2 — User Prompt (for high-value data)

Surface the conflict to the user when silent loss is unacceptable.

```dart
// lib/core/sync/conflict_resolver.dart

@freezed
class SyncConflict<T> with _$SyncConflict<T> {
  const factory SyncConflict({
    required String entityId,
    required T localVersion,
    required T serverVersion,
    required DateTime localUpdatedAt,
    required DateTime serverUpdatedAt,
  }) = _SyncConflict;
}

enum ConflictResolution { keepLocal, keepServer, keepBoth }
```

```dart
// Riverpod provider — emits conflicts for the UI to present
@riverpod
class ConflictQueue extends _$ConflictQueue {
  @override
  List<SyncConflict<Map<String, dynamic>>> build() => const [];

  void add(SyncConflict<Map<String, dynamic>> conflict) =>
      state = [...state, conflict];

  Future<void> resolve(
    String entityId,
    ConflictResolution resolution,
  ) async {
    final conflict = state.firstWhere((c) => c.entityId == entityId);
    switch (resolution) {
      case ConflictResolution.keepLocal:
        // Force-push local version with a newer timestamp
        await ref.read(entryRepositoryProvider).enqueueForcedUpdate(
          entityId,
          {...conflict.localVersion, 'force': true},
        );
      case ConflictResolution.keepServer:
        await ref.read(localRepoProvider).update(conflict.serverVersion);
      case ConflictResolution.keepBoth:
        // App-specific — e.g. duplicate the record with a suffix
        await ref.read(localRepoProvider).create(
          {...conflict.localVersion, 'localId': '${entityId}_local_copy'},
        );
        await ref.read(localRepoProvider).update(conflict.serverVersion);
    }
    state = state.where((c) => c.entityId != entityId).toList();
  }
}
```

```dart
// Widget — show conflict banner when queue is non-empty
@riverpod
Widget conflictBanner(WidgetRef ref) {
  final conflicts = ref.watch(conflictQueueProvider);
  if (conflicts.isEmpty) return const SizedBox.shrink();

  return MaterialBanner(
    content: Text('${conflicts.length} edit conflict(s) need your attention'),
    actions: [
      TextButton(
        onPressed: () => context.push('/conflicts'),
        child: const Text('Resolve'),
      ),
    ],
  );
}
```

---

### Integration with SyncManager

Add a `ConflictException` branch next to the failure branches in `drain()`:

```dart
} on ConflictException catch (e) {
  // Strategy 1 (last-write-wins): accept server version, delete the entry
  // Strategy 2 (user prompt):      keep the entry as failed, push to the conflict provider
  await _handleConflict(op, e.serverVersion);
}
```

---

### Rules

- **Choose one strategy per entity type** — mixing strategies in the same feature creates unpredictable behaviour
- **Always include `updatedAt` in sync payloads** — without it, last-write-wins is impossible to implement correctly
- **Never silently drop user edits for high-value data** (documents, schedules, financial entries) — use user prompt strategy
- **`keepBoth` is a last resort** — it creates data duplication; prefer last-write-wins or user prompt
- **Conflicts must be surfaced, not suppressed** — if using user prompt strategy, show a badge/banner count in the UI so users know action is needed
- **A rejected write is never silently rolled back** — keep it as `failed` with its payload; refreshes must not overwrite a row that still has a queued or failed entry (see [flutter-offline-cache-and-reads.md](flutter-offline-cache-and-reads.md)). Convergence of two clients is user-resolved, not automatic.
- **A write queued offline is a request, not an authorization** — for consequential or money-related decisions the server re-reads current state on replay and may reject; revalidate (GET before POST) and fail loudly rather than auto-resolve.

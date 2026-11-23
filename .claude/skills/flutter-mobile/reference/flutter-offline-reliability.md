# Flutter Offline Reliability — Queue Engine Hardening

Read this when you build or review the write side of an offline-first app: the durable operation queue, retries, idempotency, background draining, attachment uploads, and the review checklist. The basic model and loop live in [flutter-offline-sync.md](flutter-offline-sync.md); the read side (cache, refresh, migrations, sign-out) is in [flutter-offline-cache-and-reads.md](flutter-offline-cache-and-reads.md).

The code is storage-neutral. It assumes a local store with multi-statement transactions and conditional updates (SQLite-based stores qualify; a plain key-value box does not).

---

## 1. Atomic enqueue (durable before success)

A user action is durable when the local data change and its queue entry commit in ONE transaction.

```dart
// WRONG — crash between the two awaits loses the sync, or leaves an orphan entry
await documents.insertOptimistic(draft);
await queue.enqueue(op);

// RIGHT — one unit of work
await db.transaction(() async {
  await documents.insertOptimistic(draft);
  await queue.enqueue(op);
});
```

Show success to the user only after the transaction commits.

## 2. Operation state machine

| Status | Meaning | Leaves when |
|--------|---------|-------------|
| `pending` | Ready to dispatch | claimed → `inFlight` |
| `inFlight` | Claimed by exactly one drainer (lease held) | outcome written, or lease lapses → `pending` |
| `blocked` | Waits for a dependency entry | dependency row is gone → `pending`; dependency dead → `dead` |
| `failed` | Rejected or retry window exhausted; kept with payload; user-visible | user retries (→ `pending`) or discards |
| `dead` | Can never dispatch: no handler registered, owner mismatch, dead dependency | user discards |

- **Success deletes the row.** No permanent "synced" rows; dependents detect completion by the dependency row's absence and read ids it produced from an id-mapping table.
- `failed`/`dead` are retained until the user acts. Never drop user intent silently.
- Never use a sentinel field (such as a far-future retry date) to mean "done".

## 3. Idempotency key lifecycle

- Mint a UUID **once at enqueue**, persist it in the queue row, send it on every attempt (typically an `Idempotency-Key` header or a body field the API honors).
- Never derive it from the payload; never regenerate it on retry, relaunch, or manual "Retry".
- Delivery is **at-least-once**: a crash after the server applied the request but before the local row was deleted replays the request. The server is the exactly-once backstop.
- **Test:** enqueue → fail twice → build a new engine on the same database → assert the dispatcher saw the same key three times.

What to require from the API (agree this in the contract, not in the app):

| Server behaviour | Why |
|------------------|-----|
| Same key ⇒ same effect and same response | replay safety |
| Unique constraint on the key (or a derived natural key); on conflict return the existing result | concurrent replays |
| Check "already applied" **before** state/limit checks, so a replay never returns 4xx because state moved on | a 4xx on replay becomes a permanent failure for a request that actually succeeded |
| For uploads, derive the object path from (actor, key) so a retry re-mints the same object | no duplicate objects after a lost ack |
| Unparseable key ⇒ treat as absent and log; never use the raw string as an identifier | no collision/injection vector |
| Same key, different payload ⇒ return the original result and log the mismatch | do not fail a legitimate replay |

## 4. Failure classification and bounded retry

| Class | Examples | Action |
|-------|----------|--------|
| **Transport** (no server answer) | timeout, socket drop, DNS failure, no HTTP response — including a library "unknown" error wrapping a socket exception | keep `pending`; `attempts` unchanged; retry window **not** started |
| **Server transient** | 5xx, 429 | `attempts += 1`; set `firstServerFailureAt` if null; back off |
| **Permanent** | 4xx validation / conflict / forbidden | `failed`; keep payload and optimistic data; show an actionable message |
| **Unexpected throw** in a handler | bug | count as server transient — a bug must not loop silently and must not be dropped |

With Dio 5.11.1 (failure classes from [flutter-offline-sync.md](flutter-offline-sync.md) §2; the switch is exhaustive, so a new `DioExceptionType` breaks the build instead of falling through):

```dart
/// The ONE place that turns an HTTP error into a sync failure class.
SyncFailure classifyDioError(DioException e) {
  final status = e.response?.statusCode;
  return switch (e.type) {
    DioExceptionType.badResponse when status == 409 => ConflictFailure(
      (e.response?.data as Map?)?.cast<String, Object?>() ?? const {},
    ),
    DioExceptionType.badResponse
        when status != null && (status == 429 || status >= 500) =>
      ServerTransientFailure(status, 'HTTP $status'),
    DioExceptionType.badResponse => PermanentFailure(
      status ?? 0,
      'HTTP $status',
    ),
    // No server answer: keep pending, do not count.
    DioExceptionType.connectionTimeout ||
    DioExceptionType.sendTimeout ||
    DioExceptionType.receiveTimeout ||
    DioExceptionType.connectionError ||
    DioExceptionType.cancel => TransportFailure(e.type.name),
    // A TLS/pinning failure is not the op's fault: keep it pending and alert, never mark it failed.
    DioExceptionType.badCertificate => TransportFailure('bad certificate'),
    // dio 5.10+: the server answered but decoding the body timed out. Counted; the
    // idempotency key makes the replay safe.
    DioExceptionType.transformTimeout => const ServerTransientFailure(
      0,
      'transform timeout',
    ),
    // dio wraps some socket drops as `unknown`.
    DioExceptionType.unknown
        when e.error is SocketException || e.error is HttpException =>
      TransportFailure('${e.error.runtimeType}'),
    DioExceptionType.unknown => ServerTransientFailure(
      0,
      'unexpected: ${e.error.runtimeType}',
    ),
  };
}
```

Prove the mapping with a real dropped socket (§12): a mocked `DioException` only tests the switch, not how Dio reports the drop.

**Retry window, not retry count.** Measure from the first server-answered failure (e.g. 72 hours — a product decision, make it a parameter). Transport failures never start or advance it.

```dart
if (op.firstServerFailureAt != null &&
    clock.now().difference(op.firstServerFailureAt!) >= retryWindow) {
  // exhausted → failed, KEEP the optimistic data and payload
}
```

A user "Retry" clears `firstServerFailureAt` and the lease and re-queues dependents. A fixed attempt cap (for example 10) burns out during a long offline period and silently discards work — do not use one.

**Backoff:** short ladder with jitter (for example 1, 2, 4 … 64 s plus random jitter), re-armed per drain. A periodic timer is only a safety net.

**No drain while offline.** Before every drain, retry timer fire, and chain follow-up, check the connectivity hint; offline → dispatch nothing and arm no timer; going offline cancels a pending retry timer. See [flutter-network-resilience.md](flutter-network-resilience.md) on why the hint is not proof.

**Bound every step.** The drain is single-flight: one hung request freezes every queued write. Give each client class its own timeouts — normal REST (connect/receive), signed-URL transfers (send timeout sized to payload ÷ assumed throughput, clamped to the URL's lifetime), auth-token fetch (explicit timeout; do not trust the platform SDK to bound it). A timeout maps to a **transport** result that keeps the row and any staged file.

## 5. Dependencies, ordering, ownership

- Multi-step intents are chains of operations: `upload A`, `upload B` → `document.create` (depends on both). A dependent stays `blocked`/not dispatchable while any dependency row exists.
- Link by **operation id**, never by an entity's temp id.
- The handler rewrites temp ids in its payload from the id-mapping table at drain time. Write the mapping and delete the op in ONE transaction.
- Do not rely on "deletes first" ordering: a delete sorted ahead of an earlier create of the same entity runs against nothing. Use dependency edges.
- **Owner binding:** store the signed-in user id at enqueue. The processor refuses (→ `dead` with a distinct error code) any op whose owner differs from the current user. A drain with no signed-in user **skips the pass**; it must not mark ops dead (a background isolate can start before auth restores).

## 6. Single drainer: lease and termination recovery

A foreground engine and a background-task isolate can open separate connections to one database file. Only one may dispatch a given op.

```text
claim(id, owner, until): UPDATE queue SET status='inFlight', lease_owner=?, lease_expires_at=?
                         WHERE id=? AND status='pending'          -- succeeded iff 1 row changed
heartbeat: every ~20 s while the handler runs: renew WHERE lease_owner=?   (lease TTL ~60 s)
outcome:   write only while still the lease owner; on loss stop the heartbeat, skip, record nothing
recover:   at drain start move inFlight rows with lease_expires_at < now OR NULL back to 'pending'
```

- **Do not reset every `inFlight` row at drain start** — that double-dispatches an op a live drain still holds. Reclaim only lapsed leases; a NULL lease (written before the lease columns existed) is reclaimable.
- Use a distinct owner token per drainer (`foreground:<uuid>`, `background:<uuid>`).
- Set a database busy timeout (for example 5 s) so two connections wait instead of failing with a busy error.
- The numbers (60 s / 20 s) are starting points; keep the TTL a few multiples of the heartbeat.
- Opening exactly one database instance per isolate is still required; a background isolate typically cannot receive the foreground's isolate port, so it opens its own connection — the lease is what makes that safe. Streams on the foreground connection can be briefly stale after a background drain.

## 7. Attachment (media) upload pipeline

```text
pick → validate by magic bytes (not file extension) → downscale/compress + strip EXIF/GPS
→ copy into app-private storage → INSERT staging row (id, owner, path, bytes, status)
→ ONE transaction: enqueue upload op (before its parent op) and reject if queued bytes > budget
handler: request upload URL (idempotent by key) → PUT → confirm/attach (idempotent) → delete staged file + row
```

- A parent op that depends on uploads stays blocked until every upload row is gone.
- Staged file missing ⇒ permanent failure with a distinct code. Parent not yet synced ⇒ retryable wait.
- Orphan sweep at app start: staging rows or files with no live op.
- **Direct-to-storage signed URLs:** use a plain HTTP client with **no auth interceptor** (never send your API bearer token to the storage host); send exactly the headers the server returned; never rewrite any part of a signed URL, per platform or build mode; keep emulator hostnames out of app code and fix hosts at the mint.
- Resumable/chunked upload: build only the seam until a real backend endpoint and a consumer exist.
- Delete the staged file on confirmed success; keep it on retryable failure.

## 8. Never destroy the queue on a transient error

Wiping local data on "login failed" or "role fetch failed" deletes every queued write. Rules:

- The destructive wipe is reachable only from a real sign-out (see [flutter-offline-cache-and-reads.md](flutter-offline-cache-and-reads.md) §6).
- Decide "offline" with a **typed** network check, never a message-substring match.
- When a token refresh fails transiently, reuse the last verified claims for that user instead of treating the user as signed out; forget them on real sign-out. Do not put a TTL on cached claims — it would sign users out while offline.
- A 401 for a never-authenticated request must not sign out or wipe.

## 9. Kill switches

- Each offline capability sits behind a remote-controllable flag. Precedence: remote flag > build-time default > hardcoded safe default.
- Turning a flag OFF blocks **new** enqueues only; already-queued ops still drain (the handler never reads the flag — test it).
- A flag with no production reader is not a kill switch: grep for readers.
- If the flag-off path changes the flow (for example "create must also be online when attachments are online-only"), wire both halves. Test flag-off.
- Hydrate flags from cache unconditionally; fetch remote flags only when signed in.

## 10. Background execution: foreground drain is the contract

- Foreground sync (app open, connectivity regained, after enqueue) is what you promise users. Background draining is a bonus.
- Android WorkManager periodic work has a **15-minute minimum interval** (Android docs, "define work") and runs when the system allows. With `workmanager` 0.10.10 the background drain opens its own encrypted connection (the lease in §6 makes that safe) and never mints a key:

```dart
const drainTask = 'offline-queue-drain';

/// Top-level and kept by the AOT compiler: WorkManager starts it in a new engine.
@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    final userId = inputData?['userId'];
    if (task != drainTask || userId is! String) return true;
    final key = await const DatabaseKeyStore(
      FlutterSecureStorage(),
    ).existingKeyFor(userId);
    if (key == null) return true; // signed out or never opened: nothing to drain
    final db = openUserDatabase(userId: userId, hexKey: key);
    try {
      await SyncManager(
        DriftQueueStore(db),
        buildRemoteDataSource(), // app-provided: same client + timeouts as foreground
        isOnlineHint: () => true, // WorkManager's network constraint already holds
        ownerUserId: () => userId,
      ).drain();
      return true;
    } finally {
      await db.close();
    }
  });
}

Future<void> scheduleBackgroundDrain(String userId) async {
  await Workmanager().initialize(callbackDispatcher);
  await Workmanager().registerPeriodicTask(
    'drain-$userId',
    drainTask,
    frequency: const Duration(minutes: 15), // Android minimum
    inputData: {'userId': userId},
    constraints: Constraints(networkType: NetworkType.connected),
    existingWorkPolicy: ExistingPeriodicWorkPolicy.keep,
  );
}
```

  `DatabaseKeyStore`, `openUserDatabase` and `DriftQueueStore` are the app's own (encryption section of [flutter-offline-sync.md](flutter-offline-sync.md)). On Flutter 3.50.1 `flutter build apk` succeeds but warns that `workmanager_android` still applies the Kotlin Gradle plugin and that future Flutter versions will fail such builds; track the plugin's built-in-Kotlin migration before upgrading Flutter.
- Feed the connectivity hint from `connectivity_plus` 7.3.2, which reports a list of interfaces:

```dart
/// "none" alone means offline. A hint only: a captive portal or a dead backend still looks online.
bool isOnlineHint(List<ConnectivityResult> results) =>
    results.any((r) => r != ConnectivityResult.none);

/// Drain when an interface comes back; feed the same value to SyncManager's isOnlineHint.
Stream<bool> onlineHints(Connectivity connectivity) =>
    connectivity.onConnectivityChanged.map(isOnlineHint).distinct();
```
- iOS: BGTaskScheduler only runs identifiers declared under `BGTaskSchedulerPermittedIdentifiers` in `Info.plist`, at the system's discretion. If you have not configured it, do not register a task; drain in the foreground only. (Apple docs render with JavaScript and could not be fetched here — verify with the `BGTaskScheduler` documentation before relying on details.)
- UI copy: "Will sync when you reopen the app" — never "will upload in the background".
- Web: degrade gracefully behind the same queue/stream contract (no background tasks, possibly no encryption). Wrap each native init step (database, encryption, push token, path provider) in its own `try/catch` so the load-bearing action still runs.

## 11. Dead-letter and sync-status UX

- Per-item state: **Queued / Syncing / Failed**. A queued op with many server-answered failures is **stalled**: the chip stays Queued, a banner asks for attention ("server error — still retrying"), no Retry button until it truly fails.
- A "Waiting to sync" screen lists queued/failed items with Retry, Discard, Discard all, an offline hint, and an empty state; reach it from the offline banner.
- Row titles come from the op type, with an entity reference read from the **cache**, never from free text in the payload.
- Show localized copy; never render a stored server message as user copy — branch on a flag on the op.
- A field added to the queue-item view model must join `==`/`hashCode`, or the stream de-duplicates the update away.
- Mount the offline banner **once** per shell; nested scaffolds each adding one render it twice with no error.
- Queued writes that do not change local data until the server answers still need visible queued state and must withdraw their call-to-action while queued (read model: [flutter-offline-cache-and-reads.md](flutter-offline-cache-and-reads.md) §1).

## 12. Testing the queue

- Inject a clock (`now`) for retry window, lease and backoff tests.
- Use an in-memory database for logic and an **on-disk file with two connections** for the claim race (one op, two drainers ⇒ dispatched once).
- Crash injection: insert an `inFlight` row (with and without a lease), drain, assert it is reclaimed and dispatched once.
- Transport tests use a **real closing socket** (a local server that destroys the connection), not a mocked error type — a mock proves nothing about how your HTTP library classifies a dropped connection.
- Assert: idempotency key stable across relaunch; transport failures leave `attempts` unchanged; window exhaustion → `failed` with row kept; dependency chain and dead cascade; owner mismatch → `dead`; signed-out pass skips.
- Every fix ships with a positive control: revert the fix, watch the named test fail.
- Do not pump a live database `.watch()` stream inside a widget test (it leaks a pending timer): override the stream provider with a plain stream or a `Completer`-based "loading" and use an in-memory database for one-shot actions. Override the connectivity provider; never touch the real plugin channel.
- Run tests of a shared package serially if parallel runs contend on the build lock.
- **Drift + encryption tests run on the host with the real native library** (`flutter test` runs the `sqlite3` build hook): use `NativeDatabase.memory()` for logic and `NativeDatabase.createInBackground(file, setup: ...)` with the cipher setup for file tests. Minimum set, each with a positive control:
  - CRUD in a transaction; a throwing local write rolls back the queue row too (control: drop the `transaction` wrapper ⇒ test fails).
  - Idempotency key identical across two failures and a new engine on the same file (control: rebuild the key when reading rows ⇒ fails).
  - 4xx ⇒ `failed` with payload kept; retry-window exhaustion with an injected clock ⇒ `failed`; 409 ⇒ server row applied and op deleted together; offline hint or signed-out ⇒ no dispatch.
  - Migration: the generated `SchemaVerifier` test migrates every old version and compares row data (control: delete the `addColumn` step ⇒ fails).
  - Encryption: `PRAGMA cipher` returns a row; the file header is not `SQLite format 3` and contains no plaintext; wrong key and no key fail with "file is not a database"; an existing plaintext file is refused; `PRAGMA integrity_check` is `ok`; separate file and key per user.
  - Fail closed without a cipher: in a build without the `sqlite3mc` user-define the cipher test must fail and the open must throw `EncryptionUnavailableException` (control: remove the guard ⇒ plaintext open succeeds and the test fails).
- On-device proof is Maestro on the iOS simulator / Android emulator (a screen that opens the encrypted database and shows the cipher name); host tests do not prove the mobile binary bundled the cipher build.

## 13. Offline review checklist

Use for any change touching a cache, queue, upload, sync, connectivity, or offline UI.

1. Tier declared (queued / read-only / online-only); money movement never queued; secrets and raw document bodies not cached.
2. Local change + queue entry in ONE transaction; success shown after commit.
3. Idempotency key minted once, persisted, reused on retry/restart/manual retry; stability test exists.
4. Entry carries id, type, payload, key, owner, attempts, status, last error, dependency id, temp entity id.
5. State machine implemented; success deletes the row; `failed`/`dead` retained with payload.
6. Failures classified: transport (not counted) / server transient (counted) / permanent (failed, surfaced) / unexpected (counted).
7. Retry bounded by a time window; exhaustion keeps user data; manual retry resets.
8. No drain and no timer while offline; jittered backoff; connectivity is a hint.
9. Every drain step bounded; timeout ⇒ retryable, keeps row and staged file.
10. One dispatcher per op: atomic claim, lease, heartbeat, only lapsed leases reclaimed; two-connection test.
11. Dependencies block dependents; dead cascades; temp ids remapped in the transaction that deletes the op.
12. Owner checked at dispatch; signed-out pass skips; cache bound to its account.
13. Every sign-out path runs the pending-changes guard, fails closed, logs discarded **count** only; wipe unreachable from transient errors.
14. UI → repository/provider → local store; no HTTP client or API class in UI; writes only via the queue-write service.
15. Queued writes projected into the read model; drain updates the cache without manual refresh; a failed read-back never fails the op.
16. Refresh is non-destructive; never overwrites rows with queued ops; older snapshots dropped.
17. Deletions only from complete, scoped snapshots; delta mode uses tombstones.
18. Cache schema: payload + indexed promoted columns, no enforced foreign keys, new columns nullable/defaulted, version stamp; queue tables never dropped on cache reset.
19. Migrations: schema snapshot, per-hop tests that preserve rows, and a chained-upgrade test from the oldest supported version.
20. Attachments validated, compressed, metadata-stripped, staged privately, chained before parent, budget-bounded, orphan-swept; signed URLs used verbatim with no auth header.
21. Kill switch has a real reader; OFF blocks new enqueues only; flag-off path tested.
22. Sync UI: per-item state, waiting-to-sync list, stalled state, banner mounted once, honest background copy, localized.
23. Foreground drain is the contract; background tasks configured or skipped; offline data excluded from OS backup; key in secure storage.
24. Tests: fake clock, crash-injection rows, real socket drop, positive controls; analyzer and full suite run and reported.
25. Encrypted store: `hooks.user_defines.sqlite3.source: sqlite3mc` (no `sqlite3_flutter_libs`/`sqlcipher_flutter_libs`); cipher guard fails closed; per-user key and file; key never logged, hardcoded or derived from credentials.

An optional cheap guard (advisory hook, hard-fail in CI): flag direct HTTP-client imports or API-class construction in UI-layer files, and wipe calls inside `catch` blocks. Grep cannot see a client reached through a barrel import or a provider — keep the checklist item 14 as a human review item and allow an inline `// online-only: <reason>` exemption.

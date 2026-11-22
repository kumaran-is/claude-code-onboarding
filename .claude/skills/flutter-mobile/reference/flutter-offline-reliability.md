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

```dart
FailureClass classify(Object error) => switch (error) {
  final HttpResponseError e when e.status == 429 || e.status >= 500 => FailureClass.serverTransient,
  final HttpResponseError _ => FailureClass.permanent,
  _ when isNoResponseError(error) => FailureClass.transport, // timeouts, socket/DNS drops
  _ => FailureClass.serverTransient,
};
```

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
- Android WorkManager periodic work has a **15-minute minimum interval** (Android docs, "define work"; verified 2026-11-21) and runs when the system allows. `workmanager` 0.10.10 is current on pub.dev (checked 2026-11-21).
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

An optional cheap guard (advisory hook, hard-fail in CI): flag direct HTTP-client imports or API-class construction in UI-layer files, and wipe calls inside `catch` blocks. Grep cannot see a client reached through a barrel import or a provider — keep the checklist item 14 as a human review item and allow an inline `// online-only: <reason>` exemption.

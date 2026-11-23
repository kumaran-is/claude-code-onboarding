# Flutter Offline — Cache, Reads, and Account Safety

Read this when you build or review the read side of an offline-first app: showing queued writes, temp-id handling, refresh and deletion rules, local schema and migrations, retention, backup exclusion, and sign-out with pending changes. The queue engine is in [flutter-offline-reliability.md](flutter-offline-reliability.md); the basic model is in [flutter-offline-sync.md](flutter-offline-sync.md).

---

## 1. A queued write needs a read model — and so does its drain

A write that is queued and later drained exactly once can still leave the screen lying: widget state held an optimistic copy, and neither the enqueue nor the drain updated what the screen reads.

- **While queued:** project the op (or its staging row) into what the screen renders, with its sync state. Widget `State` is not a read model — it dies on navigation. Match the op by entity **and** type, not "any op on this id".
- **On drain:** the handler returns the server's row so the cache updates in the same transaction that deletes the op; if the op changes a parent it is not keyed on, re-read the parent after success.
- **A failed read-back never fails the op.** The side effect is already on the server; retrying would repeat it. Log, return success, let the next refresh heal.
- **One predicate decides an action on every surface.** The list row's button, its sort order and the detail screen call the same function, and the set of queued ops is a `required` parameter so a surface that forgets it does not compile.
- **Non-optimistic ops** (nothing local changes until the server answers) still need visible queued state: a per-entity stream over the queue (match type + entity id, exclude `failed`/`dead`), the call-to-action withdrawn while queued, and a re-read of the entity when the op leaves the queue so there is no gap in which the button returns.
- Tests: projection (queued → visible, with state), drain updates the cache, drain with a failing read-back — each with a control that removes the projection/`cacheWrites`/re-read and fails.

## 2. A temp id is an alias, and a refused create has no row

A create returns a client-generated temp id that screens and deep links hold.

- The drain writes the server row, the `temp → server` mapping, and deletes the op in **one transaction**. A watcher must read the op flag before the mapping so it never sees "neither".
- **Every** repository keyed by a parent id resolves `temp OR server-via-mapping`, not just the entity's own repository. Deleting the mapping when deduplicating the temp row turns an open screen's stream into `null`.
- Never send a temp id to the server. A queued/refused create with no mapping ⇒ make no request.
- A refused create (optimistic row removed, op kept) is a **state**, not an absence: decide from the op before the row, keep the stream alive so it follows a resend, and never offer navigation to an entity the refusal removed.
- Bound the alias table: drop an alias once neither the server row nor the temp row is cached and no queued payload still references the temp id.
- Grep every repository the target screen watches for the id it filters on before shipping a temp-id route.

## 3. Refresh is non-destructive

```dart
Future<void> refresh() async {
  try {
    final page = await api.fetch();
    await cache.upsertSkippingQueued(page); // see rules below
  } on Object catch (e, st) {
    logger.warning('refresh failed', error: e, stackTrace: st);
    if (!await cache.hasUsableRows()) rethrow; // never-synced: surface it, do not hang on a skeleton
    // cache exists: keep rows, mark stale, no error screen
  }
}
```

- Usable cached rows stay visible through every refresh path and outcome. Never clear the cache before the network succeeds, blank the screen, or swap content for a skeleton.
- A failed background refresh over a **populated** cache is staleness, not an error screen. Over a **never-synced** collection a swallowed failure traps the screen on its loading state — there the failure must reach the UI.
- **Do not clobber an un-drained local edit:** the upsert skips rows that have ANY queued op, including `failed` and `dead` — otherwise a rejected edit silently reverts under the user.
- Drop a snapshot strictly older than the stored server version (compare at the precision the store keeps). A cancel token or generation counter on top is unnecessary.
- **A narrower refresh window is a cache eviction.** A refresh that prunes rows the server did not return for the window it was given will empty another screen that shares the collection. One collection ⇒ one window helper ⇒ one refresh call.
- **Several endpoints writing one row with different field sets** (detail ⊃ list ⊃ summary): a write may only clear fields its own payload owns; narrower payloads carry over the rest, even at a newer version. Test both ways.
- Refresh triggers for **reads** are the screen's job (connectivity regained, app foreground); the sync engine drains writes only.

## 4. Delete only from a complete snapshot

> Absence is deletion evidence only in a complete, authoritative snapshot. In delta mode, absence means unchanged.

- Upsert-only is the bug, not the safe default: it keeps deleted records on screen forever.
- Prove completeness from **metadata**, never from count: a page that fills its limit is truncated until proven otherwise; a total that moves between pages is incomplete; a client cap reached is incomplete; if the API's `total` just echoes the page length, only a short final page proves completeness. Page to completion **before** reconciling.
- Scope candidates to exactly what the read covered (user + role + resource scope). A read with no definable scope never reconciles.
- Local intent always survives: rows with a queued op in any status, a created row awaiting its mapping, and rows written at/after the request started are never pruned. Compute these over the delete candidates, not the fetched page.
- Delta pages never reconcile; deletions arrive as **tombstones** (`deletedAt`/`isDeleted` on every cached entity). Use an opaque cursor the client echoes verbatim — do not parse it into a `DateTime` (web `DateTime` is millisecond precision; rounding skips rows or loops).
- Test each rule with a positive control (a case where the row must be removed).

## 5. Cache schema, migrations, and dates

- **Cache table = full DTO as a JSON payload + a few promoted, indexed columns** (id, status, parent id, timestamps, tombstone). A new API field needs no migration; only promoted columns do. Index every promoted column used in `WHERE`/`ORDER BY`.
- **No enforced foreign keys on cache tables.** Child rows can arrive before parents, and pruning removes terminal parents first; a dangling reference is normal transient state. A cache is not an authoring database — referential integrity is the server's job. (Authoring/local-master databases remain a different case.)
- **Added columns are nullable or have a default** (an `ADD COLUMN ... NOT NULL` with no default fails on upgrade).
- Keep a cache schema-version stamp: an incompatible upgrade may **drop cache tables and refetch** — never the queue or draft tables (unsynced user intent).
- Every schema bump commits a schema snapshot and a **per-hop upgrade test** that (a) keeps queued/user rows and (b) leaves the database usable. Add a **chained-upgrade test** from the oldest supported version — per-hop tests alone do not prove the whole path.
- Set a busy timeout when more than one connection can open the file.
- **Dates:** many stores read a stored epoch back as local time, so `==` against a UTC literal fails for the same instant. Compare instants (`isAtSameMomentAs`, `isAfter`, `difference`), at the precision the store keeps — for last-write-wins and staleness checks.
- With Drift, `dart run drift_dev make-migrations` writes the schema snapshot, the `stepByStep` helper and a `SchemaVerifier` data-preservation test per version; setup in [flutter-offline-sync.md](flutter-offline-sync.md) ("Migrations with Drift").

## 6. Account isolation and sign-out with pending changes

**Bind the cache to its account.** Sign-out wipe alone is not isolation: a session that ends while the app is dead (revoked, expired) leaves user A's cache readable by user B at next cold start.

```text
open cache:
  uid unknown / signed out          → open nothing new, bind nothing, wipe nothing
  stored owner == uid               → open
  stored owner != uid, or cache exists with no stored owner (upgrade) → wipe files + key, VERIFY gone
                                      (not gone ⇒ refuse to open: fail closed) → bind uid
```

Store the owner id next to the encryption key in secure storage; destroying the key clears both. A new signed-in uid appearing after the instance opened discards the instance so the next open re-checks.

**Sign-out with queued writes — three branches:**

1. Queue empty → sign out immediately.
2. Non-empty and online → "Syncing N changes…" with a "Sign out anyway" escape; time-boxed best-effort drain (hard budget, e.g. 10 s, never extended); clean drain → sign out.
3. Offline, budget expired, escape tapped, or anything still pending → explicit "Signing out will discard N changes" confirm that links to the waiting-to-sync list.

Rules:

- **Every** path that ends a session runs the guard — profile, app-lock screen, forced sign-out (401, account deletion, wrong role) — or at minimum logs how many queued ops it discarded (count only, never payloads).
- A guard failure **fails closed**: stay signed in and say so. The only "proceed" case is a typed "queue unavailable" meaning the database never opened this session; if database files exist but are unreadable, ask "Discard unreadable changes?".
- Never move the queue to a post-logout store; never silently extend the budget.
- The wipe is destructive and reachable only from a real sign-out ([flutter-offline-reliability.md](flutter-offline-reliability.md) §8): delete the database **file** (not `DELETE FROM`), destroy the key, delete media directories (upload staging and download cache).
- Encrypt at rest when the cache holds personal data; keep the key in secure storage only, generated on first launch, never derived from credentials; a key/database mismatch ⇒ drop the cache and refetch (never the queue silently: run the pending-changes guard). Setup (SQLite3MultipleCiphers via the `sqlite3` build hook, fail-closed cipher guard, one file and key per user): [flutter-offline-sync.md](flutter-offline-sync.md) ("Encryption at rest").

## 7. Keep offline data out of OS backups

- **Android:** `allowBackup="false"` alone is not enough. Docs (developer.android.com/identity/data/autobackup, verified 2026-11-21) say that for apps targeting API 31+ it can disable cloud backup on some devices but not device-to-device transfer. Also declare `android:dataExtractionRules` (Android 12+, excluding all domains for both `<cloud-backup>` and `<device-transfer>` — a missing section is treated as enabled) and `android:fullBackupContent` (Android 11 and lower).
- **iOS:** set the `isExcludedFromBackup` resource value on the directories holding the database and staged media at every launch (idempotent; log failures, never block launch). Whether excluding a directory covers its contents should be confirmed on a simulator by inspecting the backup-exclusion extended attribute — treat inheritance as **unverified** until you do.
- The OS cache directory is already excluded from backup on iOS; confirm by reading your path rather than assuming.

## 8. Retention, staleness, and caches

- **Retention:** keep the N most recent terminal entities per collection AND a max age (whichever prunes more). Run pruning in one transaction with the queue lookup so a row with an in-flight op is protected. Never prune rows with retained `failed`/`dead` ops. Run `VACUUM` (or your store's compaction) after large prunes.
- **Byte budgets must be read:** a budget constant that no code reads is not a budget. Enforce queue-staging bytes at enqueue and the download-cache budget at write.
- **Download cache:** bounded LRU keyed by stable media id (never a volatile signed URL), evicted with its owner, wiped on logout; cache what the user works with, not the whole store.
- **Staleness is a policy, not a caption.** Keep a per-collection `fetchedAt` to decide when to refresh and to separate "never synced" from "synced and empty". Showing a freshness label is a separate per-screen design call. For one record show the later of the collection stamp and the row's own stamp — both mean the server answered; a record's `updated_at` does not. A read at the same version must not move `fetchedAt`.
- If the app uses Firestore offline persistence, set it explicitly and give it an explicit cache size — do not rely on defaults. See [firestore-status-bus.md](firestore-status-bus.md).

## 9. Tier boundaries on the read side

- Before declaring a section online-only, check whether the device already holds it: when a live read fails, fall back to the cached detail for **display** and keep decisions that need freshness on the live read.
- Never cache secrets, raw payment data, or document bodies you do not need offline. Online-only (T3) actions are checked before the request, show offline copy, and send nothing — see tiers in [flutter-offline-sync.md](flutter-offline-sync.md).
- Never map a network failure onto a domain error ("offline" must not become "invalid code"), and audit the `default` arm of error switches: it should be the vaguest true statement. A catch that only logs is a silent failure — tell the user (capture the messenger before the `await`).

---

## Known gaps (not solved by this guidance)

- Chained migration tests across many versions require your own harness; per-hop tests do not cover them.
- Per-record conflict-recorded states and key-table pruning on the server are product/backend decisions this guide does not settle.

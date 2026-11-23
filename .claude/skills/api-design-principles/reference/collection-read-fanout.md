# Collection read fan-out: N+1 across the network, the ORM, the cache and the model

Read this before you build any screen, list, dashboard, read model or endpoint that returns or renders a collection. It applies to web and mobile clients, backend services, MCP tools and AI agents alike.

> **Remote work must scale with the number of data sources or pages, not with the number of rendered rows.** A provider, a stream, a repository abstraction or a backend loop does not make N+1 acceptable. It only hides it.

## 1. The invariant

Never build a read path that makes one network, database, external API or model call per rendered parent item when a bounded batch, join, aggregate or paged query can return the child data.

```text
Client, prohibited:  for each order:  GET /shipments?order_id=...
Server, prohibited:  for order in orders: db.query(Shipment).where(Shipment.order_id == order.id)
```

## 2. O(N) local work is fine. O(N) remote calls are the defect

The concern is repeated expensive boundary crossings: network, database, external API, model call, document-store read, remote storage. Not every loop is N+1.

| Acceptable | Defect |
|---|---|
| 1 request returns 100 records, the client groups them in memory | 100 records cause 100 requests |
| One SQL query returns children for 100 parents | 100 parents cause 100 SELECTs |
| A loop over an in-memory list | A loop that awaits a boundary call on each pass |

## 3. Pre-flight: answer these before you write the read path

1. How many parents can this view render? State the realistic maximum.
2. Does each row or card fetch, or subscribe to, related data?
3. Does mounting N rows create N calls? Does refreshing the parent trigger N child refreshes? Does a rebuild or re-subscription repeat them?
4. Is the child data already in another DTO, cache or read model?
5. Can the backend answer with one JOIN, batch, aggregate or bounded page?
6. Can the repository fetch once and hand the results to the per-item consumers?
7. What happens at 10, 100 and 1,000 parents, on refresh, and after a restart restores the cache?

If any answer implies O(N) remote calls, stop and redesign before you implement.

## 4. Preferred shape

```text
UI -> state -> repository -> batched or parent-scoped API -> set-based query
one response -> repository/cache -> grouped by parent id -> many UI consumers
```

## 5. Backend: set-based queries, and check the SQL the ORM really sends

Prefer JOIN, `IN` / `= ANY($1)`, aggregation, eager (`selectin` / `include`) loading, server-side filtering and pagination. Avoid a query inside a parent loop, lazy loading hidden in serialisation, and one repository call per row. Log or `EXPLAIN` the statements the ORM actually issues; do not assume eager loading is configured. SQL patterns: `postgres-best-practices` (rule `data-n-plus-one`). Compute totals with a `count()` query, never `len(rows)` of one page.

## 6. API shape

When a view needs several related entities, consider a batch endpoint, a parent-scoped collection endpoint, an expanded child summary, an aggregate read model or a bounded `ids` parameter. Never add an unbounded "return everything" endpoint. Return only what the view needs, and paginate (`rest-design-principles.md`).

## 7. Authorisation: batching must never widen scope

```text
BAD   the client sends 100 ids and the server trusts them
GOOD  authenticated caller -> the server derives the allowed scope -> the query is constrained by it
```

Put the scope predicate in the query, and take the actor from the verified token, never from the request body. Carry over every guard the per-item path had: a soft-delete filter that the per-item endpoint got for free from its 404 must become an explicit predicate in the batch. Add negative cross-tenant tests, and prove them with a control that deletes the predicate and watches the test fail.

## 8. Repository, cache and reactive state

- One collection fetch fills the **existing** repository or cache, and per-item consumers read from it. Do not add a second cache, a parallel repository or a screen-specific duplicate model.
- A per-parent provider or selector is fine when it reads shared local state. It is a defect when each instance hits the network on its own.
- **Streams are not free.** If `watchX(parentId)` triggers a fetch when the stream is created, N cards with N streams is N+1 in disguise. Prefer one collection stream and filter it locally for each child view.
- **Coalesce concurrent fetches (single flight).** N callers that reach the same wide read without a guard make N wide fetches, which is worse than N narrow ones. Clear the in-flight future in a `finally`/`whenComplete`, not on success only, or one failure blocks the repository forever. Test both directions: N concurrent callers make 1 request, and a later call still makes its own.
- Before you change a shared stream or repository method for one consumer, list every consumer. Prefer adding a sibling method.

## 9. Measure each phase separately

Cold mount, refresh, rebuild or navigation, realtime and idle each have their own request count. A view can be clean on refresh and still fan out on cold mount (refresh = 2 requests, cold mount = 40). Idle should be about 0 requests unless polling is a deliberate design choice.

## 10. Pagination: batching is not one giant request

Use bounded pages. 106 rows at `page_size=100` is 2 requests, and that is correct. Do not set `page_size=100000` to claim "one request". Measure request count, payload size, latency and memory together.

**Fetch every page before you reconcile.** If a refresh deletes cached rows missing from the response, reconciling against page 1 deletes rows that are only on page 2. A kill switch or flag-off path must fetch the same shape as the optimised path, or switching it silently truncates the data.

## 11. AI, MCP and external services

The same rule applies beyond REST. Avoid one model call per item, one geocoding call per address, one ranking call per candidate or one embedding call per document when a batched call can handle the set. Cost fan-out is a production defect even when latency looks fine (`ai-playbook`, `vector-database`).

## 12. Writes

Avoid one POST per row when the API supports a transaction or batch endpoint. Never batch writes that need independent authorisation, financial approval, safety decisions or separate idempotency keys. Correctness and auditability matter more than request count.

## 13. Evidence and tests

Report before and after for every collection view: parent rows, HTTP calls, DB queries, external/model calls, cold-mount and refresh duration, idle requests. Passing unit tests are not evidence that the N+1 is gone. Count the calls on the wire (browser network panel, `playwright-cli` network log, ORM query log, proxy).

Positive tests: N parents do not cause N calls; the batch groups children correctly; pagination; authorisation; empty collection; cache restore; no duplicates; sort order preserved.

Controls, each of which must turn the test RED (see `verification-before-completion/reference/positive-control-harness.md`):

- Put the per-parent loop back, and the request-budget test fails.
- Remove the single-flight guard, and concurrent callers make N calls.
- Drop the scope predicate, and unauthorised rows appear.
- Skip page 2, and the completeness test fails.

Make budget tests assert the **dimension**, not a brittle total:

```text
GOOD  "GET /shipments does not scale with order count"  (assert calls <= ceil(total / pageSize))
BAD   "total requests == 19"                             (breaks on any unrelated call)
```

## 14. Review triggers (flags for a human, not proof)

An `await` on a repository or API inside a loop. `.refresh(` or `invalidate` inside a loop over IDs. A DB `select` inside a loop. A per-row component that starts its own fetch. Some bounded loops are fine, so grep can only flag candidates.

## 15. Design output to record

```text
Cardinality:              Read pattern:             Potential N+1:
Batch strategy:           Pagination:               Cache strategy:
Authorisation scope:      Offline behaviour:
Cold-mount request budget:   Refresh request budget:   Realtime behaviour:
```

If you cannot fill these in, the data-fetch design is not ready to implement.

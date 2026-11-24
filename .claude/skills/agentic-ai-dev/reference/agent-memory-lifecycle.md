# Agent Memory Lifecycle (framework-neutral)

Canonical, framework-neutral home for agent memory and knowledge (MEM requirement ids map to §1–§16 here): memory types, the item contract, write policy, compilation, isolation, freshness, conflicts, erasure, user controls, storage, evaluation, metrics and cost. Framework mechanics live in the adapters; this file does not repeat them.

| Topic | Canonical home |
|---|---|
| Normative rules (MUST/SHOULD, ADAPT defaults) | this file: §1–§13 for the contract, §14 for full normative detail and defaults, §16 for organisation-owned decisions |
| LangGraph / LangChain mechanics (checkpointer, Store, `remember` / `recall`, trimming) | `agentic-memory-systems.md` |
| Google ADK mechanics (memory services, `add_memory`, Memory Bank purge, scope) | `google-adk/reference/adk-memory-artifacts.md` |
| Answer and tool caches that may hold memory-derived text | `agentic-caching-patterns.md` rules 6 and 8 |
| G15–G17 and every other guardrail | `ai-playbook/reference/engineering-guardrails.md` |
| Eval layers, golden sets, red-team tiers | `eval-guide` skill (`reference/golden-dataset.md`, `reference/red-teaming.md`) |
| Deletion verification as a governance control, risk and autonomy | `ai-governance` skill |
| Record validator | `scripts/validate_memory_item.py` + `assets/schemas/memory_item.schema.json` |

Evidence for this file: the validator's `--selftest` (30 checks) and a sandbox reference store with 21 deterministic tests (in-memory SQLite, no model) covering isolation, poisoning, canonical precedence, staleness, conflicts, idempotent compilation, deletion propagation, consent and authorization failure. The SQL in §5 and §8 was not run against PostgreSQL here: run it on your stack.

## 1. Authority rule in code

Memory is context, never truth (full authority order and may/must-not lists: §14.1). Every read path ends in one decision:

```python
def resolve_fact(canonical: Fact | None, item: MemoryItem | None, now: datetime) -> Answer:
    if canonical is not None:                                   # canonical wins immediately
        if item is not None and not item.agrees_with(canonical):
            mark_conflicted(item, reason="MEMORY_VS_CANONICAL")  # §11: route, never pick a side
        return Answer(canonical.value, source="canonical", as_of=canonical.version)
    if item is None or item.status != "CURRENT" or item.is_stale(now):
        return Answer(None, source="canonical_unavailable", label="summary is updating")  # §8.3
    return Answer(item.content, source="memory", as_of=item.generated_at, item_id=item.item_id)
```

- Every rendered memory carries `source` and `as_of` (G17, G21). A missing or building item is not missing history: load the canonical record.
- Memory never authorizes, decides eligibility, changes workflow state or suppresses a required review. Keep those decisions in code that reads canonical state only (G2, G14).

## 2. Memory types (ADAPT)

A type is supported only when its definition row is filled in. Keep types narrow; no "everything memory".

| Field | Conversation history | Long-term user / entity | Compiled knowledge | Episodic outcome | Shared org knowledge |
|---|---|---|---|---|---|
| Authoritative sources | `<thread store>` | user statements, `<profile system>` | `<canonical tables/docs>` | `<case / outcome records>` | `<curated KB>` |
| Allowed derived facts | `<…>` | preferences, stated constraints | summaries, timelines with lineage | verified results | approved playbooks |
| Prohibited conclusions | current-state facts | sensitive attributes, rankings of people (G19) | authority, untraceable claims | eligibility, performance judgments | per-user data |
| Freshness class (§8.1) | Personal | Personal | P1 | P1 | P2 |
| Role visibility | owner | owner + `<roles>` | `<roles>` | `<roles>` | org |
| Rebuild triggers | n/a | correction, dispute | source event, compiler upgrade | reversal, correction | curator change |
| Retention | `<N days>` | until changed / `<N months>` | regenerable | `<N years>` | versioned |
| Quality metrics | recall@k | recall@k, disputes | unsupported-claim rate | provenance correctness | review SLA |
| `consequential` | false | false | true | true | true |

Working / session memory is not durable: it is keyed by session **and** authenticated principal, discarded at session end, and never gets a `MemoryItem`. Promoting anything from it is a write under §3.

## 3. Item contract and write policy

Every durable item is a typed record that validates against `assets/schemas/memory_item.schema.json`. Run the validator in CI on fixtures and on any exported records:

```bash
python3 .claude/skills/agentic-ai-dev/scripts/validate_memory_item.py --json path/to/items.memory.json
# exit 0 valid, 1 invalid record(s), 2 usage/IO/schema error; --selftest proves the rules still bite
```

It rejects, with stable codes: no `org_id` (`MISSING_ORG_ID`), no lineage (`NO_LINEAGE`), no expiry (`NO_EXPIRY`), untrusted writers (`UNTRUSTED_WRITER`), users writing about others (`USER_WRITES_ABOUT_OTHERS`), agent writes not held for review (`AGENT_WRITE_NOT_HELD`), `MODEL_INFERRED` / `UNKNOWN_PROVENANCE` kept `CURRENT` on a consequential item, untraceable claims not marked `REVIEW_REQUIRED`, unversioned compilers, misaligned `source_versions`, credentials or payment data in content, facts or claims, `CURRENT` + `STALE`, and DELETED tombstones that keep content. It checks structure only; it cannot prove isolation or erasure.

Writer matrix enforcement:

| Writer | Enforcement point |
|---|---|
| Versioned compiler | the only writer of compiled knowledge and episodic outcomes; records `compiler_version` (+ `model_name`, `prompt_version` for LLM steps) |
| Agent at runtime | writes working memory; durable writes become proposals: `MODEL_INFERRED`, `REVIEW_REQUIRED`, routed to a queue |
| User | writes only items whose `subject_id` is the authenticated user; corrections apply immediately to their own stated facts |
| Curator | shared knowledge through a reviewed, diffed write path |
| Tool output, retrieved documents, uploads, inbound messages, web | nothing durable; input to a reviewed pipeline only |

- Data classes: each type declares `allowed_data_classes` / `prohibited_data_classes`. Credentials, access codes, full card or bank details are never stored. The validator's pattern check is a backstop, not the detector: PII/secret detection runs before compile **and** before embedding, is language-aware, and its false-negative rate is measured on an adversarial set (`eval-guide`). Detector failure or low confidence → `REVIEW_REQUIRED`, nothing compiled or embedded.
- Minimize: memory holds a reference to raw PII in the canonical store, not a copy.
- Long-term personal memory needs a documented legal basis and user controls (§10). Never used for training unless explicitly permitted (G20).

## 4. Compilation pipeline

```text
source event → eligibility check → normalize (keep originals) → PII/secret detect + redact
  → entity resolution (confirmed identity, never similarity alone) → schema validation
  → compile (versioned) → claim ↔ source linkage → lint → persist item → async index projection
```

- Inputs are pinned source versions (`source_versions`), so a rebuild is reproducible. LLM steps use fixed settings and structured output (G3).
- Every derived item can be deleted and rebuilt from sources. If it cannot, it is an unmanaged source of truth: do not ship it.
- Asynchronous: no user-facing workflow blocks on a compile. Coalesce per entity, but never coalesce away invalidation, safety or audit events.
- Latest wins: an older compile never overwrites a newer canonical version (SQL in §8).
- Compiler, model, prompt or schema upgrade → mark dependents `REBUILD_REQUIRED`, backfill invalidation/safety types first, and run the memory eval set (§11) before broad rollout.

## 5. Isolation: authorize before read

`caller identity + org + role + purpose → scope filter → memory read`. Never read globally and ask the model to filter.

```sql
-- PostgreSQL: the app connects as a non-owner role (owners and superusers bypass RLS unless FORCE is set)
ALTER TABLE memory_item ENABLE ROW LEVEL SECURITY; ALTER TABLE memory_item FORCE ROW LEVEL SECURITY;
CREATE POLICY org_scope ON memory_item
  USING (org_id = current_setting('app.org_id', true))
  WITH CHECK (org_id = current_setting('app.org_id', true));
-- per request, inside the request's transaction, org from the verified token (true = transaction-local, so a
-- pooled connection never carries the previous request's org): SELECT set_config('app.org_id', $1, true);
```

- Subject and role filters apply on top (`subject_id`, `role_visibility`), before ranking. Index entries (vectors, keyword) carry `org_id`, visibility and `item_id`/version so the filter runs before similarity.
- Side channels count as leaks: nearest neighbours, snippets, counts/facets, cached answers, related-entity traversal, summaries that mention another subject. Test each one with a distinctive planted string.
- Role visibility applies to content: compile per-visibility variants rather than redacting at render time.
- A missing org/user/role fails closed (an exception, never an unscoped query). A session id alone is not authorization.
- Cross-org aggregates need contractual permission, de-identification and a `<k>`-org floor; otherwise omit them.

## 6. Freshness, invalidation and conflicts

| Status | Consumer behaviour |
|---|---|
| `CURRENT` | use, with `as_of` label |
| `STALE` | label; canonical fallback for consequential uses |
| `SUPERSEDED` | never presented as current |
| `CONFLICTED` | show both with citations or defer to canonical; route to review |
| `REBUILD_REQUIRED` | canonical fallback |
| `REVIEW_REQUIRED` | suppressed from high-confidence surfaces |
| `DELETED` | tombstone: lineage only, no content |

- Each type declares its max staleness (P0 seconds–minutes … Personal until changed); `freshness_state` is computed at read time from `generated_at`.
- Source change → invalidation by event (preferred) and scheduled reconciliation (backstop: orphaned items, broken links, version drift). Hard events (reversal, reopen, correction, retraction, supersession) mark dependents `SUPERSEDED` / `REBUILD_REQUIRED` immediately, before the rebuild.
- Aggregates support subtraction: a retracted outcome removes its contribution and rebuilds dependents; prior versions stay for audit.
- The AI never resolves a consequential conflict by choosing a side. Lint (every compile + scheduled) flags missing sources, orphans, mixed compiler versions, entity mismatch, contradictory claims; it auto-fixes only non-consequential issues.
- Every review state lands in a queue with `queue_id`, `owner`, `created_at`, `due_at`, `escalation_owner`, `resolution_reason`, `evidence_required_to_close`. A review status without owner or SLA is a defect (G5).

## 7. Retention and erasure

Lineage is the erasure index: find dependents by `source_refs` / `source_event_ids`, never by text search.

| Surface | Mechanism | Proof (plant → erase → probe) |
|---|---|---|
| Items + claims | delete or rebuild without the subject | `SELECT count(*)` = 0 for the planted string |
| Retrieval index / vectors | cascade from the item (FK or projection job) | k-NN for the planted vector returns no erased id |
| Answer and tool caches | secondary index `item → cache keys`, or bump the memory version in the key (`agentic-caching-patterns.md` rule 8) | identical query misses |
| Summaries mentioning the subject | rebuilt without it, not hidden | rebuilt text lacks the planted string |
| Managed stores | ADK: `delete_memory` cannot erase a principal; use the store's purge (`adk-memory-artifacts.md` §4.2) | search by principal returns 0 |
| Offline / client caches | revocation + hard expiry (§9) | client refresh drops the item |
| Backups, revisions, legal hold | documented policy; residual windows counted in the SLA (Memory Bank keeps deleted-memory revisions up to 48 h) | governance evidence (`ai-governance`) |

Every type declares retention and `expires_at`; nothing is keep-forever. Legal hold overrides expiry for scoped items and is audited. An item without lineage cannot be erased reliably and is therefore not allowed.

## 8. Storage: metadata store + async projection

```text
canonical stores → (events / reconciliation) → memory metadata store → (async, versioned) → retrieval index → authorized read
```

```sql
-- idempotent, latest-wins upsert; commit the item first, project afterwards (outbox), never one dual-write transaction
INSERT INTO memory_item (...) VALUES (...)
ON CONFLICT (item_id) DO UPDATE SET content = EXCLUDED.content, canonical_version = EXCLUDED.canonical_version,
       source_versions = EXCLUDED.source_versions, generated_at = EXCLUDED.generated_at
WHERE memory_item.canonical_version <= EXCLUDED.canonical_version;
```

- Use the relational or document platform you already run (G13); the index is a projection (a vector extension of that database first; a dedicated store only on measured need). If projection fails, the item stays valid and semantic recall degrades visibly (G6).
- Embedding-model or chunking change = versioned migration + re-index + memory evals (G15). Never mix vector spaces in one index.
- No free-text memory files or folders; render human-readable views from the typed store.

## 9. Scope changes, portability, client caches (ADAPT)

Per type, declare whether it is portable on owner/org change (never copy everything), how account merges re-key (audited mapping; conflicts → `CONFLICTED`), what happens when a user leaves an org, and that visibility is re-evaluated at read time on role change. Transfers record effective time, old access end, new access start, types moved, redactions, legal authority. Clients cache only last-known authorized memory with `generated_at` shown, encrypted, minimized, revocable and hard-expiring; on reconnect sync canonical state first, then memory (G23).

## 10. User controls

| Capability | Contract |
|---|---|
| See | list the user's long-term items in plain language with sources and dates (operators: entities they manage) |
| Correct | own stated facts change immediately; corrections touching canonical data go to the owning workflow |
| Forget | delete items and history → §7 propagation |
| Pause | memory off: no writes, no recall; the product still works |
| Disclose | responses that used memory can say so (`memory_item_ids` on the response) |
| Dispute | `NOT_RELATED`, `WRONG_SUBJECT`, `WRONG_SUMMARY`, `STALE`, `OTHER` → suppress claim, queue, add to eval set, rebuild after correction, suppress the same suggestion unless evidence changes |

Feedback never mutates canonical history directly.

## 11. Evaluation

Memory evals follow `eval-guide` (layers, golden-set manifests, CI tiers); gate thresholds are in §14.9 and are defaults to ratify (ADAPT). Golden cases carry `(query, subject, expected_item_ids, forbidden_item_ids)` plus memory type, compiler, model, prompt and dataset versions on every result.

| Dimension | Method | Notes |
|---|---|---|
| Isolation / leakage, erasure, provenance correctness, authority, staleness, missing-artifact fallback | deterministic tests (§12) | never an LLM judge; target 0 leaks, 100 % erasure |
| Recall correctness | golden set with forbidden ids | recall@k |
| Factuality | claim-to-source check, judge + sampling | 0 unsupported claims on consequential types |
| Poisoning resistance | persistent-injection red-team cases (`eval-guide/reference/red-teaming.md`) | assert on the persisted store and tool calls |
| Regeneration | rebuild diff on same compiler + inputs | within tolerance |
| Per-language quality | per-language subsets | per G7 |

Confirmed production memory failures become permanent regression cases.

## 12. Tests every memory implementation needs

1. Cross-org and cross-user: a distinctive planted string is absent from rows, counts, k-NN results, snippets and cached answers of the other scope.
2. Missing org/user/role raises; unauthenticated principal raises; role outside `role_visibility` sees nothing.
3. Untrusted writer rejected; user cannot write about another subject; instruction-like content and `MODEL_INFERRED` items never reach `CURRENT`.
4. Canonical conflicts: canonical value returned, item `CONFLICTED`, queue entry with owner and `due_at`.
5. Stale or missing item → canonical fallback with "updating" label, never a blank or stale summary as complete.
6. Hard invalidation → `SUPERSEDED` immediately and excluded from recall.
7. Replay of the same compile is idempotent; an older compile does not overwrite a newer canonical version.
8. Source erasure propagates to items, index and caches; forget-me removes every surface; pause blocks writes and reads.
9. Projection failure leaves the item valid and recall visibly degraded.
10. `validate_memory_item.py --selftest` exits 0, and a planted invalid record exits 1 (positive control for the CI gate).

## 13. Metrics, traces and cost

Metrics (alerts are defaults to ratify): `memory_items_total{type,status}`, `memory_fresh_ratio{type}`, `memory_oldest_stale_age_seconds{type}`, `memory_rebuild_queue_age_seconds{priority}`, `memory_compile_failures_total{type,reason}`, `memory_review_queue_overdue_total{queue}`, `memory_isolation_violations_total` (any → page), `memory_erasure_sla_breaches_total` (any → privacy owner), `memory_detector_low_confidence_total{class}`, `memory_fallback_to_canonical_total{type}`, `memory_disputes_total{type,reason}`. Keep labels bounded: per-org figures (such as cost per org) come from traces or billing exports, not metric labels (`deployment-ci-cd/reference/ai-observability.md`). Every read adds trace attributes `memory_item_ids`, `memory_types`, `freshness_state`, `compiler_version`: ids, never content (G8).

Compile tiers: EAGER (invalidations, safety, verified outcomes) · EVENT_COALESCED (entity history, briefings) · BATCH (aggregates, playbooks) · LAZY (rare summaries, cached with lineage). Each type declares `max_compile_frequency`, `priority`, `target_compile_latency`, `max_staleness`, `retry_policy`, `cost_budget`, `fallback`. Use the cheapest model that passes the memory eval for the type (G12). Under burst (imports, backfills): per-org quotas, backpressure and deferral in the order invalidation/safety → verified outcomes → operational history → user-facing summaries → analytical aggregates. Track compile, embedding, rebuild, storage and retrieval cost plus cost avoided; memory that costs more than it saves is turned off (G24).

## 14. Normative detail and defaults to ratify (ADAPT)

Scope: any agent or AI feature that persists, summarises, embeds or re-uses information beyond a single model call. Precedence: the guardrails win over this file and stricter domain sources of truth win over both. Raw document retrieval is RAG (`rag-architect`, G15); this file governs what the AI system **derives and retains**. Normative words: **must / must not** = mandatory; **should** = default, deviation needs a recorded reason; **may** = optional.

### 14.1 Authority order: what memory may and must not do

```text
1 canonical structured state (system of record) > 2 authoritative source documents > 3 verified recorded outcomes
  > 4 derived / compiled memory (summaries, embeddings, profiles, lessons) > 5 LLM inference
```

- Canonical state wins **immediately**, without waiting for a rebuild (G16). Memory is never authoritative because it is concise, indexed, recent or produced by a stronger model.
- Memory **may**: summarise facts, connect related records, surface prior history, shortcut retrieval, personalise tone and defaults, prepare briefings, supply *candidate* patterns for human review, seed eval datasets, reduce repeated reasoning cost.
- Memory **must not**: override safety or policy logic, establish eligibility, authorise spend or access, change workflow state, close or verify work, suppress a required human review, reinterpret an authoritative document without citing it, or penalise a person or partner on the strength of a summary alone (G2, G14).
- Every consumer that renders memory can say where it came from and how old it is (G17, G21).

### 14.2 The six memory types

| Type | Scope | Typical lifetime | May be used for | Must not be used for |
|---|---|---|---|---|
| Working / session | one execution or session | minutes–hours; discarded at session end | intermediate tool results, plan state, scratch reasoning | persistence beyond the session; another user's session |
| Conversation history | one user (+ org), one thread | per retention policy | continuity, follow-up resolution | facts about current state (re-fetch them); training without consent |
| Long-term user / entity | one user or entity within one org | until changed, expired or erased | preferences, stated constraints, stable profile facts the user provided or confirmed | inferred sensitive attributes; eligibility or ranking of people (G19); anything the user cannot see or correct |
| Compiled / derived knowledge | one entity or aggregate within one org | regenerated on source change | summaries, timelines, briefings, patterns from canonical sources with lineage | authority; anything without lineage; cross-org content without approval |
| Episodic outcomes | one action / case / event | per retention policy | "what happened last time", verified results, eval and regression seeds | current eligibility or performance judgments without causal review; unverified outcomes treated as verified |
| Shared organisational knowledge | one org (or an explicitly shared tier) | curated, versioned | approved playbooks, FAQs, policies, procedures | content from untrusted contributors without review; per-user data |

Each supported type **must** have the §2 definition row (authoritative sources, allowed derived facts, prohibited conclusions, freshness policy, role visibility, rebuild triggers, retention, quality metrics); a type without one is not supported. Sensitive-attribute profiles of people (behaviour scores, "difficult customer" flags, inferred health, ethnicity or similar) **must not** be created (G19).

### 14.3 Provenance quality and claim lineage

| `provenance_quality` | Meaning | Default use |
|---|---|---|
| `RECORDED_LIVE` | captured by the system at the time | normal |
| `USER_STATED` | the user told us; not verified | personalisation only; labelled as user-provided |
| `MIGRATED_STRUCTURED` | imported with source-system ids | context; requires traceability |
| `MIGRATED_PARTIAL` / `RECONSTRUCTED` | incomplete or inferred backfill | visibly marked; excluded from aggregates by default |
| `MODEL_INFERRED` | derived by an LLM without a direct source | never consequential; review before durable use |
| `UNKNOWN_PROVENANCE` | origin unknown | must not feed aggregates or decisions |

An item making several consequential statements stores them as claims (`claim_id`, `claim_text`, `source_refs`, `source_versions`, `confidence`); a consequential claim that cannot be traced to a source is omitted or marked `REVIEW_REQUIRED` (validator code `UNTRACEABLE_CLAIM`). `confidence` is evidence quality, never model self-confidence. Synthetic or reconstructed timestamps are never presented as observed timestamps. Writes are idempotent and version-aware (G4): replaying a compile yields the same item; an older compile never overwrites a newer one.

### 14.4 Compiler requirements

| Requirement | Rule |
|---|---|
| Versioned compiler | Compiler code, prompt, model and policy versions recorded on every item (G11) |
| Deterministic inputs | Inputs are pinned source versions, reproducible from the item's lineage, not "whatever is current at read time" |
| Reproducibility | Same compiler version + same inputs → equivalent item; LLM steps use fixed settings and structured outputs (G3) |
| Regenerability | Every derived item can be deleted and rebuilt from sources; otherwise it is an unmanaged source of truth |
| Asynchronous | No user-facing workflow blocks on compilation unless explicitly designed to (e.g. waiting for a just-uploaded document) |
| Idempotent, latest-wins | Entity-scoped debounce/coalescing; an older compile never overwrites a newer canonical version |
| Never coalesce away | Events required for safety, audit, verification or invalidation are processed individually |
| Multilingual | Original wording preserved; translation is a retrieval aid, never an overwrite; quality measured per supported language |
| Typed types only | One compiler per memory type with its own contract; no catch-all compiler |

Upgrade (new compiler, model or schema version): mark incompatible dependents `REBUILD_REQUIRED` → detect mixed-version contradictions → backfill by priority (safety/invalidation first) → run the memory eval set (§11) before broad rollout. Mixed versions are tolerated temporarily only if consumers can tell them apart and the canonical fallback remains available.

### 14.5 Isolation extras

- Agents read memory through the same authorisation layer and tools as everything else: no private back door.
- A caller in org A must not be able to infer that org B's memory exists (counts, facets, timing of empty results included).
- One entity's memory never attaches to another by similarity alone; entity resolution needs confirmed identity (G14).
- Cross-org aggregates: explicit contractual permission, de-identification and an aggregation floor (default to ratify: ≥ `<k>` distinct contributing orgs); if safe aggregation cannot be proven, omit the aggregate.

### 14.6 Freshness classes (default max staleness)

| Class | Examples | Default max staleness |
|---|---|---|
| P0 invalidation / safety | reversal of a verified outcome, safety-relevant change | seconds–minutes |
| P1 operational | entity history, briefings | minutes–hours |
| P2 analytical | patterns, aggregates, playbooks | daily batch |
| Personal | user preferences | until changed / `<N months>` reconfirmation |

Consumers render staleness ("as of `<time>`", "may be out of date"). Stale items never override canonical facts; safety- or authority-sensitive consumers fall back to canonical sources. Missing, `BUILDING`, `REBUILD_REQUIRED` or stale-beyond-SLA → load the canonical record/timeline, render the authoritative fallback, optionally show "summary is updating" (§1).

### 14.7 Retention and erasure defaults

| Rule | Default (ratify with Legal) |
|---|---|
| Session memory | Discarded at session end or within `<N hours>`; never silently promoted |
| Erasure SLA | Every derived item, claim, embedding, cache, index entry and offline copy that used erased content is removed or rebuilt within `<30 days>`, faster for P0 |
| Embeddings | Vectors from erased content are deleted; re-indexing is verified by a retrieval probe |
| Backups | Documented policy for how erasure applies to backups and when restored data is re-scrubbed |
| Proof | Automated plant → erase → probe test asserts no retrieval, snippet, summary or count still reflects the content (§7, §12 test 8) |

### 14.8 Memory poisoning: threats and controls

| Threat | Control |
|---|---|
| Injected instructions in a message, document or tool output get "remembered" | Untrusted content never writes durable memory (§3 writer matrix); compilers treat inputs as data; re-injected memory is labelled data (`agentic-memory-systems.md` `memory_block`) |
| A user plants false facts about another person or entity | Users write only about themselves (`USER_WRITES_ABOUT_OTHERS`); claims about others need canonical evidence |
| Agent self-reinforcement (model inference later read as fact) | `MODEL_INFERRED`, never consequential, review before promotion; eval for drift |
| Bulk poisoning of shared knowledge | Curated write path, reviewer approval, contributor trust levels, diff review for bulk imports |
| Embedding poisoning (content crafted to land near sensitive queries) | Scope filter before similarity (§5); red-team cases; anomaly detection on new-item nearest-neighbour patterns |
| Slow drift via many small writes | Rate limits per writer; periodic lint and sampling review; anchor-baseline comparison |

No durable write from untrusted input without review or a deterministic, versioned pipeline that validates it against canonical sources. Memory re-injected into a prompt never changes tool permissions, policy or authority boundaries (G9). Every durable item is attributable, so a poisoning incident can quarantine every affected item by `written_by` and source. Red-team suites include persistent-injection cases (`eval-guide/reference/red-teaming.md`).

### 14.9 Eval gates and alert defaults (ratify)

| Dimension | Gate |
|---|---|
| Recall correctness (golden set with expected **and forbidden** item ids) | recall@k ≥ `<0.85>` |
| Factuality / faithfulness (claim-to-source, judge + sampling) | unsupported-claim rate ≤ `<1 %>`; 0 for consequential types |
| Provenance correctness (deterministic) | 100 % |
| Staleness handling (event-injection tests) | 100 % for hard invalidation events |
| Authority (conflict fixtures: memory X, canonical Y) | 100 % canonical wins |
| Isolation / leakage (deterministic, never an LLM judge) | 0 leaks |
| Erasure (plant → erase → probe) | 100 % |
| Poisoning resistance (persistent-injection red team) | 0 successes |
| Missing-artifact fallback (fault injection) | 100 % |
| Regeneration (rebuild diff) | within tolerance |
| Per-language quality | per G7 |

| Metric | Alert |
|---|---|
| `memory_fresh_ratio{type}` | < `<0.95>` for P0/P1 types |
| `memory_oldest_stale_age_seconds{type}` | > type SLA |
| `memory_rebuild_queue_age_seconds{priority}` | P0 > `<5 min>` |
| `memory_compile_failures_total{type,reason}` | > baseline |
| `memory_review_queue_overdue_total{queue}` | any → queue owner |
| `memory_isolation_violations_total` | any → page now |
| `memory_erasure_sla_breaches_total` | any → page privacy owner |
| `memory_detector_low_confidence_total{class}` | trend → detector review |
| `memory_fallback_to_canonical_total{type}` | sustained rise → compile health |
| `memory_disputes_total{type,reason}` | rising → quality review |

## 15. Anti-patterns

Treating memory, summaries or embeddings as the system of record, or rendering memory without source or date · a generic "everything memory" / AI wiki with no types, owners or contracts · free-text memory files or untracked vectors with no `org_id`, lineage or version · agents or untrusted content writing durable memory directly · secrets, credentials, access codes or payment data in memory or embeddings · reading memory globally and asking the model to filter by user or org · similarity alone attaching memory to an entity or merging entities · append-only aggregates that cannot subtract a retracted outcome · a blank or stale summary shown while the compile is pending · the model picking a winner between conflicting authoritative sources · deleting the source but leaving summaries, embeddings and caches that still reflect it · inferred sensitive-attribute or behaviour profiles of people · blocking a core workflow on compilation · compiling every type on every event with no per-type cost budget · memory users cannot see, correct or delete.

## 16. Adoption checklist (organisation-owned)

Decisions and owners the organisation supplies: the supported types and their definitions, retention periods (with Legal), the legal basis and notice for long-term personal memory (§3), review-queue owners and SLAs, freshness SLAs, the cross-org aggregation floor and contracts, portability rules and the backup-erasure policy. The validator, reference store tests and metrics above are aids, not proof that these decisions were made.

- [ ] Authority rule adopted; every memory consumer shows source and age (§1, §14.1)
- [ ] Supported types listed, each with a full definition row (§2, §14.2)
- [ ] Typed item contract with lineage, provenance quality, status, freshness; validator in CI (§3, §14.3)
- [ ] Write policy per writer; untrusted content cannot write durable memory (§3)
- [ ] Prohibited data classes enforced; measured PII/secret detection before compile and embed (§3)
- [ ] Versioned, reproducible, regenerable compilers; upgrade policy (§4, §14.4)
- [ ] Authorize-before-read with `org_id` + subject + role visibility; side-channel isolation tests (§5, §14.5)
- [ ] Freshness SLAs per type; hard invalidation events; aggregate reversal; canonical fallback (§6, §14.6)
- [ ] Retention per type; erasure propagates to summaries, embeddings, caches; erasure test automated (§7, §14.7)
- [ ] Poisoning controls and persistent-injection red-team cases (§14.8)
- [ ] Conflict states and owned review queues with SLAs (§6)
- [ ] User see / correct / forget / pause; dispute flow (§10)
- [ ] Metadata store + async retrieval projection; no dual-write (§8)
- [ ] Portability rules per type; client cache policy (§9)
- [ ] Memory eval set covering the §14.9 dimensions; isolation and erasure at 100 %
- [ ] §13 metrics, trace attributes and §14.9 alerts live
- [ ] Compile tiers and cost budgets per type; burst priority order (§13)

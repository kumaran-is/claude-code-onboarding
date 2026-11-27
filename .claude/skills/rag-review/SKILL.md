---
name: rag-review
model: opus
description: "End-to-end RAG pipeline audit across 8 stages (ingestion, versioning, embedding/indexing, routing, retrieval/reranking, generation/abstention, security, eval/observability). Use for \"review/audit RAG\" or a pre-merge RAG check. Not for diagnosing one failure (rag-debugger)."
allowed-tools: Read, Glob, Grep
metadata:
  triggers: review RAG pipeline, audit RAG, RAG E2E review, is this RAG production ready, check RAG implementation, RAG pre-merge review, review this RAG code
---

# RAG E2E Review Checklist

## Iron Law

> **A RAG pipeline ships only when retrieval, generation, security, AND eval all pass. Three out of four is a production incident.**

This skill is the single source of truth for "what does a production-grade RAG pipeline look like across all 8 stages." Reviewers cite reference files for detail — they do not restate content here.

## How to use this skill

**For human users:** Invoke `/rag-review` for an E2E audit. For deeper review, dispatch `@rag-implementation-reviewer` — it auto-loads this skill.

**For agents consuming this skill:** Walk the 8 stages in order. For every check, cite the file:line of the authoritative reference. Don't manufacture findings — if a stage is clean, say so in one line.

## Severity rubric

| Severity | Meaning | Verdict impact |
|---|---|---|
| 🔴 **Critical** | Security incident, data integrity, prompt injection, hallucination on high-risk path | BLOCK |
| 🟠 **High** | Production correctness, recall ceiling, missing audit log, missing abstention | NEEDS_REVIEW (fix before merge) |
| 🟡 **Medium** | Quality + ops drift (no eval gate, no per-axis breakdown, missing cache) | NEEDS_REVIEW (recommend) |
| 🟢 **Low** | Hygiene (missing comments, magic numbers, undocumented alpha) | APPROVE with note |

---

## Stage 1 — Ingestion & Chunking

Cross-refs: `rag-architect/references/advanced-chunking-guide.md`, `rag-architect/references/table-chunking-strategy.md`

| # | Check | Severity if failing | Reference |
|---|---|---|---|
| 1.1 | Parser matches corpus type — not raw `pdf.extract_text()` for complex PDFs; LiteParse (local) or LlamaParse (hosted, **approval required**; not deprecated `llama_parse`) for table-heavy / scanned docs | 🟠 | `llamaindex/references/parse-choice.md`, `advanced-chunking-guide.md §6` |
| 1.2 | Document-aware chunking on headings/sections — NOT fixed-size sliding window as the only strategy | 🟠 | `advanced-chunking-guide.md §1` |
| 1.3 | Chunk size calibrated by document type: prose 500–800 tokens, structured/SOP 300–600, tables = whole or row-groups | 🟡 | `advanced-chunking-guide.md §1` + `rag-operations-guide.md §6` |
| 1.4 | ~10–15% overlap on size-based splitters; 0 allowed on natural boundaries with parent/neighbour expansion | 🟡 | `rag-architect/SKILL.md` (canonical overlap and cap rule) |
| 1.11 | Max chunk tokens ≤ reranker input limit minus longest expected query; unit test asserts no chunk exceeds it | 🟠 | `rag-architect/SKILL.md` (canonical overlap and cap rule) |
| 1.5 | Stable chunk IDs: `(document_id, document_version, chunk_index)` — never auto-increment IDs | 🟠 | `advanced-chunking-guide.md §4` |
| 1.6 | Required metadata per chunk: `document_id`, `chunk_id`, `tenant_id`, `source_uri`, `section_title`, `page`, `chunk_index`, `embedding_model`, `chunker_version`, `parser_version`, `content_hash`, `created_at` | 🟠 | `advanced-chunking-guide.md §4` (16-field schema) |
| 1.7 | Tables NOT split mid-row; column headers repeated in every row-group chunk | 🔴 | `table-chunking-strategy.md §3` |
| 1.8 | High-stakes tables stored with multiple representations (plain text + Markdown + JSON) | 🟡 | `table-chunking-strategy.md §4` |
| 1.9 | OCR quality gate applied before ingestion: per-character confidence threshold checked, garbled text rejected | 🟡 | `advanced-chunking-guide.md §6` |
| 1.10 | Parent-child relationship stored when narrow questions need surrounding context | 🟡 | `advanced-chunking-guide.md §1.4` |
| 1.12 | Every source has a register entry (owner, classification, ACL source, `acl_sync_sla`, `deletion_sla`, `trust_level`, embedding profile); ingest refuses unregistered sources | 🟠 | `vector-database/references/rag-ingest-checklist.md` §S |
| 1.13 | Chunk envelope schema-validated at write time (`scope_id`, `acl`, `data_classification`, `trust_level`, `doc_version`, `is_current`, `language`, versions, `content_hash`); secrets removed before embedding | 🔴 | `rag-ingest-checklist.md` §I, §B |
| 1.14 | `user-generated` / `external-web` content cannot enter a shared corpus without review; instruction-like text flagged at ingestion; per-source context share capped | 🔴 | `rag-ingest-checklist.md` §P |

---

## Stage 2 — Versioning, Updates & Deletion

Cross-refs: `rag-architect/references/versioning-and-freshness.md`, `rag-architect/references/incremental-ingestion-guide.md`

| # | Check | Severity if failing | Reference |
|---|---|---|---|
| 2.1 | Two-level hash gate implemented: document hash (fast skip) AND chunk hash (exact diff) — NOT document hash alone | 🟠 | `incremental-ingestion-guide.md §1` |
| 2.2 | Text normalized before hashing (whitespace, page numbers, timestamps stripped) to prevent false re-embeds from formatting noise | 🟠 | `incremental-ingestion-guide.md §2` |
| 2.3 | Stable chunk IDs enable clean upsert — changed chunk updates in place, does not create duplicate vector | 🔴 | `incremental-ingestion-guide.md §3` |
| 2.4 | Soft-delete: removed chunks set `is_active=false`; retrieval filters `WHERE is_active = true` | 🔴 | `incremental-ingestion-guide.md §4` |
| 2.5 | Version fields stored per chunk: `embedding_model`, `chunker_version`, `parser_version`, `normalizer_version` | 🟠 | `incremental-ingestion-guide.md §5` |
| 2.6 | Versioning metadata: `effective_from`, `effective_to`, `superseded_at` — default retrieval filter `superseded_at IS NULL` | 🟠 | `versioning-and-freshness.md §2–3` |
| 2.7 | New document version supersession runs in a single atomic transaction (marks old superseded + inserts new together) | 🔴 | `versioning-and-freshness.md §5` |
| 2.8 | Historical query detection implemented — temporal keywords trigger `effective_from`/`effective_to` filter instead of current-only filter | 🟡 | `versioning-and-freshness.md §4` |
| 2.10 | Deletion meets the source `deletion_sla` and ends with a probe query that no longer retrieves the content; legal hold overrides deletion and is recorded; ACL revocation stops retrieval within `acl_sync_sla` (tested) | 🔴 | `versioning-and-freshness.md §8`, `rag-ingest-checklist.md` §E |
| 2.9 | Erasure/RTBF: tenant-scoped hard delete of all versions (vector + FTS + metadata + object store + caches + derived artifacts) plus a tombstone; supersession is never erasure; audit row keeps ids/counts only | 🔴 | `versioning-and-freshness.md §8` |

---

## Stage 3 — Embedding & Indexing

Cross-refs: `vector-database` skill, `vector-database/references/embedding-migration-guide.md`, `vector-database/references/ann-vs-knn.md`

| # | Check | Severity if failing | Reference |
|---|---|---|---|
| 3.1 | Embedding model pinned as a constant or env config — NEVER inline string literal at each call site | 🔴 | `vector-database/SKILL.md` |
| 3.2 | `embedding_model` version stored in chunk metadata AND every retrieval query filters on the active model | 🔴 | `advanced-chunking-guide.md §4` + `vector-database/SKILL.md` |
| 3.9 | Embedding chokepoint asserts `len(vector) == SCHEMA_DIMS`; query and document task modes match | 🔴 | `rag-implementation-reviewer` agent checklist |
| 3.10 | pgvector HNSW/IVFFlat column ≤ 2000 dims (else reduced dims or `halfvec` expression index) | 🔴 | `vector-database/SKILL.md` model table |
| 3.3 | Query and index use the SAME distance operator (`cosine <=>` matches `vector_cosine_ops` index) | 🔴 | `vector-database/references/ann-vs-knn.md` |
| 3.4 | ANN/HNSW used for production retrieval; KNN/Flat reserved for golden-set eval baseline and scoped high-risk paths | 🟠 | `vector-database/references/ann-vs-knn.md` Decision rule |
| 3.5 | `efSearch` / `nprobe` calibrated against KNN ground truth on golden set — never tuned by feel | 🟠 | `vector-database/references/ann-vs-knn.md` Tuning |
| 3.6 | Null guard: `WHERE embedding IS NOT NULL` (or equivalent) in retrieval query | 🟠 | `rag-implementation-reviewer` agent checklist |
| 3.7 | Batch embedding — NOT one API call per chunk in a loop | 🟡 | `rag-implementation-reviewer` agent checklist |
| 3.8 | Embedding model upgrade plan documented (dual-write or shadow index strategy before cutover) | 🟡 | `vector-database/references/embedding-migration-guide.md` |
| 3.11 | Vector store and embedding model chosen against recorded criteria (not a public leaderboard alone); one corpus is never dual-written to two stores as two sources of truth | 🟡 | `vector-database/references/tier-1-tier-2-decision.md` Step 0, `vector-database/SKILL.md` Embedding Model Selection |

---

## Stage 4 — Query Understanding & Routing

Cross-refs: `rag-architect/references/query-classification-taxonomy.md`, `rag-architect/references/query-transformation-guide.md`

| # | Check | Severity if failing | Reference |
|---|---|---|---|
| 4.1 | Query classification covers the 9 canonical intent classes (`factual_lookup`, `policy_question`, `structured_record_lookup`, `comparison`, `summarization`, `multi_hop`, `troubleshooting`, `personalized`, `unsafe`) | 🟠 | `query-classification-taxonomy.md §1` |
| 4.2 | Structured record lookups (exact IDs, counts, current account state) route to SQL/API — NOT RAG | 🔴 | `query-classification-taxonomy.md §4` |
| 4.3 | `unsafe_or_disallowed` class refuses before any retrieval takes place; attempt is audit-logged | 🔴 | `query-classification-taxonomy.md §1` |
| 4.4 | Router type matches corpus complexity: rule-based for v1 (< ~30 rules), classifier for more; LLM router only for agentic flows | 🟡 | `query-classification-taxonomy.md §3` |
| 4.5 | Conversational follow-up queries rewritten (pronouns resolved, standalone query) before retrieval | 🟠 | `query-transformation-guide.md §1` |
| 4.6 | HyDE NOT deployed on factual, legal, or contractual query types without A/B measured win on golden set | 🟠 | `query-transformation-guide.md §5` |
| 4.7 | Sub-index routing considered when a corpus segment exceeds ~100k documents | 🟡 | `query-classification-taxonomy.md §4` |

---

## Stage 5 — Retrieval, Fusion & Reranking

Cross-refs: `rag-architect/SKILL.md` (Default Stack), `rag-architect/references/rag-operations-guide.md`

| # | Check | Severity if failing | Reference |
|---|---|---|---|
| 5.1 | Hybrid retrieval: dense + BM25 — or documented measured justification for skipping sparse | 🟠 | `rag-architect/SKILL.md` Step 1 |
| 5.2 | Fusion via RRF (k=60) — NOT ad-hoc weighted score blending without normalization | 🟠 | `rag-architect/SKILL.md` Step 1 |
| 5.3 | Tenant/ACL filter inside the retrieval call — NEVER post-filter on top-k results | 🔴 | `rag-security-reviewer/SKILL.md §1` |
| 5.3a | Filtered-ANN recall: pgvector selective filters covered by iterative scan (≥ 0.8), partial index (bound tenant → `plan_cache_mode = force_custom_plan`), partition or exact scan; ≤ 1%-selective fixture asserts `count == LIMIT` over > 5 calls on one connection | 🟠 | `vector-database/references/ann-vs-knn.md` §Filtered ANN |
| 5.4 | `top_k_retrieve` >> `top_k_final`: retrieve 50–80 candidates, rerank down to 5–10 for generation | 🟠 | `rag-operations-guide.md §6` |
| 5.5 | Cross-encoder reranker on production paths, or an eval result justifying its absence; reranks against the ORIGINAL user query | 🟠 | `rag-architect/SKILL.md` Step 1 |
| 5.6 | Environment-aware reranker: local/dev may use a lighter reranker; staging/prod uses the production reranker that the eval gate measured | 🟡 | `rag-operations-guide.md §5` |
| 5.7 | Retrieval and answer cache keys include tenant, permission fingerprint and index version (query-*embedding* cache may be tenant-independent: key = query + model + dims + task type) | 🔴 | `rag-operations-guide.md §1` (canonical) |
| 5.9 | Weaviate `hybrid()` on self-provided vectors passes `vector=`; golden paraphrase case with zero keyword overlap hits | 🔴 | `weaviate-schema-reviewer` agent |
| 5.10 | Every derived query (rewrite, expansion, HyDE, sub-query, hop) uses the same scoped retrieval entry; fan-out capped in code; one deadline | 🔴 | `query-transformation-guide.md §5` |
| 5.11 | Keyword fallback on embed failure is logged and flagged to the generator — never silent | 🟠 | `rag-implementation-reviewer` agent checklist |
| 5.12 | Fan-out budgets enforced in code (defaults ≤ 6 sub-queries, ≤ 60 rerank candidates, ≤ 6 rerank calls, hard timeout); breach returns `PARTIAL` with a visible note | 🟠 | `rag-architect/SKILL.md` Requirement homes and ADAPT defaults |
| 5.13 | Semantic (similarity-keyed) answer cache not used for personalized, high-stakes or ACL-varying answers; caches purged on delete and ACL change within SLA | 🔴 | `rag-operations-guide.md §1` |
| 5.14 | Cross-scope negative tests cover results, snippets, counts/facets, nearest neighbours, rerank inputs and caches | 🔴 | `rag-security-reviewer` Multi-tenancy security checklist |
| 5.8 | MMR or diversity filter applied during context packing to prevent near-duplicate chunks in final context | 🟡 | `context-packing-patterns.md §1` |

---

## Stage 6 — Generation Contract & Abstention

Cross-refs: `rag-architect/references/context-packing-patterns.md`, `rag-architect/references/abstention-decision-framework.md`, `rag-architect/references/rag-response-contract.md`

| # | Check | Severity if failing | Reference |
|---|---|---|---|
| 6.1 | Strict grounding prompt: "answer ONLY using the provided context" — no room for LLM to draw on training data | 🟠 | `context-packing-patterns.md §3` |
| 6.2 | Structured answer contract returned (not free-form prose with embedded citations the system can't parse) | 🟠 | `rag-response-contract.md §1` |
| 6.3 | Per-claim citations — every factual sentence in the answer carries a `[chunk_id]` reference | 🟠 | `context-packing-patterns.md §3` |
| 6.3a | Runtime citation validation: cited ids ⊂ retrieved ids else abstain; support check below threshold → abstain; checker unavailable → `verified=false` | 🔴 | `rag-response-contract.md §10` |
| 6.4 | `schema_version` emitted on every response | 🟠 | `rag-response-contract.md §8` |
| 6.5 | `status` field is a value from the closed 10-value enum: the six answer outcomes (`ANSWERED`/`PARTIAL`/`NOT_FOUND`/`CONFLICTED`/`STALE`/`HUMAN_REVIEW`) plus `CLARIFICATION_NEEDED`/`TOOL_ERROR`/`POLICY_BLOCKED`/`NO_RETRIEVAL`; conflicting sources return `CONFLICTED`, never a silently chosen side | 🔴 | `rag-response-contract.md §3` |
| 6.6 | `NO_RETRIEVAL` status is explicitly policy-governed — NOT used as a silent fallback that bypasses RAG | 🔴 | `rag-response-contract.md §3` |
| 6.7 | `confidence_level` is a band (`high`/`medium`/`low`) — NEVER raw float exposed to UI | 🟠 | `rag-response-contract.md §4` |
| 6.8 | Confidence derived from evidence signals (retrieval score, rerank score, citation coverage, freshness), NOT from LLM self-report | 🟠 | `rag-response-contract.md §4` |
| 6.9 | Faithfulness gate implemented: if faithfulness < threshold (~0.7), band clamped to `low` regardless of weighted score | 🟠 | `rag-response-contract.md §4` |
| 6.10 | `safety` block emitted on every response — missing block ≠ empty `{}` | 🔴 | `rag-response-contract.md §6` |
| 6.11 | `answer_spans` character offsets use UTF-16 code units; encoding documented in `schema_version` notes | 🟠 | `rag-response-contract.md §5` |
| 6.12 | `evidence_type` enum (`direct`/`inferred`/`contextual`) present on every citation | 🟡 | `rag-response-contract.md §5` |
| 6.13 | Internal-only fields (`relevance_score`, `retrieval_metadata`, `trace`, `usage`, raw `chunk_id`) stripped before response reaches client | 🟠 | `rag-response-contract.md §2` |
| 6.14 | Abstention enforced at agent/pipeline layer via calibrated threshold checks — NOT relying solely on LLM prompt instruction | 🔴 | `abstention-decision-framework.md §3` |
| 6.15 | All 8 abstention triggers handled: no context, off-topic retrieval, missing clause, conflicting docs, citation unsupported, stale evidence, high-risk domain without grounding, required doc not retrieved | 🟠 | `abstention-decision-framework.md §3` |
| 6.16 | Refusal text uses one of the 4 named templates (missing context / weak context / conflicting context / high-risk) — NOT free LLM improvisation | 🟡 | `abstention-decision-framework.md §6` |
| 6.17 | `clarification_reason` field REQUIRED when `status = clarification_needed` | 🟠 | `rag-response-contract.md §3` |
| 6.18 | Streaming uses 6-event model (`status`/`answer_delta`/`citation`/`warning_flag`/`answer_span`/`done`); `answer_span` emitted only after generation is complete, NOT mid-stream | 🟠 | `rag-response-contract.md §7` |
| 6.19 | Context budget computed per model (`model_window − system_prompt − tools − history − output_reserve`), never filled to the limit; whole-chunk truncation with dropped chunks recorded; canonical facts in a separate labelled block; no other user's history re-injected | 🟠 | `context-packing-patterns.md §0` |

---

## Stage 7 — Security

**This stage delegates to `rag-security-reviewer/SKILL.md` — do NOT duplicate it here.** Load that skill in parallel when reviewing security-sensitive RAG code. The five items below are the minimum gate; the dedicated skill has full coverage.

| # | Minimum gate (full coverage in rag-security-reviewer) | Severity | Reference |
|---|---|---|---|
| 7.1 | Filter inside the retrieval call at a SINGLE chokepoint, tenant/permissions from the verified auth context — NEVER post-filter on top-k | 🔴 | `rag-security-reviewer/SKILL.md §1–2` |
| 7.2 | Retrieved content treated as untrusted: clear delimiters in prompt, no tool-call execution allowed from retrieved text | 🔴 | `rag-security-reviewer/SKILL.md §3` |
| 7.3 | Per-response audit log: `request_id`, `user_id`, `tenant_id`, query hash (not raw text), `filters_applied`, `chunks_used`, `model`, `prompt_version`, `latency_ms` | 🔴 | `rag-security-reviewer/SKILL.md §4` |
| 7.4 | PII redaction at ingest AND at response (`safety.redactions[]`) | 🔴 | `rag-security-reviewer/SKILL.md §5` + `rag-response-contract.md §6` |
| 7.5 | Right-to-be-forgotten tested end-to-end: vector index + BM25 index + metadata + object store + all caches + tombstone; audit row keeps ids/counts only | 🔴 | `rag-security-reviewer/SKILL.md` Deletion + `versioning-and-freshness.md §8` |

If ANY 🔴 item in Stage 7 fails, the review verdict is **BLOCK** regardless of other stages.

---

## Stage 8 — Evaluation & Observability

Cross-refs: `rag-evaluator/SKILL.md`, `rag-architect/references/rag-operations-guide.md`

| # | Check | Severity if failing | Reference |
|---|---|---|---|
| 8.1 | Golden set exists with ≥ 50 labeled queries — or has a concrete plan with date | 🔴 | `rag-evaluator/SKILL.md` Golden set design |
| 8.2 | Coverage targets met: ~60% happy path, ~20% edge cases, ~20% known unanswerable | 🟠 | `rag-evaluator/SKILL.md` Coverage targets |
| 8.3 | CI gate configured: fails build on Recall@K, Faithfulness, or Citation Quality regression beyond tolerance; thresholds name the metric exactly (Recall@K = relevant retrieved ÷ all relevant; Hit@K = any relevant in top K — not interchangeable; formulas: `llm-evaluation` skill, canonical) | 🔴 | `rag-evaluator/SKILL.md` CI gate pattern |
| 8.4 | Abstention metrics tracked as two separate rates — False Abstention Rate + False Answer Rate — NOT collapsed into one metric | 🟠 | `rag-evaluator/SKILL.md` Answer metrics |
| 8.5 | Eval breakdown by dimension when corpus grows: doc type, recency, query style, query length, corpus segment | 🟡 | `rag-evaluator/SKILL.md` Eval Breakdown by Dimension |
| 8.6 | LLM-as-judge calibrated against human labels (≥ 80% agreement) before use at scale | 🟠 | `rag-evaluator/SKILL.md` LLM-as-judge dangers |
| 8.7 | All 5 production dashboards wired: Health (p95 latency), Quality (faithfulness, abstention rate), Cost (per-query cost, cache hit rate), Ingestion (queue depth, failed ingestions), Security (cross-tenant attempts, audit log gaps) | 🟠 | `rag-operations-guide.md §3` |
| 8.8 | Async eval pattern: sample 1–10% of production traffic via trace store — NOT inline in sync response path | 🟡 | `rag-response-contract.md §1` |
| 8.9 | Corpus hygiene checks run after bulk ingestion: near-duplicate detection (`content_hash` dedup), stale/superseded doc sweep, authority tagging for canonical versions | 🟡 | `rag-operations-guide.md §9` |
| 8.10 | Post-ingestion smoke test runs after every ingestion that changed ≥ 1 chunk; ingestion trace logged | 🟡 | `incremental-ingestion-guide.md §7` |
| 8.12 | Recall, faithfulness and isolation-leak count reported per tenant and per query-type slice; the PR gate blocks on any isolation leak | 🔴 | `rag-evaluator/SKILL.md` |
| 8.13 | Trace records the required fields (routing decision, filter names not values, index + embedding model + chunking version, candidate and final chunk ids with scores, rerank model, groundedness, citation validity, outcome, per-stage latency and cost); an isolation violation pages immediately | 🟠 | `rag-operations-guide.md` §3 Trace |
| 8.11 | p95 latency target defined and monitored per stage: query embedding ≤ 50ms, ANN retrieval ≤ 200ms, reranker ≤ 250ms, LLM first token ≤ 500ms, total ≤ 2s | 🟡 | `rag-operations-guide.md §4` |

---

## Anti-patterns (each one found is a finding)

| Anti-pattern | Stage check |
|---|---|
| Post-filtering retrieval results by ACL instead of pre-filtering the index | 5.3, 7.1 |
| Taking the tenant/scope filter from client input or model output | 7.1 |
| Using RAG for facts that live in a system of record | 4.2 |
| Fine-tuning on customer data that may need to be deleted or access-controlled | 4.2 (`rag-architect` Step 0) |
| Splitting tables or clauses by raw token count | 1.2, 1.7 |
| Mixing vectors from different embedding models or dimensions in one search | 3.2 |
| Re-embedding in place during serving; switching embedding models without a shadow index and eval gate | 3.8 |
| Dual-writing the same content to two stores as two sources of truth | 3.11 |
| Pure-vector retrieval for identifier-heavy queries; one global hybrid weight for every query type | 5.1, 5.2 |
| Choosing an embedding model or vector store from a public leaderboard alone | 3.11 |
| HyDE or multi-query on high-stakes questions; unbounded query fan-out | 4.6, 5.10, 5.12 |
| Stuffing the context window to the limit "for safety" | 6.19 |
| Trusting a prompt instruction as the only grounding control; no citation validation | 6.3a, 6.14 |
| Forcing an answer when evidence is missing or conflicting instead of `NOT_FOUND` / `CONFLICTED` | 6.5, 6.15 |
| Cache keys without scope and ACL; semantic answer caches on personalized answers | 5.7, 5.13 |
| Deleting the source but not chunks, vectors, derived summaries, caches and eval copies | 2.9, 7.5 |
| Letting user-generated or external content into a shared corpus without review | 1.14 |
| Reporting one aggregate metric and missing per-slice and per-tenant regressions | 8.12 |
| Logging raw chunk text or raw queries containing PII in traces | 8.13 |

## Adoption checklist

**Technical (evidence = file:line, test output or eval report; an item with no evidence is a finding, not a pass):**

- [ ] Source register filled for every corpus (1.12); ingestion sanitizes at the storage boundary, secrets never embedded, idempotency mechanism chosen and tested (1.13, 2.3)
- [ ] Chunking strategy chosen per content type, versioned, validated on the golden set (1.2–1.5)
- [ ] Embedding model/version/dimension pinned, env-invariant, stamped per chunk; queries filter on it (3.1–3.2); blue/green re-index runbook written and full re-embed cost estimated (3.8)
- [ ] Chunk envelope enforced at write time, schema-validated (1.13)
- [ ] Vector store choice recorded against the selection criteria; ANN recall measured against exact KNN (3.4–3.5, 3.11)
- [ ] Multi-tenancy pattern chosen; cross-scope negatives cover results, snippets, counts, neighbours, rerank inputs and caches (5.3, 5.14)
- [ ] Authorization pre-filter applied from server-side context on every retrieval (7.1)
- [ ] Hybrid retrieval + fusion + reranker in place; fan-out budgets enforced (5.1–5.5, 5.12)
- [ ] Context budget computed per model; retrieved text delimited as data (6.19, 7.2)
- [ ] Citation validation + grounding check + outcome enum implemented; degraded path labelled (6.3a, 6.5, 6.9)
- [ ] Versioning, freshness SLO and deletion propagation implemented and tested end to end (2.6–2.10)
- [ ] Caches keyed by scope + ACL + versions; purged on delete and ACL change (5.7, 5.13)
- [ ] Injection and poisoning controls in place; red-team suite covers untrusted corpora (1.14, 7.2)
- [ ] Golden sets per query type; PR, re-index and pre-launch gates wired (8.1–8.3, 8.12)
- [ ] Traces carry the required fields; isolation-violation alert pages on any non-zero (8.13)
- [ ] Cost per answered query tracked by outcome and by tenant (8.7, `rag-operations-guide.md` §2)

**Organisation-owned (recorded decisions and named people; no tool enforces these):**

- [ ] Capability ADR records why RAG and the rejected alternatives (`ai-decision-record`)
- [ ] Named owner per corpus, accountable for content and access; `approved_use`, `data_classification`, `pii_policy`, retention and legal-hold rules set by the data owner with Privacy/Legal where policy requires
- [ ] ADAPT values ratified and recorded per corpus: `acl_sync_sla`, `deletion_sla`, freshness SLO, `isolation_boundary`, grounding thresholds, eval gate thresholds, fan-out budgets (`rag-architect/references/rag-operations-guide.md` §6)
- [ ] Architecture review approves any new vector store (G13); embedding provider and region approved for the corpus classification (G9, G20)
- [ ] Re-index / model-change approval includes the full re-embed cost and wall-clock estimate
- [ ] Red-team cadence agreed for every corpus below `trusted-internal`

## Verdict format

Output verdict as the **final line** of the review report:

```
VERDICT: [APPROVE | NEEDS_REVIEW | BLOCK] — CRITICAL: N | HIGH: N | MEDIUM: N | LOW: N
```

Rules:
- **BLOCK** — any 🔴 Critical finding. Must fix before merge.
- **NEEDS_REVIEW** — zero Critical, but ≥ 1 High or pattern of Medium. Recommend fix.
- **APPROVE** — zero Critical, zero High, ≤ 3 Medium. Ship with notes on Lows.

Every finding carries severity, evidence (`file:line` + quoted code) and a remediation. Do not claim a test, eval or runtime check passed unless you executed it in this session and show the command and its output; otherwise mark it NOT RUN.

---

## When NOT to use this skill

| Situation | Use instead |
|---|---|
| Pure security review only | `rag-security-reviewer/SKILL.md` directly (more depth) |
| Designing a NEW RAG pipeline | `rag-architect/SKILL.md` |
| Diagnosing one failed production query | `rag-debugger/SKILL.md` 9-layer chain via `/rag-debug` |
| Running the eval suite to detect regressions | Dispatch `@rag-eval-runner` agent |
| Debugging why corpus-scale accuracy dropped | `rag-evaluator/SKILL.md` Eval Breakdown by Dimension |

---

## References table

| Stage | Authoritative references |
|---|---|
| 1 — Ingestion & chunking | `rag-architect/references/advanced-chunking-guide.md`, `rag-architect/references/table-chunking-strategy.md` |
| 2 — Versioning / updates / deletion | `rag-architect/references/versioning-and-freshness.md`, `rag-architect/references/incremental-ingestion-guide.md` |
| 3 — Embedding & indexing | `vector-database/SKILL.md`, `vector-database/references/ann-vs-knn.md`, `vector-database/references/embedding-migration-guide.md` |
| 4 — Query understanding & routing | `rag-architect/references/query-classification-taxonomy.md`, `rag-architect/references/query-transformation-guide.md` |
| 5 — Retrieval, fusion & reranking | `rag-architect/SKILL.md` (Default Stack), `rag-architect/references/rag-operations-guide.md` |
| 6 — Generation contract & abstention | `rag-architect/references/context-packing-patterns.md`, `rag-architect/references/abstention-decision-framework.md`, `rag-architect/references/rag-response-contract.md` |
| 7 — Security | `rag-security-reviewer/SKILL.md` (dedicated) |
| 8 — Eval & observability | `rag-evaluator/SKILL.md`, `rag-architect/references/rag-operations-guide.md` |

---

## Maintenance note

When a new reference file is added to any sibling skill (`rag-architect`, `rag-evaluator`, `rag-security-reviewer`, `vector-database`, `rag-debugger`), update the corresponding stage table here in the same PR. The skill is the single point of update; the consuming agent (`rag-implementation-reviewer`) and command (`/rag-review`) inherit automatically via `skills:` frontmatter.

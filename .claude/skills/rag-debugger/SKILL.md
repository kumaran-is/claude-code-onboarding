---
name: rag-debugger
description: Use when a RAG system is returning bad answers — hallucinations, wrong content, missing exact terms, low recall, slow responses, stale data, citation errors, tenant data leakage, or any production retrieval failure. Walks the 9-layer diagnostic chain backward from output to root cause. Triggers on phrases like "RAG returning wrong answers", "hallucinating", "can't find document", "wrong tenant data", "low recall", "RAG is slow", "missing citations".
---

# RAG Failure Diagnosis

When a RAG answer is wrong, **walk the layers backward** from output to root cause. Most "the LLM hallucinated" reports are actually upstream failures that surface at generation.

**Critical principle:** don't fix downstream when upstream is broken. Tuning the reranker won't help if the parser dropped the table.

## The diagnostic chain

For any wrong answer, walk in this order. **The first layer where you find a problem is your root cause** — stop walking there.

```
Wrong answer
  │
  ├─ Layer 9: LLM generation
  │     Did the LLM ignore evidence it had?
  │     check: was the correct chunk in the context window?
  │
  ├─ Layer 8: Context packing
  │     Did the right chunk reach the LLM?
  │     check: was it retrieved but dropped before packing?
  │
  ├─ Layer 7: Reranker
  │     Did rerank bury the right chunk?
  │     check: was the right chunk in pre-rerank candidates but not top-k?
  │
  ├─ Layer 6: Fusion (RRF)
  │     Did fusion lose a strong single-retriever hit?
  │     check: was it top-3 in BM25 or dense alone but buried after RRF?
  │
  ├─ Layer 5: Retrieval (dense)
  │     Did dense find the right chunk?
  │     check: similarity score; close to top hits?
  │
  ├─ Layer 4: Retrieval (sparse / BM25)
  │     Did BM25 find the right chunk?
  │     check: does the chunk contain query terms? Stop-words eating query?
  │
  ├─ Layer 3: Filtering
  │     Did filters wrongly exclude the right chunk?
  │     check: replay query without filters; does it appear?
  │
  ├─ Layer 2: Chunking
  │     Was the answer split across chunk boundaries?
  │     check: does the answer text exist in any single chunk?
  │
  └─ Layer 1: Parsing / Ingestion
        Was the source content captured at all?
        check: does the raw document contain the answer?
```

## Failure modes by layer

| Layer | Symptom | Likely cause | Fix direction |
|---|---|---|---|
| 1 Parsing | Answer not in any chunk; raw doc has it | Parser dropped table, lost footer, OCR failed | Better parser (Unstructured.io / LlamaParse), OCR quality gates, chunk quality scoring |
| 1 Ingestion | Document not indexed | Failed job, deletion bug, tombstone | Audit ingestion logs, idempotency check |
| 2 Chunking | Condition separated from rule | Fixed-size split mid-statement | Document-aware chunking, parent-child, overlap |
| 2 Chunking | Table broken across chunks | Naive splitter cut the table | Adaptive chunking, preserve tables whole |
| 3 Filtering | Right chunk filtered out | Metadata mismatch, tenant filter too aggressive, version filter | Audit filter logic; check effective_to / version |
| 3 Filtering | Post-filter killed recall | Top-k all filtered after retrieval in app code | Move the filter into the retrieval call (`rag-security-reviewer` §1) |
| 3 Filtering | Small tenant gets 0–few results on pgvector | `WHERE` runs after the HNSW/IVFFlat candidate list (`ef_search` 40) | Iterative scan (pgvector ≥ 0.8), partial index, partition, or exact scan; compare with `SET LOCAL enable_indexscan = off`. Works for 5 calls then returns 0 again → generic-plan trap: a partial index on a bound parameter (`tenant_id = $2`) needs `SET LOCAL plan_cache_mode = force_custom_plan`, or it silently stops being used after 5 prepared executions |
| 3 Filtering | Results mix old and new model | No `embedding_model = active` filter during re-embed | Add the active-model filter |
| 4 Sparse | Exact term not matched | Tokenizer issue, stop-words too aggressive | Check tokenization; rebuild with correct analyzer |
| 5 Dense | Paraphrase not matched | Domain-weak embedder, chunk size wrong, query/document task mode mismatch | Test domain embedder; adjust chunk size; check task type / prefixes |
| 5 Dense | Hybrid behaves like keyword search | Weaviate `hybrid()` on self-provided vectors called without `vector=` | Pass the query embedding |
| 5 Dense | Proper noun missed | Model never saw the proper noun | Hybrid (BM25 catches it) |
| 6 Fusion | Strong hit buried | One retriever had 1 great hit, other had 50 mediocre | Inspect rank-by-rank; consider weighted RRF |
| 7 Reranker | Wrong chunk preferred | Reranker mismatched to domain | Try different reranker; eval on labeled pairs |
| 7 Reranker | Length bias | Long irrelevant beat short relevant | Length normalization; switch reranker |
| 7 Reranker | Answer in chunk tail never ranks | Chunk longer than reranker input limit; tail truncated | Cap chunks at reranker limit minus query length |
| 8 Packing | Right chunk dropped | Aggressive top-k, dedup removed unique answer | Loosen top-k; smarter dedup |
| 8 Packing | Lost in the middle | Right chunk at end of long context | Move highest-scored first |
| 9 Generation | LLM ignored evidence | Weak grounding prompt; model priors | Strict grounding; structured output; abstention threshold |
| 9 Generation | Hallucinated citation | Citation present, chunk doesn't support claim — or cites an id never retrieved | Runtime citation validation (`rag-architect/references/rag-response-contract.md` §10) |

## Common failure patterns (signature → layer)

| Pattern | Signature | Likely layer |
|---|---|---|
| Plausible but wrong | Coherent answer, no citation matches | 9 or 8 |
| "I don't know" when answer exists | Right chunk never retrieved | 4–6 |
| Outdated answer | Newer version exists, old retrieved | 3 (version filter) or 5 (no freshness signal) |
| Wrong tenant data | Info from another customer | 3 — **security incident, page someone** |
| Repeated / redundant | Same content cited multiple times | 8 (no dedup) |
| Right facts, wrong combination | Each fact cited, combination invented | 9 or 2 (lost connector across chunks) |

## How to apply

When the user reports a RAG failure:

1. **Get the trace.** Ask for: query, classification (if any), filters applied, all retriever outputs with scores, RRF result, rerank result, context sent to LLM, LLM response. If they don't have this — that's the first problem to fix (audit logs per §39.2).

2. **Check Layer 1 first.** Does the answer exist in any chunk? If no, stop. Nothing downstream matters. Recommend parser / ingestion fixes.

3. **Walk forward layer by layer.** At each layer, ask: was the right chunk present? The first layer where it disappears is the root cause.

4. **Match against common patterns** — they short-circuit the walk.

5. **For tenant data leakage: page immediately.** Pre-filter chokepoint is broken; this is a security incident, not a quality issue.

## Anti-patterns to watch for

- "It's just hallucinating, raise the temperature lower" → almost never the answer; check upstream first
- "Add more chunks to context" → if retrieval is wrong, more wrong chunks won't help
- "Try a bigger model" → bigger model with same broken retrieval is still broken
- "Tune the reranker" before checking that the right chunk is in the candidate pool

Reference: full playbook §40 (failure taxonomy), §39.2 (audit log schema).

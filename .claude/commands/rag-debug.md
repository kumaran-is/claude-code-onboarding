---
description: Walk the 9-layer RAG failure diagnostic chain against a specific failing query
argument-hint: "[symptom or query]"
---

# /rag-debug — Diagnose RAG Failure

Diagnose a specific RAG failure by walking the 9-layer diagnostic chain (playbook §40).

**Symptom or failing query:** $ARGUMENTS

## Phase 1: Get the trace

Ask the user for the full trace of the failing query. You need:

- The exact query as the user typed it
- Filters applied (tenant, ACL, version, date range)
- All retriever outputs with scores (dense top-N, sparse top-N)
- RRF fused result
- Reranker output (pre and post)
- Final context packed into the LLM prompt
- The LLM's response
- What the *correct* answer should have been, and which document(s) should have produced it

If the user can't produce this — that's already a finding: they don't have audit logs (§39.2). Recommend that first. Then ask what they CAN reproduce manually.

## Phase 2: Walk the chain

Walk these layers IN ORDER. The first layer where the right chunk goes missing is the root cause. Do not skip ahead.

### Layer 1: Parsing / Ingestion
**Question:** Does the answer text exist in ANY chunk in the index?

Action: search the index directly (BM25 or substring) for distinctive phrases from the expected answer. If you can't find it, the problem is parsing or ingestion.

- ❌ Not in any chunk → **stop here**. Root cause is Layer 1. Recommend parser audit (§6.1), OCR check, chunk quality scoring (§9.11).
- ✅ Found in a chunk → continue to Layer 2.

### Layer 2: Chunking
**Question:** Is the full answer in a SINGLE chunk, or split across chunks?

- ❌ Split across chunks (e.g., the condition is in one chunk, the rule in another) → **stop here**. Root cause is chunking. Recommend document-aware + parent-child (§9.4), overlap, or recursive retrieval (§9.12).
- ✅ Single chunk → continue to Layer 3.

### Layer 3: Filtering
**Question:** Did filters wrongly exclude the right chunk?

Action: replay the query WITHOUT filters. Does the right chunk appear?

- ❌ Right chunk only appears without filters → **stop here**. Root cause is filtering. Check tenant filter (should not exclude), version filter (`effective_to`), access_level mismatch.
- Special case: post-filter on top-k → critical fix (§20.2)
- Special case: right chunk appears with an exact scan but not with the ANN index under the same filter (pgvector `SET LOCAL enable_indexscan = off` to compare) → filter-after-index recall loss, not a filter bug; see `vector-database/references/ann-vs-knn.md` §Filtered ANN
- ✅ Right chunk found with filters → continue to Layer 4.

### Layer 4: Sparse retrieval (BM25)
**Question:** Did BM25 find the right chunk?

Action: look at BM25 top-50 for this query. Is the right chunk there?

- ❌ Not in BM25 results → check tokenization (stop-words, stemming, analyzer mismatch), check that the chunk contains query terms literally
- ✅ Found in BM25 (and at what rank?) → note rank, continue to Layer 5.

### Layer 5: Dense retrieval
**Question:** Did dense find the right chunk?

Action: look at dense top-50 for this query. Is the right chunk there?

- ❌ Not in dense results → embedding model is weak on this domain or query style; chunk size may be wrong; consider domain-specific embedder or note that BM25 should carry this query type
- ✅ Found in dense (rank?) → continue to Layer 6.

### Layer 6: Fusion (RRF)
**Question:** Did RRF preserve the strong single-retriever hit?

If the chunk was top-3 in either dense or BM25 alone, but is buried after RRF, fusion is hurting.

- ❌ Strong hit buried by RRF → check if one retriever returned 1 great hit while the other returned 50 mediocre hits (broader retriever wins). Consider weighted RRF or per-class fusion strategy.
- ✅ Survived fusion → continue to Layer 7.

### Layer 7: Reranker
**Question:** Did the reranker preserve the right chunk in top-k?

- ❌ In pre-rerank top-50 but not post-rerank top-10 → reranker is mismatched to domain. Try a different reranker; evaluate on labeled query/chunk pairs. Check for length bias (long irrelevant chunks beating short relevant ones).
- ✅ Survived reranking → continue to Layer 8.

### Layer 8: Context packing
**Question:** Did the right chunk reach the LLM in the context window?

- ❌ Top-10 had it, but final context didn't → top-k too aggressive, dedup removed unique answer, or context budget cut it off. Increase top-k passed to LLM; check dedup logic.
- ⚠️ Right chunk present but at the end of long context → "lost in the middle" effect. Move highest-scored chunks first.
- ✅ Right chunk reached LLM → continue to Layer 9.

### Layer 9: LLM generation
**Question:** Did the LLM ignore evidence it had?

If you've reached here, the right chunk WAS in the LLM's context but the LLM didn't use it.

- Cause: weak grounding prompt, model defaulting to priors, or distracting content elsewhere in context
- Fix: strict grounding prompt ("answer ONLY from the documents below"), structured output (§32.1), abstention threshold when reranker top-1 is below cutoff
- If citation is present but doesn't match the claim → citation quality issue (§35.2), implement per-claim checking

## Phase 3: Report

Produce a finding in this format:

```markdown
# RAG Debug Report

**Query:** {{query}}
**Symptom:** {{user's report}}
**Expected:** {{what should have happened}}

## Root cause

**Layer {{N}}: {{layer name}}**

{{Specific evidence — at this layer, the right chunk was/wasn't present, with scores/ranks}}

## Why this happens

{{Explanation referring to the playbook section}}

## Fix

{{Concrete, code-level if possible}}

## Verification

After applying the fix, re-run this query and confirm:
- {{Specific check 1}}
- {{Specific check 2}}

## Watch for

{{Other queries likely affected by the same root cause}}

## Playbook reference

§40.{{x}}, §{{related section}}
```

## Phase 4: Pattern recognition

If this failure matches a common pattern (§40.4):

- "Plausible but wrong" → Layer 9 or 8
- "I don't know" when answer exists → Layers 4–6
- "Outdated answer" → Layer 3 or 5
- "Wrong tenant data" → **Layer 3, security incident, page someone**
- "Right facts, wrong combination" → Layer 9 or Layer 2

Flag the pattern explicitly in the report.

## Anti-patterns to NOT recommend

Don't suggest these as fixes:

- "Just raise the temperature lower" → not the root cause
- "Add more chunks to the context" → if retrieval is wrong, more wrong chunks won't help
- "Try a bigger model" → bigger model with broken retrieval is still broken
- "Tune the reranker" before checking that the right chunk is in the candidate pool

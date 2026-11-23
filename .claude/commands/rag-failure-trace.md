---
description: Capture a full RAG audit trace for a query — useful for debugging or seeding a regression test
argument-hint: "[query]"
allowed-tools: Read, Write, Glob, Grep, Bash
---

# /rag-failure-trace — Capture Full RAG Audit Trace

Capture a complete audit trace for a query, conforming to the playbook §39.2 audit schema. Useful for debugging a specific failure, adding to the golden set, or demonstrating ACL enforcement.

**Query:** $ARGUMENTS

## Phase 1: Identify the pipeline

Find the user's RAG pipeline entry point. Ask if unclear:
- Path to the main RAG handler / endpoint
- How to invoke it locally (CLI, test, script)
- Whether they want to invoke against dev / staging / prod data

## Phase 2: Run the query with instrumentation

If the pipeline already emits audit logs (§39.2), grab the latest. Otherwise, add temporary instrumentation:

```python
# Temporary tracing wrapper — for trace capture only, not for production
import json
import time
import uuid
from datetime import datetime, timezone


def trace_rag_call(rag_pipeline, query: str, user_context: dict) -> dict:
    trace = {
        "response_id": f"trace-{uuid.uuid4()}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "user_id": user_context.get("user_id"),
        "tenant_id": user_context.get("tenant_id"),
        "stages": {},
    }

    # Stage 1: query understanding & classification
    t0 = time.perf_counter()
    classified = rag_pipeline.classify(query)
    trace["stages"]["classification"] = {
        "result": classified,
        "latency_ms": (time.perf_counter() - t0) * 1000,
    }

    # Stage 2: filters
    filters = rag_pipeline.build_filters(user_context, classified)
    trace["stages"]["filters_applied"] = filters

    # Stage 3: retrieval
    t0 = time.perf_counter()
    dense_results = rag_pipeline.dense_retrieve(query, filters=filters, top_k=50)
    sparse_results = rag_pipeline.sparse_retrieve(query, filters=filters, top_k=50)
    trace["stages"]["retrieval"] = {
        "dense_top10": [{"chunk_id": c.id, "score": c.score} for c in dense_results[:10]],
        "sparse_top10": [{"chunk_id": c.id, "score": c.score} for c in sparse_results[:10]],
        "latency_ms": (time.perf_counter() - t0) * 1000,
    }

    # Stage 4: fusion
    fused = rag_pipeline.rrf_fuse([dense_results, sparse_results])
    trace["stages"]["fusion"] = {
        "method": "RRF(k=60)",
        "top10_after_fusion": [{"chunk_id": c.id, "rrf_score": c.rrf_score} for c in fused[:10]],
    }

    # Stage 5: rerank
    t0 = time.perf_counter()
    reranked = rag_pipeline.rerank(query, fused[:100])
    trace["stages"]["rerank"] = {
        "top10_after_rerank": [{"chunk_id": c.id, "rerank_score": c.rerank_score} for c in reranked[:10]],
        "latency_ms": (time.perf_counter() - t0) * 1000,
    }

    # Stage 6: abstention check
    top1_score = reranked[0].rerank_score if reranked else 0
    abstention_threshold = rag_pipeline.abstention_threshold
    abstained = top1_score < abstention_threshold
    trace["stages"]["abstention"] = {
        "top1_score": top1_score,
        "threshold": abstention_threshold,
        "abstained": abstained,
    }

    if abstained:
        trace["final_response"] = "I don't have enough information to answer that."
        trace["abstained"] = True
        return trace

    # Stage 7: context packing
    packed = rag_pipeline.pack_context(reranked[:5])
    trace["stages"]["context_packing"] = {
        "chunks_packed": [{"chunk_id": c.id, "document_id": c.document_id, "version": c.version} for c in packed],
        "total_tokens": rag_pipeline.count_tokens(packed),
    }

    # Stage 8: generation
    t0 = time.perf_counter()
    response = rag_pipeline.generate(query, packed)
    trace["stages"]["generation"] = {
        "model": rag_pipeline.model_name,
        "prompt_template_version": rag_pipeline.prompt_version,
        "latency_ms": (time.perf_counter() - t0) * 1000,
    }

    trace["final_response"] = response.answer
    trace["citations"] = response.citations
    trace["abstained"] = False

    return trace


# Save the trace
trace = trace_rag_call(my_rag_pipeline, "$ARGUMENTS", user_context={...})
with open(f"traces/{trace['response_id']}.json", "w") as f:
    json.dump(trace, f, indent=2)
```

If the user prefers, walk them through running this manually and pasting the output back.

## Phase 3: Output the trace

Save to `traces/trace-{uuid}.json` and also produce a human-readable summary:

```markdown
# RAG Trace: {{query}}

**Trace ID:** {{trace_id}}
**When:** {{timestamp}}
**Final answer:** {{abbreviated answer or "[ABSTAINED]"}}

## Stage-by-stage

### 1. Classification
- Detected intent: {{intent}}
- Classification confidence: {{score}}

### 2. Filters
{{filter dict}}

### 3. Retrieval
- Dense top-3: {{ids and scores}}
- Sparse top-3: {{ids and scores}}
- Latency: {{ms}}

### 4. Fusion (RRF k=60)
- Top-3 after fusion: {{ids and scores}}

### 5. Reranking
- Top-3 after rerank: {{ids and scores}}
- Latency: {{ms}}

### 6. Abstention check
- Top-1 reranker score: {{score}}
- Threshold: {{threshold}}
- Decision: {{abstained / proceed}}

### 7. Context packing
- Chunks sent to LLM: {{count}}
- Total context tokens: {{n}}

### 8. Generation
- Model: {{model}}
- Latency: {{ms}}
- Citations: {{list}}

## Anomalies

{{Flag anything suspicious: e.g., dense and sparse disagree strongly, low reranker scores across the board, no citations in final answer when chunks were packed}}
```

## Phase 4: Offer follow-ups

After the trace is captured:

- "Want me to use this trace to walk the §40 diagnostic chain via `/rag-debug`?"
- "Want to add this query to the golden set as a regression test?"
- "Want to compare against another query that succeeded to spot the difference?"

## Style notes

- The trace is the truth. Don't speculate about what happened without it.
- If audit logs already exist in the user's system, use them. Only add temporary tracing if there's no existing log.
- Remove the temporary tracing wrapper after capture — it shouldn't ship to production.

Use instead when: `/rag-debug` — diagnose why the answer is wrong (it starts from this trace); `/rag-eval-init` — turn captured traces into a golden set and CI gate.

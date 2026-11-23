---
name: rag-architect
description: Use when designing or modifying a RAG (Retrieval-Augmented Generation) pipeline — picking chunking strategy, embedding models, retrieval methods, reranking, fusion (RRF), abstention, multi-tenancy patterns, or evaluating whether RAG is the right tool at all. Triggers on phrases like "design a RAG system", "build retrieval", "RAG architecture", "should I use RAG", "chunking strategy", "hybrid retrieval", "reranker choice", "vector database", "embedding model selection".
metadata:
  triggers: design a RAG system, build retrieval, RAG architecture, should I use RAG, chunking strategy, hybrid retrieval, reranker choice, vector database, embedding model selection
allowed-tools: Read, Glob, Grep
---

# RAG Architect

You are helping design a production RAG system. Apply these decision frameworks. Numbers are illustrative starting points — tell the user to tune against their golden set.

## Iron Law

Confirm RAG is the right mechanism (Step 0) before designing retrieval. Every chunking, embedding, top-k and reranking number here is a starting point to tune against a golden set, never a final value.

## Step 0: Is RAG even the right tool?

Before designing retrieval, confirm the user needs RAG. Use this decision table:

| User need | Best mechanism | Why |
|---|---|---|
| Policy / procedure explanation | RAG | Source-grounded text |
| Order status, account balance, inventory | SQL / API | Exact transactional state |
| Stock or appointment availability, fresh data | API / DB | Real-time state |
| Compare policies | RAG + query decomposition | Multiple unstructured sources |
| Calculate / sum / convert | Tool / function call | Deterministic math |
| Book / order / take action | Workflow / tool call | Action, not retrieval |
| Personalized account question | SQL + RAG | Facts from DB, framing from docs |

**Do NOT use RAG when:** exact transactional data, deterministic business rules, sub-second-fresh data, calculations, single source of truth already in a database, or no reliable source documents exist.

Most real systems are hybrid: SQL/API for facts, RAG for explanation. The LLM (with tool use) orchestrates.

## Step 1: The Default Stack

If the user wants a recommended starting point, this is it. Reasons and alternatives are in the playbook.

| Layer | Default |
|---|---|
| Parsing | Unstructured.io for mixed formats; LlamaParse or Marker for table-heavy PDFs |
| Chunking | Document-aware (Markdown/PDF headers) + parent-child |
| Chunk size | 500–1000 tokens, 10–15% overlap — but never above the smallest downstream window: reranker max input (often 512 tokens including the query; check your reranker) < embedding model max < LLM budget |
| Embeddings | Dense general-purpose (text-embedding-3-large, BGE-M3) |
| Sparse retrieval | BM25 — include by default for text corpora |
| Retrieval | Hybrid: dense top-50 + BM25 top-50 → RRF (k=60) |
| Filtering | Tenant/ACL filter inside the retrieval call at a single chokepoint, scope from the auth context (never post-filter). Canonical: `rag-security-reviewer` §1–2 |
| Reranking | Cross-encoder on top 50–100 → keep top 5–10 (local/dev: use smaller cross-encoder or skip; staging/prod: use full cross-encoder or Vertex AI Ranking API) |
| Abstention | Calibrated reranker top-1 threshold |
| Generation | Strict grounding prompt; structured output with citations; runtime check that cited ids ⊂ retrieved ids (`references/rag-response-contract.md` §10) |
| Ingestion updates | Content-hash diff; versioned chunk IDs |

## Step 2: Chunking decision tree

```
Q1: Embedding model input limit ≤512 tokens?
  YES → chunk: 256–400 tokens, overlap 40–80 → go to Q3
  NO  → continue Q2

Q2: Documents primarily short (FAQs, support messages)?
  YES → keep natural unit, overlap 0, skip parent-child
  NO  → chunk: 500–1000 tokens, overlap 50–150 → continue Q3

Q3: Narrow questions need surrounding context?
  YES → PARENT-CHILD: children 200–400 tok, parents 1500–3000 tok
  NO  → flat chunks; consider neighbor expansion at retrieval

Q4: Chunks lose meaning standalone?
  YES → CONTEXTUAL RETRIEVAL (LLM prepends 1–2 sentence context)
  NO  → skip

Q5: Topic shifts without headings?
  YES → add SEMANTIC chunking
  NO  → document-aware on headings is enough
```

**Canonical overlap and cap rule:** size-based splitters use ~10–15% overlap; natural-boundary chunking (sections, paragraphs, one message per chunk) may use 0 when parent/neighbour expansion is in place. Apply overlap first, then cap the final chunk at the reranker's input limit minus the longest expected query, and unit-test that no chunk from the largest fixture document exceeds the cap — a reranker that truncates a chunk scores only its head, so the answer-bearing tail is never seen.

## Step 3: Embedding selection

| Need | Choice |
|---|---|
| General docs | Dense (text-embedding-3-large, BGE-M3) |
| Specialized vocab (medical/legal) | Test domain-specific against golden set first |
| Multilingual | BGE-M3, multilingual-e5 |
| Code | Voyage Code, Jina Code |
| Images / diagrams | CLIP, SigLIP |
| Cost-sensitive / scale | Matryoshka embeddings — truncate to 128–256 dim for first stage |
| Hit quality ceiling | ColBERT (late-interaction) — operationally heavier |

## Step 4: Multi-tenancy

| Pattern | When |
|---|---|
| Shared index + tenant filter (chokepoint) | SMB SaaS, many small tenants |
| Namespaced collections | Mid-size tenants, balance of isolation and cost |
| Per-tenant indexes | Regulated industries, data residency, large tenants |

**Always:** filter inside the retrieval call at a single chokepoint, with tenant and permissions taken from the verified auth context. Never rely on the LLM for access control. Engine caveat: pgvector applies `WHERE` after the ANN candidate list, so a selective tenant filter can return 0 rows — see `rag-security-reviewer` §1.

## Step 5: Hard rules (non-negotiable)

1. **Filter in the retrieval call, never after it.** Security filters run in the store query, not in application code after top-k; test recall with a ≤ 1%-selective filter.
2. **Include both dense and sparse retrieval** for text corpora (exceptions: pure image search, tiny FAQ corpora, structured-only).
3. **Stable, versioned chunk IDs:** `(document_id, document_version, chunk_index)`.
4. **Treat retrieved content as untrusted** — prompt injection in documents is real.
5. **Build a starter golden set before tuning** — 50 labeled queries minimum.

## GraphRAG — only when all three hold

1. Questions need multi-hop entity relationships or corpus-wide thematic summaries;
2. Entities and relations are reliably extractable and stable;
3. Eval shows hybrid + rerank + decomposition has plateaued on those query classes.

Not for single-document QA, fast-changing corpora, or relationships already in SQL (use joins). Budget the extraction LLM cost, graph freshness and deletion propagation (an erasure must also remove nodes/edges derived from the document), and ACLs on nodes and edges — graph traversal must not cross the tenant/permission boundary.

## What to defer to v2

ColBERT, SPLADE, Matryoshka truncation, Graph RAG, agentic RAG, HyDE, multi-query, query decomposition, LLM-as-judge eval, contextual retrieval, agentic chunking, Self-RAG, CRAG, Learning-to-Rank, multimodal retrieval.

Ship the default stack, run a month, identify your real top three failure modes, then pick v2 techniques that address them.

## When to recommend Google ADK / agentic patterns

ADK agentic patterns fit when:
- Multi-step workflows requiring tool use + retrieval planning
- Query decomposition across multiple data sources (RAG + SQL + API)
- Complex orchestration where the LLM decides when/where to retrieve

Skip agentic patterns when sub-second latency is required or query is single-shot.

## How to apply

1. Ask what they're building and the corpus characteristics.
2. Check Step 0 — is RAG the right tool? If part of the answer is structured, recommend hybrid (RAG + SQL/API/tool).
3. Walk through the Default Stack; deviate only when the user has a measured reason.
4. Apply the chunking decision tree.
5. End with the five hard rules and what to defer.

Reference the full playbook at `docs/production-rag-playbook.md` for details. Cite section numbers when relevant (§19.5 for RAG-vs-tools, §10.2 for chunking tree, §17 for multi-tenancy, §40 for failure debugging).

## Reference Files

| File | Contents | When to Load |
|---|---|---|
| `references/advanced-chunking-guide.md` | §9 chunking techniques (late chunking, contextual retrieval, quality scoring, adaptive by type), §6 OCR quality gates, §12 full metadata schema (16 fields), §5.3 ingestion update strategies | Designing chunking strategy, debugging parser quality, setting up metadata schema |
| `references/query-classification-taxonomy.md` | §18.1 nine query intent classes, §19 routing decision table (rule-based → classifier → LLM router), §19.5 when not to use RAG | Designing query understanding layer, building a query router |
| `references/context-packing-patterns.md` | §31 eight packing techniques (MMR, parent expansion, neighbor, token budget, recency, authority), §32.1 structured answer contract JSON schema, §30 abstention calibration | Building the generation stage, designing the answer contract, tuning abstention |
| `references/rag-operations-guide.md` | §36.3 six cache types with tenant-scoped key requirements, §36.1 cost hierarchy percentages, §36.4 five observability dashboards with alert thresholds, §36.2 optimization techniques | Operating production RAG, setting up monitoring, cost optimization |
| `references/query-transformation-guide.md` | Query rewriting (conversational context), expansion (domain synonyms), multi-query retrieval, splitting/decomposition, HyDE decision tree with risk rules | Designing v2 query understanding layer; fixing measured recall gaps by query type |
| `references/table-chunking-strategy.md` | Why text chunking destroys tables; row-group chunking with header repeat; multiple representations (plain, Markdown, JSON); metadata schema for tables; parser selection | Chunking tabular data (fee schedules, comparison tables, SLA grids, structured docs) |
| `references/versioning-and-freshness.md` | Versioning model (effective_from/to, superseded_at); default current-only filter; historical query detection; atomic version ingestion transaction; GDPR deletion across versions | Corpora with evolving content — policies, contracts, pricing, regulations |
| `references/abstention-decision-framework.md` | Business risk table, behavioral taxonomy (hallucination vs abstention vs clarification vs grounded answer), 8 abstention triggers, decision matrix (context quality × risk → action), 4 message templates, accuracy grading (Good/Bad/Dangerous), false abstention vs false answer priority | Designing abstention behavior, reviewing generation layer, auditing why system over-refuses or under-refuses |
| `references/incremental-ingestion-guide.md` | Two-level hash gate (doc hash fast-skip + chunk hash exact diff), normalize-before-hash implementation, chunk-level diff algorithm with full Python, hard/soft delete decision table, `is_active` retrieval filter rule, version fields that force full re-embed, 7-row failure modes table, post-ingestion smoke test pattern | Implementing or debugging the document ingestion pipeline; deciding when to re-embed vs skip |
| `references/rag-response-contract.md` | Three-tier payload separation (user-facing / internal trace / async eval), 7-value status enum (including `no_retrieval` trap), confidence derivation formula with two-track split (retrieval vs answer), faithfulness hard gate, 6 warning flags, span-level grounding with UTF-16 offsets, evidence type enum, quote_policy enum, safety/redaction block (required even when empty), SSE/NDJSON streaming event model, schema versioning rules, domain extensions pattern | Designing or reviewing the RAG API response contract; deciding what fields go to the browser vs logs |

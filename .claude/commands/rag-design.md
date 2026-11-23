---
description: Interactive RAG architecture design — produces an ADR with stack choices grounded in the production playbook
argument-hint: "[project-name]"
allowed-tools: Read, Write, Glob, Grep, AskUserQuestion
---

# /rag-design — Interactive RAG Architecture Design

You are helping the user design a production RAG system for the project: **$ARGUMENTS**.

Produce an Architecture Decision Record (ADR) in markdown, saved to `docs/adr/NNN-rag-architecture.md` (auto-numbered).

## Phase 1: Discovery (ask interactively)

Ask these questions one at a time. Wait for the user's answer before continuing. Do not assume:

1. **Corpus characteristics**
   - What kinds of documents? (PDF / Markdown / HTML / DOCX / mixed)
   - Approximate corpus size? (thousands / hundreds of thousands / millions of docs)
   - Update frequency? (static / daily / hourly / real-time)
   - Are there tables, code, images, or scanned docs?

2. **Query patterns**
   - What kinds of questions will users ask? Give 3–5 representative examples.
   - Are there proper nouns, IDs, error codes, or rare terms? (BM25 needed)
   - Are queries conversational or keyword-style?
   - Single-question or multi-step (comparisons, multi-hop)?

3. **Users and isolation**
   - Single-tenant or multi-tenant?
   - Access control requirements? (roles, groups, document-level ACLs)
   - Regulatory regime? (HIPAA, GDPR, SOC2, none)

4. **Latency and scale**
   - Target p95 latency?
   - Expected QPS?
   - Cost ceiling per query (if known)?

5. **Non-RAG needs**
   - Are some questions actually about structured data (orders, inventory, account state) that should hit SQL / API instead?
   - This is the §19.5 question — flag it explicitly.

## Phase 2: Apply the playbook decision framework

Based on answers, walk these decisions and explain each:

1. **Is RAG the right tool for each query type?** Some may route to SQL/API/tool use (§19.5).
2. **Chunking strategy** (chunking decision tree, §10.2)
3. **Embedding model selection** (§14, §15)
4. **Retrieval method** — likely hybrid (BM25 + dense + RRF), justify (§23)
5. **Filtering / multi-tenancy pattern** (§17, §20.2 — filter inside the retrieval call, scope from the auth context; canonical: `rag-security-reviewer` §1–2; pgvector selective filters need the filtered-ANN mitigation)
6. **Reranking** — cross-encoder default (§28)
7. **Abstention threshold strategy** (§30)
8. **Generation prompt + answer contract** (§32)
9. **Eval approach for v1** — golden set size, metrics (§33–37)
10. **Operational concerns** — observability, cost, ingestion lifecycle

## Phase 3: Produce the ADR

Save to `docs/adr/NNN-rag-architecture.md` using this template:

```markdown
# ADR-NNN: RAG Architecture for {{project-name}}

**Status:** Proposed
**Date:** {{today}}
**Deciders:** {{user}}

## Context

{{Summary of corpus, queries, users, constraints from Phase 1}}

## Decision

### Scope: What RAG handles vs what it doesn't

| Query type | Mechanism | Why |
|---|---|---|
| {{type 1}} | RAG | {{reason}} |
| {{type 2}} | SQL/API | {{reason}} |
| {{type 3}} | Hybrid (RAG + tool) | {{reason}} |

### Stack

| Layer | Choice | Rationale |
|---|---|---|
| Parsing | {{}} | {{}} |
| Chunking | {{}} | {{}} |
| Chunk size | {{}} | {{}} |
| Embeddings | {{}} | {{}} |
| Sparse retrieval | {{}} | {{}} |
| Retrieval | {{}} | {{}} |
| Filtering | {{Pre-filtered ANN at single chokepoint}} | Security |
| Reranking | {{}} | {{}} |
| Abstention | {{}} | {{}} |
| Generation | {{Strict grounding, structured answer contract}} | {{}} |
| Multi-tenancy | {{}} | {{}} |
| Ingestion updates | {{Content-hash diff, versioned chunk IDs}} | {{}} |

### What we deliberately defer to v2

{{List with reasons}}

### Hard rules

1. Filter inside the retrieval call, never post-filter for security
2. Hybrid retrieval (dense + BM25) unless measured exception
3. Versioned chunk IDs from day one
4. Retrieved content is untrusted (prompt injection defenses)
5. Golden set (50+ queries) before tuning

## Consequences

{{What this enables, what it costs, what risks remain}}

## Open questions

{{Anything that needs measurement before commit}}

## References

- `rag-architect` skill (`.claude/skills/rag-architect/SKILL.md` and `references/`) — the external production RAG playbook that the § numbers cite is not shipped in this repository; mark a § citation UNVERIFIED unless you can open the source
- §1.5 Default Stack
- §19.5 RAG vs Tools vs SQL
- {{other relevant sections}}
```

## Phase 4: Confirm and create eval bootstrap

After ADR is written, offer to:
- Create the starter golden set file (`evals/golden_set.yaml` with 5–10 placeholder queries)
- Scaffold a Python eval runner (`evals/run_eval.py`)
- Suggest the next 3 PRs to ship v1

## Style notes

- Be skeptical when the user wants a fancy technique (Graph RAG, agentic, HyDE). Push toward the default stack unless they have a measured reason.
- If the user can't answer a discovery question, that's a finding — note it as "TBD, measure first" in the ADR.
- Cite playbook section numbers in the ADR rationale column.
- The output is a *decision*, not a survey of options. Recommend, justify, and move on.

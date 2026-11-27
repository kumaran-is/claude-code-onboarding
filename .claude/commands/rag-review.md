---
description: Audit a RAG pipeline E2E against all 8 stages of the production RAG checklist; produce a structured gaps report with severity and verdict
allowed-tools: Read, Glob, Grep
---

# /rag-review — E2E RAG Pipeline Audit

**Skill:** Load `rag-review` skill — it is the single source of truth for all 8-stage checks, severity rubric, verdict format, and reference cross-links. Do not restate checks inline here.

Audit a RAG pipeline against the production checklist covering all 8 stages: ingestion/chunking, versioning/updates, embedding/indexing, query routing, retrieval/fusion/reranking, generation/abstention, security, and eval/observability.

## Phase 1: Discover the implementation

Walk the repo and identify:
- Where is the RAG pipeline code? (`rag/`, `retrieval/`, `pipeline/`, `agents/`, or similar)
- **Which selectable framework?** (`google-adk` / `llamaindex` / `langchain`; custom Python is compatibility-only)
- What vector DB is used? (check imports: pgvector, weaviate, qdrant, pinecone, chroma)
- What embedding model and reranker, if any?
- Where is the generation prompt template? Is there a second synthesizer (LlamaIndex query engine **and** ADK/LangGraph generate)?
- Hosted LlamaParse / `llama_cloud` without an approval record?
- Is there an audit log?
- Is there an eval directory with a golden set?

If the structure is unclear, ask the user once to point at the main pipeline entry point.

## Phase 2: Run the checklist

Apply the 8-stage checklist from the `rag-review` skill. For each check, classify as:
- ✅ **Present** — implemented correctly with evidence
- ⚠️ **Partial** — exists but incomplete or misconfigured
- ❌ **Missing** — not present
- ❓ **Unknown** — couldn't determine from available code

For every ❌ or ⚠️ finding, cite **file:line** as evidence. No generic advice without a code reference.

## Phase 3: Output a structured report

```markdown
# RAG Pipeline Audit

**Repo:** {{repo-name}}
**Date:** {{today}}
**Stack detected:** {{framework | vector DB | embedding model | reranker | LLM}}

## Summary

- ✅ Present: N of total
- ⚠️ Partial: N
- ❌ Missing: N
- ❓ Unknown: N

## 🔴 Critical (BLOCK)

### C1. {{Finding title}}
**Stage:** {{stage number and name}}
**Status:** ❌ Missing / ⚠️ Partial
**Evidence:** `path/to/file.py:42` — [paste the problematic code]
**Issue:** [one sentence — why this is a production risk]
**Fix:** [concrete code change or pattern]
**Reference:** `rag-review/SKILL.md §{{stage}} check {{#}}`

## 🟠 High (NEEDS_REVIEW — fix before merge)

### H1. {{Finding title}}
[same structure as Critical]

## 🟡 Medium (NEEDS_REVIEW — recommend)

[same structure]

## 🟢 Low (APPROVE with note)

[brief list — no full structure needed for Low]

## Recommended next 3 PRs (priority order)

1. **{{PR title}}** — fixes {{finding IDs}}; effort S/M/L
2. ...
3. ...

VERDICT: [APPROVE | NEEDS_REVIEW | BLOCK] — CRITICAL: N | HIGH: N | MEDIUM: N | LOW: N
```

## Phase 4: Offer follow-ups

After delivering the report, offer:
- Draft the top-priority fix as a PR-ready change
- Run `/rag-debug` traces for specific failing queries
- Scaffold missing eval setup via `/rag-eval-init`
- Dispatch `@rag-security-reviewer` for a deeper security audit on Stage 7 findings

## Style notes

- Cite file:line for every finding — no generic advice without evidence
- Severity matters: a missing audit log is 🟠 High; a post-filter on security is 🔴 Critical
- If a stage is clean, say so in one line — don't pad the report
- Mark ❓ Unknown and ask ONE clarifying question rather than guessing

Use instead when: `/rag-debug` — one failing query; `/rag-design` — no pipeline yet, choose the architecture (ADR); `/rag-eval-init` — the eval gate is missing.

# Orchestration Patterns

Detailed patterns for common multi-agent orchestration scenarios in this workspace.

---

## Pattern 1: Comprehensive Feature Review

**When to use:** Any PR touching security-sensitive code, database, or multiple services.

**Step-by-step:**

```
1. code-reviewer
   Prompt: "Review [file list] for quality, security, maintainability.
   Focus: [specific concerns or blank for full review].
   Output: severity-bucketed findings."

2. [stack-specific reviewer] (nestjs-reviewer / spring-reactive-reviewer / riverpod-reviewer / etc.)
   Prompt: "Review [file list] for [framework]-specific patterns.
   Check: module correctness, framework idioms, test coverage.
   Output: framework-specific findings with file:line."

3. security-reviewer
   Prompt: "Review [file list] for OWASP Top 10.
   Flag: auth issues, input validation, secret handling, injection vectors.
   Output: CRITICAL/HIGH/MEDIUM/LOW findings."

4. silent-failure-hunter
   Prompt: "Review [file list] for swallowed exceptions and silent failures.
   Find: catch blocks that return empty/null/default without logging.
   Output: file:line locations with severity."

5. pr-test-analyzer
   Prompt: "Analyze test coverage for [file list].
   Check: happy path, error conditions, edge cases, critical business logic.
   Output: coverage gap rating 1-10 with specific missing test cases."
```

**Synthesis:** See `synthesis-protocol.md`

---

## Pattern 2: Pre-Deploy Audit

**When to use:** Before merging significant feature branches or releasing.

**Parallel dispatch (all 3 simultaneously):**

```
Dispatch in parallel:
  security-reviewer     → "Audit [PR files] for OWASP Top 10 before deploy"
  [stack reviewer]      → "Review [PR files] for framework correctness"
  pr-test-analyzer      → "Identify behavioral test gaps in [PR files]"

After parallel agents complete:
  synthesize            → merge verdict APPROVE / NEEDS_REVIEW / BLOCK per
                           references/synthesis-protocol.md (Review Severity Policy)
  output-evaluator      → optional advisory second opinion on the staged diff;
                           its verdict never replaces the synthesis verdict (not a merge gate)
```

---

## Pattern 3: Full Flutter Feature

**When to use:** Any Flutter feature touching UI, state management, auth, or Firebase.

**Step-by-step:**

```
1. riverpod-reviewer
   "Review Riverpod providers in [file list].
   Check: provider types, ref.watch vs ref.read, AsyncValue handling, lifecycle."

2. flutter-security-expert
   "Review [file list] for Flutter security.
   Check: secure storage (not SharedPreferences for tokens), cert pinning, GDPR data handling."

3. accessibility-auditor
   "Review [file list] for WCAG 2.2 AA.
   Check: Semantics labels, touch targets >=48dp, color contrast."

4. ui-standards-expert
   "Review [file list] for design system compliance.
   Check: no hardcoded colors, AppSpacing usage, text style tokens."

5. silent-failure-hunter
   "Review [file list] for silent failures in async/await code and Firebase callbacks."
```

---

## Pattern 4: Agentic AI System Review

**When to use:** Any LangGraph, LangChain, or Google ADK agent implementation.

**Step-by-step:**

```
1. agentic-ai-reviewer
   "Review [file list] for agent correctness.
   Check: graph structure, guardrails, iteration limits, cost efficiency."

2. security-reviewer
   "Review [file list] for prompt injection and agentic AI security risks.
   Check: input sanitization, tool output validation, privilege escalation."

3. rag-implementation-reviewer (only if RAG components present)
   "Review [file list] for RAG pipeline correctness.
   Check: embedding model pinned, chunking justified, reranking present, null guards."

4. silent-failure-hunter
   "Review [file list] for swallowed exceptions in tool calls and LLM API invocations."
```

---

## Pattern 5: Database Schema Review

**When to use:** Any migration, new table, index change, or vector column addition.

**Step-by-step:**

```
1. postgresql-database-reviewer
   "Review [migration files] before running on staging.
   Check: index coverage, constraint correctness, migration safety, reversibility."

2. pgvector-schema-reviewer (only if vector columns or indexes added)
   "Review [migration files] for pgvector correctness.
   Check: operator-index alignment, dimension vs model match, null guards."
```

---

## Pattern 6: Architecture Validation

**When to use:** Before committing to a significant architectural decision.

**Step-by-step:**

```
1. architect
   "Design [system/feature] with C4 diagram and API contracts.
   Output: Mermaid diagram + ADR with alternatives considered."

2. plan-challenger
   "Attack this plan across 5 dimensions: Assumptions, Missing Cases, Security,
   Architecture, Complexity Creep. Eliminate false positives. Output: issues by severity."

3. threat-modeling-expert (if security-sensitive)
   "Perform STRIDE analysis on [architecture/feature].
   Output: threat model + risk assessment + security requirements."
```

---

## Dispatch Template

Use this template when dispatching any agent to ensure adequate context:

```
Agent: [agent-name]
Task: [specific task — not "review this code"]
Files: [explicit file paths]
Tech stack: [Java 21 / NestJS 11 / Python 3.14 / Flutter 3.50.x / Angular 22.3 / React 19.3 / etc.]
Focus: [specific area of concern]
Output format: [severity-bucketed findings | PASS/FAIL | recommendation list]
Non-negotiable rules:
- No silent failures: every catch block must log + rethrow or return error state
- Load the relevant skill before starting
- Show file:line evidence for every finding
```

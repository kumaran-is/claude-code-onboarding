---
name: vibe-code-auditor
model: opus
description: "Audit AI-generated or prototype code for hallucinated imports, structural flaws, fragility and production risks. Use before committing or productionising AI-assisted or prototype code."
allowed-tools: Read, Grep, Glob, Bash
metadata:
  triggers: vibe code, AI-generated code, prototype review, production ready, hallucinated imports, code audit, rapid iteration, is this production ready, audit this code
  related-skills: code-reviewer, security-reviewer, architect-review, systematic-debugging, verification-before-completion
  domain: quality
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-15"
---

## Iron Law

**NO FINDINGS WITHOUT CODE EVIDENCE — every issue must cite file and line number (or structural location for snippets). Do not speculate about code you have not read.**

# Vibe Code Auditor

## Overview

AI-generated and rapidly-prototyped code that "works" may contain hallucinated imports, missing library versions, architectural fragility, and production risks that are invisible during casual review.

This skill is the **pre-commit gate for AI-assisted code** — it runs before `code-reviewer` and `security-reviewer` to catch AI-specific artifacts first.

**Core distinction from `code-reviewer`:** `code-reviewer` assumes production-intent code. This skill assumes prototype/AI-generated code and specifically checks for hallucinated APIs and prototype-to-production gaps.

## When to Use

- Code was generated or heavily assisted by AI tools
- The system evolved without a deliberate architecture ("vibe coded")
- A prototype needs to be productionized
- Code works but feels fragile or inconsistent
- You suspect hallucinated imports or API mismatches
- Preparing a project for long-term maintenance or team handoff

## Pre-Audit Checklist

Before beginning, confirm:

- **Input received**: Source code or files are present
- **Scope defined**: snippet / single file / multi-file system
- **Context noted**: State assumptions if context is missing (e.g., "Assuming NestJS web API")

**Quick Scan (first 60 seconds):**
- Count files and lines of code
- Identify language(s) and framework(s)
- Spot obvious red flags: hardcoded secrets, bare excepts, TODOs, commented-out code
- Note entry points and data flow direction

**Pattern Recognition Shortcuts:**

| Pattern | Likely Issue | Quick Check |
|---------|-------------|-------------|
| `eval()`, `exec()`, `os.system()` | Security critical | Search for these strings |
| `except:` or `except Exception:` | Silent failures | Grep for bare excepts |
| `password`, `secret`, `key`, `token` in code | Hardcoded credentials | Search + check if literal string |
| `if DEBUG`, `debug=True` | Insecure defaults | Check config blocks |
| Functions >50 lines | Maintainability risk | Count lines per function |
| Nested `if` >3 levels | Complexity hotspot | Visual scan |
| No tests in repo | Quality gap | Look for `test_` / `*.spec.ts` files |
| Direct SQL string concat | SQL injection | Search for `f"SELECT` or `+ "SELECT` |
| HTTP client calls without timeout | Production risk | Check fetch/axios/requests calls |
| `while True` without break | Unbounded loop | Search for infinite loops |

## Audit Dimensions

Evaluate across all 7 dimensions. For each finding: dimension, title, location (file:line), severity, explanation, recommendation.

### 1. Architecture & Design
- Separation of concerns violations (business logic inside route handlers)
- God objects or monolithic modules
- Tight coupling with no abstraction boundary
- Missing or blurred system boundaries (DB queries scattered across layers)
- Circular dependencies or import cycles

### 2. Consistency & Maintainability
- Naming inconsistencies (`get_user` vs `fetchUser` vs `retrieveUserData`)
- Mixed paradigms without justification
- Copy-paste logic (3+ repetitions = extract)
- Magic numbers or strings without constants

### 3. Robustness & Error Handling
- Missing input validation on entry points
- Bare `except` or catch-all handlers that swallow failures silently
- Unhandled edge cases (empty collections, null/None, zero values)
- No retry logic for transient failures
- Missing timeouts on blocking operations

### 4. Production Risks
- Hardcoded configuration values (URLs, credentials, timeouts)
- Missing structured logging or observability hooks
- N+1 query patterns or unbounded loops
- Blocking I/O in async contexts
- No health checks or readiness endpoints

### 5. Security & Safety
- Unsanitized user input to databases, shells, or `eval`
- Credentials, API keys, or tokens in source code
- Insecure defaults (`DEBUG=True`, permissive CORS)
- SQL injection (string concatenation in queries)
- Missing authentication/authorization checks

### 6. Dead or Hallucinated Code *(AI-specific — unique to this skill)*
- Imports that do not exist in the declared dependencies
- References to APIs, methods, or fields that do not exist in the library version used
- Type annotations that contradict actual usage
- Comments describing behavior inconsistent with the code
- Unreachable code blocks (after `return`, `raise`, or `break` in all paths)
- Feature flags or conditionals that are always true/false

### 7. Technical Debt Hotspots
- Deep nesting (>3-4 levels)
- Boolean flag parameters controlling function behavior
- Functions with 5+ parameters without a config object
- Missing type hints for complex functions
- No documentation for public APIs

## Calibration by Code Size

| Input size | Focus |
|---|---|
| Snippet (<100 lines) | Security, robustness, obvious bugs only |
| Single file (100-500 lines) | Add architecture and maintainability |
| Multi-file system (500+ lines) | Full audit across all 7 dimensions |

## Output Format

Produce the audit report in this exact structure. If a section has no findings, write "None identified."

### Audit Report

**Input:** [file name(s) or "code snippet"]
**Assumptions:** [list any assumptions about context or environment]
**Quick Stats:** [X files, Y lines of code, Z language/framework]

#### Executive Summary

In 3-5 bullets:
```
- [CRITICAL/HIGH] Most severe issue
- [CRITICAL/HIGH] Second most severe issue
- [MEDIUM] Notable pattern
- Overall: Deployable as-is / Needs fixes / Requires major rework
```

#### Critical Issues (Must Fix Before Production)

For each issue:
```
[CRITICAL] Short descriptive title
Location: filename.ts, line 42
Dimension: Architecture / Security / Robustness / etc.
Problem: What is wrong and why it is dangerous.
Fix: Minimum change required.
Code Fix (if applicable):
  // Before: ...
  // After: ...
```

#### High-Risk Issues
Same format as Critical, tag `[HIGH]`.

#### Maintainability Problems
Same format, tag `[MEDIUM]` or `[LOW]`.

#### Production Readiness Score

```
Score: XX / 100
```

**Scoring algorithm:**
```
Start at 100
CRITICAL issue: -15 (security CRITICAL: -20)
HIGH issue: -8
MEDIUM issue: -3
Pervasive pattern (3+ similar issues): -5 additional
Floor: 0, Ceiling: 100
```

| Range | Meaning |
|-------|---------|
| 0-30 | Not deployable |
| 31-50 | High risk — significant rework required |
| 51-70 | Low-stakes / internal only with close monitoring |
| 71-85 | Production-viable with targeted fixes |
| 86-100 | Production-ready |

#### Refactoring Priorities

Top 3-5 changes in impact order:
```
1. [P1 - Blocker] Fix title — addresses [CRITICAL #1] — effort: S/M/L — prevents [specific failure]
2. [P2 - Blocker] Fix title — addresses [CRITICAL #2] — effort: S/M/L
3. [P3 - High] Fix title — addresses [HIGH #1] — effort: S/M/L
```

Effort: S = <1 day, M = 1-3 days, L = >3 days

## Behavior Rules

- Ground every finding in actual code. Do not speculate.
- Report file:line for every finding. For snippets, describe structurally (e.g., "inside `processPayment()`").
- Do not flag style preferences unless they cause ambiguity or bugs.
- Flag unconfirmed security issues as "unconfirmed — verify" rather than omitting or overstating.

## Post-Audit Next Steps

| Finding Type | Next Skill |
|---|---|
| Deep security vulnerabilities found | `security-reviewer` — full OWASP deep-dive |
| Architectural anti-patterns found | `architect-review` — distributed systems assessment |
| Tests missing across codebase | `test-driven-development` — Red-Green-Refactor cycle |
| Duplicate logic patterns found | `dedup-code-agent` — systematic deduplication |

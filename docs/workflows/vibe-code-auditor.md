# Vibe Code Auditor Workflow

Use when code was AI-generated, rapidly prototyped, or evolved without a deliberate architecture — before committing, handing off, or escalating to full code review.

## When to Use

- AI assistant generated the code (Claude, Copilot, Cursor, etc.)
- A prototype needs to be productionized
- Code "works" but feels fragile or inconsistent
- You suspect hallucinated imports or library API mismatches
- Preparing a project for team handoff or long-term maintenance

## How to Trigger

```bash
# Paste or reference the code, then:
# "Audit this code — use the vibe-code-auditor skill"
```

## Workflow

```
1. Load skill
   └── Paste code or reference files in context

2. Pre-audit triage (automatic)
   ├── Count: files, lines, languages
   ├── Quick scan: hardcoded secrets, bare excepts, TODOs
   └── Calibrate: snippet / single-file / multi-file depth

3. 7-dimension audit
   ├── Architecture & Design
   ├── Consistency & Maintainability
   ├── Robustness & Error Handling
   ├── Production Risks
   ├── Security & Safety
   ├── Dead / Hallucinated Code  ← AI-specific dimension
   └── Technical Debt Hotspots

4. Audit Report output
   ├── Executive Summary (3-5 bullets)
   ├── Critical Issues [CRITICAL] — must fix before production
   ├── High-Risk Issues [HIGH]
   ├── Maintainability Problems [MEDIUM/LOW]
   └── Production Readiness Score (0-100)

5. Act on score
   ├── 0-50  → Requires major rework — do NOT commit
   ├── 51-70 → Fix CRITICAL + HIGH before any production exposure
   ├── 71-85 → Fix targeted issues, then run code-reviewer
   └── 86-100 → Run code-reviewer as final gate, then commit
```

## Integration with Other Skills

| Skill | When to Chain |
|-------|---------------|
| `code-reviewer` | Always — run after vibe-code-auditor resolves CRITICAL/HIGH |
| `security-reviewer` | When security dimension finds CRITICAL issues — full OWASP deep-dive |
| `architect-review` | When architecture dimension finds anti-patterns — distributed systems assessment |
| `test-driven-development` | When no tests exist — add coverage before committing |
| `dedup-code-agent` | When copy-paste logic found across 3+ locations |

## Difference from code-reviewer

| | `vibe-code-auditor` | `code-reviewer` |
|---|---|---|
| **Assumes code is** | AI-generated / prototype | Production-intent |
| **Hallucination check** | ✅ Dimension 6 — imports, API versions | ❌ Not covered |
| **Scoring** | ✅ 0-100 Production Readiness Score | ❌ Qualitative findings |
| **Calibration** | ✅ Snippet / file / multi-file depth | Fixed depth |
| **Run order** | First — before code-reviewer | After vibe-code-auditor |

## Example: NestJS AI-Generated Module

```
Input: 3 files, 280 lines, NestJS/TypeScript (AI-generated payments module)

Executive Summary:
- [CRITICAL] PaymentsService imports from '@nestjs/stripe' — package does not exist (hallucinated)
- [HIGH] stripe.payouts.create() signature mismatch — changed in stripe v14 (API version mismatch)
- [HIGH] No error handling on Prisma calls — P2002 unique constraint not caught
- Overall: Needs fixes before production

Production Readiness Score: 47 / 100
(CRITICAL security -20, HIGH -8, HIGH -8, no-tests pattern -5 = 41 deductions)

Refactoring Priorities:
1. [P1 - Blocker] Remove @nestjs/stripe import — install stripe SDK directly — effort: S
2. [P2 - Blocker] Fix stripe.payouts.create() against v14 docs — effort: S
3. [P3 - High] Wrap Prisma calls, handle P2002 → 409 Conflict — effort: M
```

## Tech Stack Applicability

| Stack | Coverage |
|-------|----------|
| NestJS / TypeScript | ✅ Detects hallucinated NestJS decorators, missing Prisma imports, wrong decorator targets |
| Angular / TypeScript | ✅ Detects ghost Angular imports, signal API misuse, redundant `standalone: true` or explicit OnPush (both Angular 22 defaults) |
| Flutter / Dart | ✅ Detects Riverpod provider hallucinations, wrong ref.watch vs ref.read usage |
| Python / FastAPI | ✅ Detects non-existent FastAPI imports, sync handlers in async context, missing `async def` |
| Java / Spring Boot | ✅ Detects @Autowired on non-beans, missing @Repository, wrong WebFlux types |
| All stacks | ✅ Hardcoded secrets, bare excepts, N+1 patterns, missing timeouts |

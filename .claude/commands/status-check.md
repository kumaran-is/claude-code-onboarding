---
description: Binary status report showing what works, what's broken, and what's not implemented. No percentages, no hedging. Given a plan file, issue number or "the approved plan", audits every plan item against the source instead (read-only, path:line evidence per item).
allowed-tools: Bash, Read, Glob, Grep
---

# Status Check

Give me an honest status report. Follow these rules STRICTLY:

## Format Required

```
## What WORKS (end-to-end, no caveats)
- [Feature]: ✅ User can [specific action]

## What's BROKEN (non-functional)
- [Feature]: ❌ [What happens] instead of [what should happen]

## What's NOT IMPLEMENTED (doesn't exist yet)
- [Feature]: 🚫 Not built
```

## Rules

1. **NO PERCENTAGES** - Never say "90% done" or "mostly complete"
2. **NO CONTRADICTIONS** - If you list issues, it's BROKEN, not "works with issues"
3. **BINARY ONLY** - Either it WORKS end-to-end or it's BROKEN
4. **NO HEDGING** - No "almost", "nearly", "mostly", "partially"
5. **MATCH SUMMARY TO DETAILS** - If details show problems, summary must say BROKEN

## Evidence (mandatory)

A feature is WORKS only with evidence executed in THIS session: the test or flow that exercises it, its command and its own exit code (unit/integration runner, Playwright for web, Maestro for Flutter Android/iOS — `.claude/rules/testing-tool-selection.md`). Reading the code is not evidence. A feature you could not exercise goes under a fourth heading, `## NOT VERIFIED`, with what blocked it.

Use instead when: `/verify` — build/test exit codes per stack; `/project-status` — repo inventory with no verdict; `/checkpoint verify` — what changed since a snapshot.

## Plan conformance mode (when `$ARGUMENTS` names a plan)

If `$ARGUMENTS` is a plan file (`docs/plans/*.md`, an ADR, a spec), an issue number (`gh issue view <N>`: its acceptance criteria are the checklist) or "the approved plan" (the newest `docs/plans/*.md` for this branch), audit the plan against the source instead. Read-only: never edit, never fix. Echo which plan and its source first; if none resolves, stop and ask.

1. **Material assumptions** that shape the audit (or "None").
2. **One row per plan item**, tracing entry → logic → persistence (`verification-and-reporting.md` "Verify Before Claiming"):
   ```
   ### <item text from the plan>
   - Status: ✅ IMPLEMENTED | ⚠️ PARTIAL | ❌ MISSING | ❓ UNVERIFIED
   - Evidence: <path:line> — <what the code actually does> (each layer)
   ```
   PARTIAL and MISSING need evidence too: name the file you read and what was not there. UNVERIFIED means you did not read the source this run; never upgrade it without a citation.
3. **Docs-first check**: versions current and pinned, no deprecated API (`path:line`), current official APIs used. A deprecated call or stale pin is a gap, so the plan is not conformant.
4. **Report** in five buckets, never mixing inference into Verified: `Plan conformance — <source> — <N implemented / M total>`, then ✅ Verified, 🔧 Assumptions, ❌ Gaps / unverified, ⚠️ Risks / contradictions (both citations), 📋 Recommendations (extend an existing `file:line` first). If you ran out of items, the audit is INCOMPLETE and the unread items are UNVERIFIED.

Fixing gaps is `/iterate-pr` or the stack implementer; build and test evidence is `/verify`.

## Self-Check Before Responding

Ask yourself:
- Did I say something "works" then list why it doesn't? → REWRITE
- Did I use a percentage? → REMOVE IT
- Did I use "mostly/almost/nearly"? → REPLACE with WORKS or BROKEN

$ARGUMENTS

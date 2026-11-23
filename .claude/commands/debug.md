---
name: debug
description: Systematic debugging mode — loads the systematic-debugging skill and enforces root-cause-first investigation with structured output. Use when something is broken, a test fails, or behavior is unexpected.
allowed-tools: Read, Grep, Glob, Bash
---

# Debug

Loads the `systematic-debugging` skill and enforces the 4-phase root-cause-first process.

**Iron Law: NO fixes without root cause investigation first.**

## Input

`$ARGUMENTS` — description of the problem (e.g. "login fails intermittently", "NullPointerException in PaymentService:47", "Flutter app crashes on startup")

If `$ARGUMENTS` is empty, ask: "Describe the problem — paste the error message, stack trace, or reproduction steps."

## Process

Load and follow `systematic-debugging` skill phases in order:

1. **Phase 1 — Root Cause Investigation**
   - Read the error message completely (do not skim)
   - Reproduce consistently — exact steps, every time?
   - Check recent changes: `git log --oneline -10`, `git diff HEAD~1`
   - For multi-component systems: add diagnostic logging at each boundary before guessing

2. **Phase 2 — Pattern Analysis**
   - Find a working equivalent in the codebase
   - List every difference between working and broken

3. **Phase 3 — Hypothesis and Testing**
   - Form ONE hypothesis: "I think X is the root cause because Y"
   - Score it against alternatives using the hypothesis ranking table
   - Test minimally — one variable at a time

4. **Phase 4 — Implementation**
   - Write a failing test that reproduces the bug
   - Fix the root cause, not the symptom
   - Verify: test passes, no other tests broken

## Output Format

```
🔍 Symptom: [what is observable — exact error, stack trace, behavior]

🔎 Investigation:
- Recent changes: [git log summary or "none in past 10 commits"]
- Reproduction: [reproducible every time / intermittent / unclear]
- Evidence gathered: [what was read/logged/traced]

🎯 Root Cause: [one sentence — what is actually wrong and why]
  Hypothesis confidence: [X%] because [evidence]

✅ Fix: [the change — file:line]

🛡️ Prevention: [what would stop this class of bug recurring]
```

## If You Hit 3+ Failed Fixes

Stop. Do not attempt Fix #4. Per `systematic-debugging` skill Phase 4.5:
- Each fix revealing a new problem in a different place = architectural issue
- Raise with the developer before continuing

## Related

- Full 4-phase protocol: `.claude/skills/systematic-debugging/SKILL.md`
- Supporting techniques in same directory: `root-cause-tracing.md`, `defense-in-depth.md`, `condition-based-waiting.md`
- After the fix is confirmed: the reproducing test passes and `/verify` reports the stack PASS with its own exit code; `/validate-changes` is optional advisory review on top
- Use instead when: `/rag-debug` — a RAG system returns a wrong, missing or leaked answer; `error-detective` agent — the evidence is production logs or traces rather than a local repro

$ARGUMENTS

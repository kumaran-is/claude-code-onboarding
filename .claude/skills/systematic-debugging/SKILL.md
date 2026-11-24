---
name: systematic-debugging
description: "Root-cause-first debugging methodology for any bug, test failure, exception, or unexpected behavior — mandates investigation before proposing fixes. Use when something is broken, not working, crashing, or throwing errors; triggers: debug, error, bug, exception, stack trace, not working, crash."
allowed-tools: Read, Grep, Glob, Bash
metadata:
  triggers: debug, error, bug, exception, stack trace, troubleshoot, root cause, not working, crash, investigate issue
  related-skills: test-driven-development, verification-before-completion, code-reviewer
  domain: quality
  role: specialist
  scope: analysis
  output-format: analysis
last-reviewed: "2026-03-15"
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Manager wants it fixed NOW (systematic is faster than thrashing)

## The Four Phases

You MUST complete each phase before proceeding to the next.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully**
   - Don't skip past errors or warnings
   - They often contain the exact solution
   - Read stack traces completely
   - Note line numbers, file paths, error codes

2. **Reproduce Consistently**
   - Can you trigger it reliably?
   - What are the exact steps?
   - Does it happen every time?
   - If not reproducible → gather more data, don't guess

3. **Check Recent Changes**
   - What changed that could cause this?
   - Git diff, recent commits
   - New dependencies, config changes
   - Environmental differences

4. **Gather Evidence in Multi-Component Systems**

   **WHEN system has multiple components (CI → build → signing, API → service → database):**

   **BEFORE proposing fixes, add diagnostic instrumentation:**
   ```
   For EACH component boundary:
     - Log what data enters component
     - Log what data exits component
     - Verify environment/config propagation
     - Check state at each layer

   Run once to gather evidence showing WHERE it breaks
   THEN analyze evidence to identify failing component
   THEN investigate that specific component
   ```

   **Example (multi-layer system):**
   ```bash
   # Layer 1: Workflow
   echo "=== Secrets available in workflow: ==="
   echo "IDENTITY: ${IDENTITY:+SET}${IDENTITY:-UNSET}"

   # Layer 2: Build script
   echo "=== Env vars in build script: ==="
   env | grep IDENTITY || echo "IDENTITY not in environment"

   # Layer 3: Signing script
   echo "=== Keychain state: ==="
   security list-keychains
   security find-identity -v

   # Layer 4: Actual signing
   codesign --sign "$IDENTITY" --verbose=4 "$APP"
   ```

   **This reveals:** Which layer fails (secrets → workflow ✓, workflow → build ✗)

5. **Trace Data Flow**

   **WHEN error is deep in call stack:**

   See `root-cause-tracing.md` in this directory for the complete backward tracing technique.

   **Quick version:**
   - Where does bad value originate?
   - What called this with bad value?
   - Keep tracing up until you find the source
   - Fix at source, not at symptom

### Phase 2: Pattern Analysis

**Find the pattern before fixing:**

1. **Find Working Examples**
   - Locate similar working code in same codebase
   - What works that's similar to what's broken?

2. **Compare Against References**
   - If implementing pattern, read reference implementation COMPLETELY
   - Don't skim — read every line
   - Understand the pattern fully before applying

3. **Identify Differences**
   - What's different between working and broken?
   - List every difference, however small
   - Don't assume "that can't matter"

4. **Understand Dependencies**
   - What other components does this need?
   - What settings, config, environment?
   - What assumptions does it make?

### Phase 3: Hypothesis and Testing

**Scientific method:**

1. **Form Single Hypothesis**
   - State clearly: "I think X is the root cause because Y"
   - Write it down
   - Be specific, not vague

### Hypothesis Ranking

For each hypothesis, score and document:

| Hypothesis | Probability | Evidence | Falsification | Test Approach |
|------------|-------------|----------|---------------|---------------|
| H1: DB pool exhausted | 85% | Timeout errors every 30s | Check active connections < max | `SHOW PROCESSLIST` or pool metrics |
| H2: Network latency | 30% | Intermittent not consistent | Ping DB host | `curl` timing, traceroute |

**Scoring guide:**
- 80-100%: Strong evidence, consistent with all symptoms → test first
- 50-79%: Partial evidence, explains some symptoms → test second
- <50%: Weak evidence, speculative → test only if higher-ranked fail

Always state: "Highest-probability hypothesis is H1 (85%) because [evidence]."

### Five Whys Drill-Down

Use when root cause is unclear after initial hypothesis. Ask "Why?" 5 times:

**Example:**
```
Error: Database connection timeout after 30s
Why? The database connection pool was exhausted
Why? All connections were held by long-running queries
Why? A new feature introduced N+1 query patterns
Why? The ORM lazy-loading wasn't properly configured
Why? Code review didn't catch the performance regression
Root cause: Missing performance review criteria in PR checklist
```

Stop when you reach: a process failure, a human decision, or an external constraint.
The answer to the 5th "Why?" is your fix target.

2. **Test Minimally**
   - Make the SMALLEST possible change to test hypothesis
   - One variable at a time
   - Don't fix multiple things at once

3. **Verify Before Continuing**
   - Did it work? Yes → Phase 4
   - Didn't work? Form NEW hypothesis
   - DON'T add more fixes on top

4. **When You Don't Know**
   - Say "I don't understand X"
   - Don't pretend to know
   - Ask for help
   - Research more

### Phase 4: Implementation

**Fix the root cause, not the symptom:**

1. **Create Failing Test Case**
   - Simplest possible reproduction
   - Automated test if possible
   - One-off test script if no framework
   - MUST have before fixing
   - The test is **permanent**: committed in the same PR as the fix, named for the bug (`test_refund_twice_is_rejected`, not `test_fix_2`), and asserting the root cause rather than the symptom (the duplicate row is refused, not "no 500"). Show it red before the fix and green after; never delete or `skip` it once green
   - See `leverage-patterns.md` test-first protocol: write the test that defines success, then implement until it passes

2. **Implement Single Fix**
   - Address the root cause identified
   - ONE change at a time
   - No "while I'm here" improvements
   - No bundled refactoring

3. **Verify Fix**
   - Test passes now?
   - No other tests broken?
   - Issue actually resolved?

4. **If Fix Doesn't Work**
   - STOP
   - Count: How many fixes have you tried?
   - If < 3: Return to Phase 1, re-analyze with new information
   - **If ≥ 3: STOP and question the architecture (step 5 below)**
   - DON'T attempt Fix #4 without architectural discussion

5. **If 3+ Fixes Failed: Question Architecture**

   **Pattern indicating architectural problem:**
   - Each fix reveals new shared state/coupling/problem in different place
   - Fixes require "massive refactoring" to implement
   - Each fix creates new symptoms elsewhere

   **STOP and question fundamentals:**
   - Is this pattern fundamentally sound?
   - Are we "sticking with it through sheer inertia"?
   - Should we refactor architecture vs. continue fixing symptoms?

   **Discuss with the developer before attempting more fixes.**

   This is NOT a failed hypothesis — this is a wrong architecture.

### No-Progress Detection (catch a stuck loop before the 3rd blind retry)

The "3 fixes failed" counter is a backstop, not the first signal. A loop is usually
stuck several attempts earlier — detect it *structurally* instead of waiting to exhaust
the count (loop-engineering no-progress signals):

| Signal | What it looks like | Response |
|---|---|---|
| Repeated error | The SAME error recurs after your change — compare the **normalized** form (strip timestamps, IDs, paths, line offsets), not the raw text | Do not re-try the same class of fix. Form a genuinely new hypothesis (Phase 3) or escalate. |
| Ping-pong edit | Your new diff reverts a previous attempt's diff (alternating file hashes) | Stop — you are oscillating between two wrong states. The real cause is elsewhere; escalate. |
| Strategy repetition | You are about to run an approach already recorded as failed | Reject it without new evidence. A previously-failed strategy needs a NEW fact to be worth re-running. |
| Verifier stagnation | Failing-test count / error signature does not improve across attempts | Treat as no progress even if each attempt "looks" different. |

Rule of thumb: **a repeated normalized error signature with no new strategy = escalate
now** — do not spend the remaining attempts. Record the normalized signature when you log
an attempt so repeats are detectable across a long session (that is exactly what
`ralph-state.local.md`'s `## Attempt counts` is for in an autonomous `/ralph-loop`).

## Red Flags — STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before tracing data flow
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals new problem in different place**

**ALL of these mean: STOP. Return to Phase 1.**

**If 3+ fixes failed:** Question the architecture (see Phase 4.5)

## Developer Signals You're Doing It Wrong

**Watch for these redirections:**
- "Is that not happening?" — you assumed without verifying
- "Will it show us...?" — you should have added evidence gathering
- "Stop guessing" — you're proposing fixes without understanding
- "Ultrathink this" — question fundamentals, not just symptoms
- "We're stuck?" (frustrated) — your approach isn't working

**When you see these:** STOP. Return to Phase 1.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question pattern, don't fix again. |

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare | Identify differences |
| **3. Hypothesis** | Form theory, test minimally | Confirmed or new hypothesis |
| **4. Implementation** | Create test, fix, verify | Bug resolved, tests pass |

## When Process Reveals "No Root Cause"

If systematic investigation reveals issue is truly environmental, timing-dependent, or external:

1. You've completed the process
2. Document what you investigated
3. Implement appropriate handling (retry, timeout, error message)
4. Add monitoring/logging for future investigation

**But:** 95% of "no root cause" cases are incomplete investigation.

## Supporting Techniques

These techniques are available in this directory:

- **`root-cause-tracing.md`** — Trace bugs backward through call stack to find original trigger
- **`defense-in-depth.md`** — Add validation at multiple layers after finding root cause
- **`condition-based-waiting.md`** — Replace arbitrary timeouts with condition polling

**Related skills:**
- `leverage-patterns.md` test-first protocol — for creating failing test case (Phase 4, Step 1)
- `.claude/skills/verification-before-completion/SKILL.md` — verify fix worked before claiming success

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common

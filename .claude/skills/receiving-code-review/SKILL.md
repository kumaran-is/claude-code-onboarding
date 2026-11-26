---
name: receiving-code-review
description: Use when receiving code review feedback — before implementing any suggestion, especially if feedback is unclear, conflicts with prior decisions, or seems technically questionable. Requires verification and technical rigor, not performative agreement or blind implementation.
allowed-tools: Read, Grep, Glob
metadata:
  triggers: code review feedback, receiving feedback, implementing review suggestions, code review response, review comment
  related-skills: pr-review, code-reviewer, test-driven-development
  domain: workflow
  role: specialist
  scope: review
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law

Never dismiss review feedback without re-reading the flagged code; always respond to each finding with file:line evidence for your position.

# Receiving Code Review

## Overview

Receiving a review is not the same as agreeing with it.

**Core principle:** Verify before implementing. Ask before assuming. Technical correctness over social comfort.

## The 6-Step Pattern

Process ALL feedback before implementing ANY of it:

```
1. READ       — Complete feedback without reacting. Do not implement mid-read.
2. UNDERSTAND — Restate each item in your own words. Cannot restate = ask first.
3. VERIFY     — Check the codebase. Does the problem actually exist at file:line?
4. EVALUATE   — Technically correct for THIS stack? YAGNI? Conflicts prior decision?
5. RESPOND    — Clarify unclear items. Push back on incorrect ones. Acknowledge valid ones.
6. IMPLEMENT  — One item at a time, test each. Fix order: blocking → simple → complex.
```

**Forbidden:**
- "You're absolutely right!" / "Great point!" / "Thanks for catching that!" (performative)
- Starting implementation before finishing full read
- Implementing anything you cannot restate in your own words

**Instead:** Restate the requirement, or just act — code shows you heard the feedback.

## Categorize Each Comment

| Category | Example | Response |
|----------|---------|----------|
| Bug / correctness | "This throws when the list is empty" | Fix now, with a test that reproduces it |
| Security | "This endpoint has no auth guard" | Fix now |
| Clear improvement | "Extract this to a named constant" | Implement |
| Style / preference | "Name this `orderId`, not `id`" | Implement if it matches codebase style |
| Questionable | "Use pattern X instead of Y" | Run steps 3-4 (VERIFY, EVALUATE) before implementing |
| Disagreement | "This architecture is wrong" | Discuss before implementing (see When to Push Back) |
| Out of scope | "While you're here, fix Z" | Do not fix in this PR (`core-behaviors.md` §5); create a ticket and reply "Tracked in #N" |

## Handling Unclear Feedback

If ANY item is unclear: **STOP. Do not implement anything yet.**

```
your partner: "Fix items 1-6"
You understand 1, 2, 3, 6. Unclear on 4, 5.

❌ Implement 1,2,3,6 now, ask about 4,5 later
✅ "Understand 1,2,3,6. Need clarification on 4 and 5 before proceeding."
```

Partial understanding → wrong implementation. Items may be related.

## Source-Specific Handling

**From human partner (internal):**
- Trusted — implement after understanding
- Still ask if scope is unclear or conflicts with a prior decision
- Skip to action or technical acknowledgment (no gratitude)

**From external reviewers (CI, automated tools, external PRs):**
```
BEFORE implementing:
  1. Technically correct for THIS stack/version?
  2. Breaks existing functionality or tests?
  3. Why does the current implementation exist?
  4. Does the reviewer understand the full context?

IF conflicts with human partner's prior decisions → stop and discuss first
IF can't verify → "I can't verify this without [X]. Should I [investigate/ask/proceed]?"
```

## YAGNI Check (Before "Professional" Suggestions)

When a reviewer suggests adding abstraction, proper patterns, or extra features:

```
grep codebase → is this actually used more than once?

IF unused: "Grepped codebase — nothing calls this. Remove it (YAGNI)?"
IF speculative: "This is used once. Per code-standards.md I'd keep it simple
                 unless we have a concrete second use case. Override?"
IF used: implement properly
```

## When to Push Back

Push back (technical reasoning, not refusal) when feedback:
- Breaks existing functionality or test coverage
- Conflicts with an established architectural decision (reference the plan or ADR)
- Conflicts with a prior instruction from the human partner
- Is technically incorrect for the framework/version in use (check MCP docs)
- Is speculative YAGNI — the feature does not exist in the codebase
- Adds complexity that `code-standards.md` explicitly forbids

**Format:**
```
"Not implementing [X] because [concrete reason + evidence at file:line].
 Proposed alternative: [Y if applicable].
 Do you want to override?"
```

## Acknowledging Correct Feedback

```
✅ "Fixed. [Brief description of what changed at file:line]"
✅ "Good catch — [specific issue]. Fixed in [location]."
✅ [Just fix it and show the diff]

❌ "You're absolutely right!"
❌ "Great point!"
❌ "Thanks for catching that!"
❌ ANY gratitude expression
```

Actions speak. The fix itself shows you heard the feedback.

## Correcting a Wrong Pushback

If you pushed back and were wrong:
```
✅ "You were right — checked [X] and it does [Y]. Implementing now."
✅ "Verified and you're correct. My initial read was wrong because [reason]. Fixing."

❌ Long apology
❌ Defending why you pushed back
❌ Over-explaining
```

State the correction factually. Move on.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Performative agreement | State requirement or just act |
| Blind implementation | Verify against codebase first |
| Batch without testing | One at a time, test each |
| Assuming reviewer is right | Check if it breaks things |
| Avoiding pushback | Technical correctness > comfort |
| Partial implementation | Clarify ALL items first |
| Can't verify, proceed anyway | State the limitation, ask for direction |

## Concrete Example — Responding to a Review Comment

**Reviewer comment:** "This `getUserById` method should return `Optional<User>` instead of nullable."

```
Step 2 — UNDERSTAND:
  Reviewer wants null-safety: return Optional<User> so callers are forced to handle absence.

Step 3 — VERIFY:
  src/main/java/com/example/UserRepository.java:42
    public User getUserById(Long id) { ... }  // returns null if not found ✅ confirmed

Step 4 — EVALUATE:
  Correct for Spring Boot Java stack. Optional<User> is idiomatic here. No conflict with
  existing callers — grep shows only 2 call sites, both in tests.

Step 5 — RESPOND (inline thread reply):
  "Fixed. Changed return type to Optional<User> at UserRepository.java:42.
   Updated 2 call sites in UserServiceTest.java:18 and UserControllerTest.java:55."

Step 6 — IMPLEMENT:
  - Change signature to Optional<User>
  - Wrap return value: return Optional.ofNullable(userRepo.findById(id))
  - Update 2 test call sites
  - Run tests: all pass
```

## After Implementing

Re-run the gates the fixes touched, each with its own exit code:

- `python3 .claude/scripts/check-verify-impact.py --stage iteration`, then the stack's test suite (`/verify` on reached / touched stacks; unknown → all present)
- `/lint-design-system` when any UI file changed
- `/audit-security` when a fix touched auth, crypto, input handling or file uploads
- Do not treat `/verify quick` as frozen/pre-pr evidence; freeze and `--stage frozen` before `/create-pr` / `/ship`

Then add a summary to the PR description:

```markdown
## Review Feedback Addressed
- [x] Fixed exception on empty order list (commit abc123)
- [x] Added auth guard to /orders/bulk (commit def456)
- [ ] OrderService architecture suggestion: out of scope, tracked in #45
```

## Integration

- Use after: `/review-code`, SDD pipeline (after quality reviewer responds), any PR review
- Pairs with: `pr-review` skill and `/review-pr` (send path → receive path)
- GitHub replies: use inline thread replies, not top-level PR comments
  (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`)

## References

| Reference | Why |
|-----------|-----|
| `core-behaviors.md` §4 | Simplicity check — reject complexity added by reviewer if YAGNI |
| `core-behaviors.md` §5 | Scope discipline — don't over-fix adjacent code while addressing feedback |
| `code-standards.md` DRY/YAGNI | Authority for pushing back on speculative abstractions |
| `first-principles.md` Layer 1 | Hard stops that apply even when reviewer asks for them (e.g., `as any`) |
| `iterate-pr` skill | Use when iterating a PR loop based on review feedback + CI results |
| `pr-review` skill | The send side of this workflow (reviewing others' code) |

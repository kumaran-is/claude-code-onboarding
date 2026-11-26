# Implementation notes (sub-ADR log)

Per-issue decision log for choices a reviewer will ask about. Not an ADR. Not `lessons.md`.

**Iron Law: the `needs human review` flag is the product.** Forty unflagged entries are noise. Flag 0 → the human reads 0.

## Path

`docs/plans/<issue-N>-implementation-notes.md` (or `docs/plans/<branch-slug>-implementation-notes.md` when there is no issue). Never a repo-root global file (merge-conflict magnet under worktrees).

Seed **once** at the start of implementation (`/next` Step 5b). If the file already exists, **append only** — never `Write` over it. Verify with `git diff --numstat` against the default branch: the deletions column for this file must be `0`.

## What to log

Log only if all three hold:

1. Spec / ADR / constraint did not dictate the choice
2. A reviewer would have questions about it
3. It is visible in the code (not naming, log wording, formatting)

**Files** is the scope a reviewer greps — not a restatement of `git diff --stat`. One issue, one notes file; this is not a second plan (`/next --plan` / `plan-mode-review` stay the planning workflow).

Do not log constraint-dictated choices or restatements of the diff.

If the decision is load-bearing **and** architectural / cross-service / schema → write an ADR (`architecture-decision-records`) and reference its number here. Do not use notes to avoid ADRs.

## Entry schema (newest at top)

```markdown
---
### [ISO timestamp] — <one-line decision>

**Category:** gap | deviation | tradeoff | assumption
**Context:** <file:line or module>
**Files:** <paths this decision is visible in>
**Options considered:**
- A: … — pro/con
- B: … — pro/con
**Chosen:** <which, one reason>
**Confidence:** high | medium | low
**What would flip it:** <one concrete signal>
**Reversibility:** GREEN | YELLOW | RED
**Needs human review:** yes | no
---
```

Auto-set `needs human review: yes` when category is `deviation`, or reversibility is `RED` and confidence is below `high`.

Supersede a prior entry by appending a new one that cites its timestamp. Never edit or delete history.

## Wiring

- `/next` Step 5b seeds the file; Step 6 appends as decisions happen.
- End of implementation: print a summary (counts by category + every `needs human review: yes` line) into the PR concerns section (`/create-pr` / `/ship`). One place for reviewers — not a second report.
- A `deviation` the human rejects becomes a `/promote-lessons` candidate.
- Session wrap: `/end-session` lists open human-review flags.

Validate a file with:

```bash
python3 .claude/skills/next-issue/scripts/check-next-issue.py --check-notes docs/plans/<file>.md
```

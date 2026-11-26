---
description: Create a PR with embedded risk score, conventional title, and context-aware checklist. Analyzes the diff to calculate risk (size, complexity, test coverage, dependencies, security) and generates the gh pr create command. Usage: /create-pr [optional: target branch, defaults to develop]
allowed-tools: Bash, Read, Glob, Grep
---

# Create PR

Generate a pull request with embedded risk assessment.

## Step 1 — Determine diff scope

```bash
# Current branch
git rev-parse --abbrev-ref HEAD

# Target branch: $ARGUMENTS is substituted by Claude Code (`${ARGUMENTS:-develop}` is NOT, so it always gave develop)
TARGET="$ARGUMENTS"; [ -n "$TARGET" ] || TARGET=develop

# Verify the target exists locally or on origin; fall back to main only when develop is absent
git rev-parse --verify --quiet "$TARGET" >/dev/null || git rev-parse --verify --quiet "origin/$TARGET" >/dev/null || TARGET=main

# Commit range
git log --oneline $TARGET..HEAD
```

## Step 2 — Gate evidence, then risk assessment

1. **Gate evidence (mandatory, not replaceable by this command):** `/verify pre-pr` must have run on this branch in this session with its own exit codes. If it has not run, or any stack is FAIL/BLOCKED, say so in the output and mark the PR body `Gate: NOT RUN` or `Gate: FAIL` — never write "CI is green" or tick a checklist item from reading the diff.
2. **Fresh evidence:** `python3 .claude/scripts/review_state.py stamp check verify --mode full,pre-pr` must print VALID (the stamp `/verify full` or `/verify pre-pr` writes on PASS; a quick run prints INSUFFICIENT). CHANGED, EXPIRED or MISSING means the gate result no longer describes this tree: re-run `/verify pre-pr` or write `Gate: NOT RUN (stale)`. With the enforcement kit on, `gh pr create` is denied until it is VALID and `review_state.py stamp check review` is VALID too (every reviewer re-reported on the current tree with no blocking findings; this evidence comes only from reviewer reports, never from a hand-written stamp).
3. **Lessons review (every PR; "no new lesson" is a valid outcome):** look back over this branch: user corrections, reviewer findings closed or dismissed (`review_state.py findings list` when the kit is on), fixes that took more than one attempt, and anything that worked unusually well. Route each through `/promote-lessons` Step 1 (avoid X, do Y, because Z → lesson, rule, deterministic control, skill reference or implementation note) and list the outcome in the PR body's Lessons section. Then record that the review ran: `python3 .claude/scripts/review_state.py stamp write lessons --note "<N routed | no new lesson>"`. `gh pr merge` checks it (advisory with the kit off, denied with it on); an edit after the review makes it stale, so review again before merging. Paste every `Needs human review: yes` line from `docs/plans/*-implementation-notes.md` into the PR concerns section.
4. **Risk score:** read `.claude/commands/pr-risk.md` and apply its Steps 2–6 (raw data, the five 0–10 factors, overall score, large-PR detection, context-aware checklist) to the range `$TARGET..HEAD`. That file is the single source of the rubric; do not restate or alter it here.

5. **Phased work under one issue:** only the final PR may close the parent issue. GitHub closes it when a closing keyword (`close`, `fix` or `resolve` and their `-s`/`-d` forms) is followed by `#N` anywhere in a commit message or PR body, even mid-sentence, and when the PR's branch was created with `gh issue develop N` (a linked branch), whatever the body says. Intermediate phases: write `Refs #N`, never a closing keyword next to the number, and create the branch with plain `git checkout -b`. Final phase: `Closes #N`. If a phase closed it early, `gh issue reopen N`.

## Step 3 — Generate PR title

```bash
git log --oneline $TARGET..HEAD
```

Analyze the commits and pick the type that best represents the aggregate change:

| Type | When to use |
|------|-------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code restructuring without behavior change |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `chore` | Tooling, config, dependency updates |

Format: `type(scope): description` — 70 characters max, imperative mood, lowercase after colon.

Examples:
- `feat(auth): add JWT refresh token rotation`
- `fix(api): handle null response from payment gateway`
- `refactor(orders): extract order validation into service`

## Step 4 — Generate PR description

Construct the PR body using the template below, substituting the actual values from Steps 2 and 3.

## PR Description Template

```markdown
## Summary
- [2-4 bullet points describing what changed and why — derived from commit messages and diff]

## Risk Assessment
**Overall Risk**: [🟢 Low / 🟡 Medium / 🟠 High / 🔴 Critical] ([X.X] / 10)

| Factor | Score | Key Signal |
|--------|-------|------------|
| Size | X/10 | N files, N lines |
| Complexity | X/10 | [what drove the score] |
| Test Coverage | X/10 | ratio X.XX |
| Dependencies | X/10 | [what changed] |
| Security | X/10 | [what changed] |

[Include only if 🔴 Critical]: ⛔ **Requires tech lead sign-off before merge**
[Include only if 🟠 High]: ⚠️ **Two reviewers + test evidence required**

## Test Plan
- [ ] [Specific thing to test based on what changed]
- [ ] [Edge case to verify based on what changed]

## Gate
`/verify pre-pr`: [PASS / FAIL / BLOCKED / NOT RUN] — [stacks and exit codes, or why it was not run]; evidence stamp [VALID / CHANGED / MISSING]
Reviewer agents dispatched: [agent → verdict, open MEDIUM/LOW advisories] or "none"

## Rollback
[How to undo: revert commit, feature flag, down-migration (tested?), data repair] — "revert only" is a valid answer for a code-only change

## Performance impact
[Measured before/after, or "none expected: <reason>"; never a guess presented as a measurement]

## Lessons
[Each: avoid X, do Y, because Z → destination] or "No new lesson"

## Pre-Merge Checklist
[the sections generated by `/pr-risk` Step 6 for this diff — only the ones that apply]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Step 5 — Output gh command

Write the body from Step 4 to a file with the Write tool (for example `$TMPDIR/pr-body.md`), then print the complete command. Do NOT run it — let the user run it after review. Never inline the body in double quotes: the shell runs `` `code` `` spans as commands and deletes them (`core-behaviors.md` §5).

```bash
gh pr create \
  --base "$TARGET" \
  --title '<generated title from Step 3>' \
  --body-file "$TMPDIR/pr-body.md"
```

The title is single-quoted so backticks and `$` stay literal; an apostrophe inside it is written `'\''` (close the quote, an escaped quote, reopen).

After the user has run it, watch CI on the new PR: `gh pr checks <PR> --watch --fail-fast --interval 30; echo "CHECKS EXIT:$?"` (gh 2.87: 0 = every check passed, 1 = a check failed or none were reported (read the message), 8 = still pending because the watch was interrupted). Report that exit code; a failure goes to the `iterate-pr` skill. CI that was not watched is reported as NOT RUN, never as green. No hook polls CI for you.

## Step 6 — Output

Print in this order:

1. **Risk assessment summary** — the scored table from Step 2 with the overall level
2. **The full `gh pr create` command** — ready to copy and run
3. **Review recommendations** — which `/review-pr` filters to run based on what changed:
   - Security-sensitive changes → run `/review-pr errors` and dispatch `security-reviewer`
   - Auth / permission changes → run `/review-pr types` in addition to errors
   - High test_ratio gap → run `/review-pr tests`
   - Complex diff (complexity score ≥ 6) → run `/review-pr simplify`
   - Default: run `/review-pr` (all 6 roles)

$ARGUMENTS

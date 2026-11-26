---
name: pr-review
model: opus
description: "Use when reviewing someone else's PR or preparing your own review comments for posting to GitHub. Implements a two-stage approval process — internal rich analysis first, human approval gate, then clean public posting. Nothing posts to GitHub until you explicitly approve. Triggers: \"review this PR\", \"post a PR review\", \"review PR #N\", \"give feedback on PR\", \"submit a code review\", \"pr comment\"."
allowed-tools: Read, Write, Bash, Glob, Grep
metadata:
  triggers: PR review, pull request review, GitHub PR, code review, review PR, post PR comment, PR feedback
  related-skills: receiving-code-review, code-reviewer, verification-before-completion, changelog-generator
  domain: quality
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-15"
---

# PR Review (Two-Stage)

## Iron Law

**NO PR COMMENT POSTED WITHOUT HUMAN APPROVAL FIRST**

Generate internally. Review locally. Approve explicitly. Post to GitHub.

## Why Two Stages

Internal analysis uses rich formatting (emojis, line numbers, full context) optimized for thorough reasoning. Public comments use clean professional language optimized for the PR author. Mixing them leaks internal noise and draft thinking onto GitHub.

## Stage 1 — Internal Analysis

### Step 1: Fetch PR Data

```bash
# PR metadata
gh pr view <PR_NUMBER> --json number,title,body,author,additions,deletions,changedFiles

# Full diff
gh pr diff <PR_NUMBER>

# Existing comments and reviews
gh pr view <PR_NUMBER> --json comments,reviews

# CI status
gh pr checks <PR_NUMBER>
```

### Step 2: Analyze

Read `references/pr-review-checklist.md` and evaluate the PR against all categories.

Optionally run `/review-pr` command on the diff to get structured 6-role findings before writing.

### Step 2b: Identify THE CONVERSATION

Before writing any files, identify the one architectural or design decision in this PR that deserves a real conversation before merging. This is **mandatory** — every non-trivial PR has one.

THE CONVERSATION is not a problem. It is a *decision* — something the author chose that a reviewer should explicitly agree with before the code merges. Examples:
- "This adds a new caching layer — have we decided this is the right place for that abstraction?"
- "This moves retry logic into the service — is that our pattern going forward or a one-off?"
- "This introduces a new dependency — was that evaluated against existing alternatives?"

If the PR is trivially small (typo, config value, one-line fix), state: "No architectural decision requiring discussion."

Include THE CONVERSATION in both `pr/review.md` and `pr/human.md`.

### Step 3: Generate Two Files

**`pr/review.md`** — Internal rich format (never posted):
- Use 🔴🟡🟢 severity markers
- Include code snippets with file:line references
- Write reasoning notes freely — this is for you, not the author
- Include THE CONVERSATION with your internal reasoning about why it matters
- No length limit; be thorough

**`pr/human.md`** — Public clean format (posted after approval):
- Professional, constructive tone
- No emojis, no file:line references, no internal notes
- Lead with one positive observation
- Group issues: Blocking -> Important -> Suggestions
- Include THE CONVERSATION as a clearly labelled section before the decision line
- End with clear decision: Approve / Request Changes / Comment

## Gate — Human Review

Before Stage 2, open both files:

```bash
open pr/review.md   # or: code pr/review.md
open pr/human.md
```

Edit `pr/human.md` as needed. This is the last chance before GitHub sees anything.

## Stage 2 — Public Posting

Choose the appropriate action:

```bash
# Approve the PR + post your comment
gh pr review <PR_NUMBER> --approve --body "$(cat pr/human.md)"

# Request changes + post your comment
gh pr review <PR_NUMBER> --request-changes --body "$(cat pr/human.md)"

# Comment only (no approve/reject decision)
gh pr review <PR_NUMBER> --comment --body "$(cat pr/human.md)"
```

## Inline Comments (Optional)

For specific line-level feedback, create `pr/inline.md` with one `gh api` command per comment. Post each one selectively after Stage 2 — pick only the ones you agree with.

See `references/pr-review-workflow.md` for the full inline comment command format.

## File Structure

```
pr/
  review.md      <- Internal rich analysis (NEVER posted to GitHub)
  human.md       <- Public clean version (posted after human approval)
  inline.md      <- Optional per-line comments (posted selectively)
```

## Related

> For 6-role concern analysis before writing review.md: use `/review-pr` command.
> For when you RECEIVE a review on your own PR: see `receiving-code-review` skill.
> For checking code quality before opening a PR: use `/review-code` command.

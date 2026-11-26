---
description: Sync git worktrees for all open PRs so each branch has its own directory for parallel work without stashing. Usage: /worktree-sync [--new <branch>] (default: sync all open PRs to ./tree/). Optional isolation — not mandatory.
allowed-tools: Bash, Read
---

# Worktree Sync

Create and maintain git worktrees so each open PR branch has its own directory on disk. Isolation is **not mandatory**. **Do not stash**, reset, discard, merge, or commit `.gitignore`. Preserve unrelated staged, unstaged, and untracked files.

## Step 0 — Detect current worktree

```bash
python3 .claude/scripts/check-worktree-isolation.py --detect
```

If `in_linked_worktree` is true, you are already inside a worktree: do not nest another. Report the current branch and stop `--new`. Dirty files listed by `--detect` must still be there when you finish — this command must not touch them.

Before `--new <branch>`:

```bash
python3 .claude/scripts/check-worktree-isolation.py --propose-branch <branch>
```

Exit 1 means a branch-name, directory, or overlapping-file collision. Stop. Do not create the worktree. Multiple agents must not edit the same files in parallel without an explicit human coordination note.

## Step 1 — Determine Mode

If `$ARGUMENTS` contains `--new <branch-name>`: skip to Step 3 (create one new branch + worktree).
Otherwise: run Step 2 (sync all open PRs).

## Step 2 — Sync All Open PR Worktrees

```bash
# Verify GitHub CLI auth
gh auth status

# Create worktree base directory
mkdir -p ./tree

# Create a worktree for each open PR branch
gh pr list --json headRefName --jq '.[].headRefName' | while read branch; do
  safe_name="${branch//\//-}"
  branch_path="./tree/$safe_name"
  if [ ! -d "$branch_path" ]; then
    echo "Creating worktree: $branch → $branch_path"
    git fetch origin "$branch" 2>/dev/null || true
    git worktree add "$branch_path" "$branch"
  else
    echo "Already exists: $branch_path (skipping)"
  fi
done

git worktree list
```

After sync: open each `./tree/<branch>/` in a separate terminal or editor window. Each directory is a full independent working copy sharing the same `.git` object store.

## Step 3 — Create New Branch + Worktree

Use when starting a new feature branch and wanting an isolated working directory from day one.

```bash
# branch_name comes from --new argument (e.g. --new feature/auth)
branch_name="<extract branch name from $ARGUMENTS after --new>"
repo_root=$(git rev-parse --show-toplevel)
parent_dir=$(dirname "$repo_root")
safe_branch="${branch_name//\//-}"
worktree_path="$parent_dir/$(basename "$repo_root")-$safe_branch"

python3 .claude/scripts/check-worktree-isolation.py --propose-branch "$branch_name" --propose-path "$worktree_path"
# only if that exited 0:
git worktree add -b "$branch_name" "$worktree_path"
echo "Worktree created at: $worktree_path"
echo "Open this directory in a separate editor window to work in parallel."
git worktree list
```

Never `git stash`, `git reset --hard`, `git merge`, or commit `.gitignore` from this command. Baseline checks after creation are the stack's existing tests (`/verify` in the new worktree), not a second workflow.

## Step 4 — Prune Stale Worktrees

If a worktree directory was deleted manually, clean up the dangling reference:

```bash
git worktree prune
git worktree list
```

$ARGUMENTS

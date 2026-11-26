# `/next` — discovery adapters

Collect candidate work items, then rank with `scripts/check-next-issue.py --pick`. Never hardcode owner, repo, project number, or a product path.

## Candidate JSON

Each item:

```json
{
  "id": "42",
  "number": 42,
  "title": "Add login",
  "source": "github-issue",
  "status": "todo",
  "assignees": [],
  "blocked_by_open": [],
  "labels": ["area:backend"],
  "wave": null,
  "is_epic": false,
  "verification": "unknown"
}
```

`status`: `todo` | `in_progress` | `in_review` | `done` | `blocked`.  
`verification`: `unknown` | `pass` | `fail` | `not_run`.  
`source`: `github-project` | `github-issue` | `local-plan` | `session-task` | `git-branch`.

Write the list to a temp file and run:

```bash
INVOKER=$(gh api user --jq .login 2>/dev/null || git config user.login || git config user.name)
python3 .claude/skills/next-issue/scripts/check-next-issue.py \
  --pick /tmp/next-candidates.json --invoker "$INVOKER"
```

`--limit` on `gh project item-list` / `gh issue list` is a **hard cap**. If the returned count equals the limit, raise it and re-run — truncated boards hide Todo items.

## Adapter 0 — resume current work (always first)

Before any board query:

1. Current branch name containing `#N` or `issue-N` → candidate `git-branch`, `status=in_progress`.
2. Uncommitted or unpushed work on a non-default branch → same.
3. Session TaskList in-progress items → `session-task`.
4. Newest `docs/plans/*issue-<N>*.md` on this branch that is not marked shipped → `local-plan`.
5. If a GitHub Project item is `In Progress` and assigned to the invoker → `github-project`.

Mark `verification=fail` when this session (or CI on the open PR) has a failing `/verify`, Maestro, Playwright, or unit run for that item.

## Adapter 1 — GitHub Project (optional)

Use only when config exists. Load **human-readable** values, then fetch GraphQL IDs live — never pin node IDs.

Search, in order:

1. `docs/github-issues-strategy/repo-config.md` for `OWNER=`, `REPO=`, `PROJECT_NUMBER=`
2. `.github/project-config.md` with the same keys
3. `gh repo view --json owner,name` plus `gh project list --owner <owner>` if the operator named a project

If any of those are missing, skip this adapter (do not invent a project).

Wave field: if the project has a field named `Wave` (or `wave`), resolve the **lowest-numbered wave that still has Todo items**. If `--wave N` was passed, use that wave. If there is no wave field, leave `wave` null.

Status mapping (case-insensitive): `Todo` → `todo`, `In Progress` → `in_progress`, `In Review` → `in_review`, `Done` → `done`, `Blocked` → `blocked`.

## Adapter 2 — GitHub Issues (optional)

When `gh` works but no project is configured:

```bash
gh issue list --state open --limit 100 --json number,title,assignees,labels,milestone
```

Parse each body for `Blocked by: #N` lines. For every cited `N`, `gh issue view N --json state`. Open → put `N` in `blocked_by_open`. Empty `Blocked by` is not a free pass if comments still say the issue is waiting on a decision — read comments before flipping a `blocked` label to ready.

## Adapter 3 — local plans and docs

When GitHub is absent or empty:

- `docs/plans/*.md` with unchecked `- [ ]` items
- `TODO.md` / `BACKLOG.md` at repo root (if present)
- Unchecked items in the current session TaskList

Give these `number=null` and `source=local-plan` or `session-task`. Ranking still applies (blockers, assignee, layer labels if the plan lists them).

## Adapter 4 — none

If every adapter is empty after resume: report `NONE` and stop. Do not invent work.

## Explicit override

`--plan #N` / `/next #N` skips discovery (takeover). Still read the full issue/plan before doing anything else.

## Collecting `blocked_by_open`

1. Declared `Blocked by: #N` in the body.
2. GitHub `blocked` label / project Status `Blocked`.
3. An open linked `[DECISION]` issue mentioned in comments.

Any one of those with an **open** target keeps the item out of the Todo pool.

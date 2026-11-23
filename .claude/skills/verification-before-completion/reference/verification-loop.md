# Verification loop: when to verify, findings ledger, standing habits

This page decides **when** work is verified, never **whether**. Every gate, reviewer and evidence rule in `.claude/rules/verification-and-reporting.md` stays as strict as written. Optimising never means skipping a validation, ignoring a failed test, accepting stale output or marking a gate passed that did not pass. Status: RECOMMENDED PRACTICE (SOURCE-PROVEN on a large multi-stack monorepo; adapt the commands to your repo).

**Core rule:** never repeat work whose inputs have not changed, and never run an expensive gate on a tree that is about to change.

## 1. Order

```
implement → narrow verify (the test file, then the package)
→ review round (all reviewers on a complete implementation)
→ batch the fixes, each with its own positive control
→ scoped re-review (each reviewer re-checks only its own findings)
→ every finding CLOSED
→ FREEZE the tree (code, version bump, CHANGELOG, PR body all done)
→ run each expensive gate the diff can reach, once, serially
→ open the PR
```

- **Cheap tier** (formatter check, linter, analyzer, grep gates, unit tests of the touched package) runs after every edit batch, unscoped.
- **Expensive tier** (full test suites, E2E, Docker rebuilds, live-model evals, MCP validation, Maestro, reviewer subagents) runs only when its inputs changed, and only on a frozen tree.
- Every selection doubt resolves to **more** verification. Print each skip with its reason. If the final full run catches something a scoped run missed, widen the selection rule in the same change.

## 2. Freshness: when a green result still holds

- A gate whose declared input scope is byte-identical to its last GREEN run cannot change verdict. Elapsed time, a new session or an expired sentinel file are not source changes.
- An **under-declared** input scope is a false green (the gate reads a file its scope does not list). When unsure, declare more inputs.
- When the diff since the last green is comments or prose only (zero code lines in the gate's scope), the green holds; say so with the diff that proves it instead of re-running.
- Attribute before re-running: narrowest scope first (test file → package → affected gate → umbrella gate on the frozen tree).

## 3. Heavy gates

- Heavy jobs never overlap. A timing-sensitive failure under load is not evidence until it reproduces on an idle machine.
- Enumerate the sentinel/evidence set from the diff up front, then run the sentinel-writing gates once, last, on the frozen tree.
- Flakes: capture the artifact (trace, log, screenshot), re-run that one test once, and record it as a finding. Never re-run until green.
- A green umbrella command is not admission: a pre-PR hook can still refuse. Never create or `touch` a sentinel by hand, and re-check a delegated `gh pr create` with `gh pr view`.
- A reviewer subagent may hold Write/Edit: run `git status` before and after each round and stage explicit paths, never `git add -A` while a reviewer is live.

## 4. Findings ledger

Reviewer findings recorded only at the end become bookkeeping; recorded on arrival, they bound the next round. Keep one append-only ledger (a TSV or JSON file under a gitignored state directory, or the task list) with: `id | reviewer | severity | status (OPEN/CLOSED/DISMISSED) | summary | closing evidence`.

- **Record each finding as it arrives**, one per entry. Namespace ids per reviewer and round (`sec-r2-1`, `db-r1-3`); never a bare `H1`, and severity goes in its own column.
- **Close against the file:** grep the fix back out of the changed file and name the positive control (`removed the guard → test_x FAILED`). A finding about the environment closes with the output of the command that settles it.
- Dismiss only with a citation (why it is not a defect), never by deleting the entry.
- Do not launch the next review round, and do not report done, while any finding is OPEN. A scoped re-review covers only that reviewer's findings.
- A reviewer-suggested fix gets the same positive control as your own code.

Hook enforcement of this ledger (a SubagentStop recorder, a PreToolUse(Agent) gate on reviewer launches, a bounded Stop gate) is optional; any blocking Stop hook must honour `stop_hook_active` (`.claude/rules/hook-and-gate-authoring.md`).

## 5. Reporting

At a phase boundary: phase · MOVING/FROZEN · changed scope · open findings · results reused (with why they still hold) · results invalidated · next command. After each fix, one line:

```
fix: <what> | invalidates: <gates> | preserved: <gates> | next: <cmd>
```

## 6. Standing habits

- **Check the branch** (`git branch --show-current`) after every squash-merge and before the first write of a new task: `gh pr merge --delete-branch` checks out the base branch.
- **Local commits and healthy containers prove nothing about the PR.** Verify the remote ref (`git branch -r --contains <sha>`) and push again when code lands after the PR is open.
- **A validation or binding change has two sides:** enumerate the producers as well as the consumers, and ask what a removed guard was compensating for.
- **Adding a field:** field-by-field mappers drop it silently. Assert the serialised payload at every hop that rebuilds the object (model, API layer, client `fromJson`).
- **Before deleting an "unused" value,** check whether the expression that produced it had a check or a side effect.
- **Re-verify your own comments after your own fix,** and look up an issue or PR's live state before writing prose about it.
- **A 401 is not proof a credential expired:** confirm with one authenticated call before rotating anything.
- **Empty `docker logs --since` output** on a long-lived container can mean the window is wrong; confirm the window is live before concluding "it did not happen".
- **No GNU-only flags on macOS** (`timeout`, `sed -i` without a suffix, `grep -P`); verify destructive in-place edits by size or diff, not by `tail`.

## 7. Plans: convention first

- A plan task that names a new file path cites a `find`/`ls` result showing the path matches the repo's convention. An issue's suggested path is not evidence; the codebase is.
- **Reuse means fitness, not existence.** "Reuse X" requires reading X and citing what it actually returns or renders (`file:line`). If it does not fit, say so at plan time.
- **A build-new verdict never rests on a truncated search.** Re-run without `| head`, state the count, and search the layer above (a repository-layer search cannot see a service-layer implementation of the same query).

## 8. Writing content through the shell

- File content goes through Write/Edit, not heredocs or `python3 -c "…"`. In a double-quoted shell argument, backticks are command substitution: the shell runs the code span and silently removes it from the text (in `git commit -m "…"` as much as anywhere). Prompt-injection hooks that scan Bash command strings can also block heredoc content.
- Multi-line commit messages → `git commit -F <file>`; PR and issue bodies → `--body-file <file>`.

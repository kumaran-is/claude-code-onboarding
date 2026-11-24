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
- The kit's `verify` stamp (section 4) implements this rule: it is a content fingerprint, so an unchanged tree stays VALID across sessions. Its max-age backstop exists for inputs outside the tree (toolchain, registry, services), not as a substitute for the fingerprint.
- Attribute before re-running: narrowest scope first (test file → package → affected gate → umbrella gate on the frozen tree).

## 3. Heavy gates

- Heavy jobs never overlap. A timing-sensitive failure under load is not evidence until it reproduces on an idle machine.
- Enumerate the sentinel/evidence set from the diff up front, then run the sentinel-writing gates once, last, on the frozen tree.
- Flakes: capture the artifact (trace, log, screenshot), re-run that one test once, and record it as a finding. Never re-run until green.
- A green umbrella command is not admission: a pre-PR hook can still refuse. Never create or `touch` a sentinel by hand, and re-check a delegated `gh pr create` with `gh pr view`.
- A reviewer subagent may hold Write/Edit: run `git status` before and after each round and stage explicit paths, never `git add -A` while a reviewer is live.

## 4. Findings ledger

Reviewer findings recorded only at the end become bookkeeping; recorded on arrival, they bound the next round. Keep one ledger with: `id | reviewer | severity | status | summary | closing evidence`. With the enforcement kit (below) it is `.claude/state/review/<branch>/ledger.json` (ids `F1`, `F2`…, states OPEN / INVESTIGATION_REQUIRED / CLOSED / DISMISSED); without it, a TSV under a gitignored state directory or the task list, append-only.

- **Record each finding as it arrives**, one per entry, severity in its own column. In a hand-kept ledger, namespace ids per reviewer and round (`sec-r2-1`, `db-r1-3`), never a bare `H1`; the kit records reviewer and round itself.
- **Close against the file:** grep the fix back out of the changed file and name the positive control (`removed the guard → test_x FAILED`). A finding about the environment closes with the output of the command that settles it.
- Dismiss only with a citation (why it is not a defect), never by deleting the entry.
- Do not re-dispatch a reviewer while it owns a **blocking** finding (the kit denies it), and do not report done while any blocking finding is OPEN: every open finding in rounds 1–2, only CRITICAL/HIGH from round 3 (see "Bounded re-review"; MEDIUM/LOW then go in the PR body). Other reviewers may run meanwhile; a scoped re-review covers only that reviewer's findings.
- A reviewer-suggested fix gets the same positive control as your own code.

### Closure evidence and escalation

Every close names one evidence class; a finding never closes on "looks fixed".

| Class | Means | Example |
|---|---|---|
| `CONTROL` | A test or check that failed before the fix and passes after | `tests/test_auth.py::test_rejects_unsigned FAILED before, PASSED after` |
| `MECHANISM` | A gate, hook, type or constraint now makes the defect impossible | `NOT NULL` + migration; lint rule now errors on the shape |
| `STATIC` | Verified by reading the code; cite `path:line` | `src/auth/guard.ts:41 now checks audience` |
| `NOCONTROL` | Fixed, but no automated control is possible; say why | copy change in a marketing page |
| `DISMISSED` | Not a defect; the citation says why | reviewer misread a generated file |

A close that does not survive re-verification is recorded as a failed attempt. After **2 failed closes** the finding becomes `INVESTIGATION_REQUIRED`: stop patching, find the root cause (`systematic-debugging`), and close it only with `CONTROL` or `MECHANISM` evidence. This pairs with the 3-attempt hard stop in `first-principles.md`.

### Bounded re-review

The review round is the most reports any one reviewer has made on the branch. Rounds 1–2 block on every open finding; from **round 3 only CRITICAL and HIGH block**. MEDIUM and LOW stay open, are still fixed where cheap, and go into the PR body as advisories. Re-dispatch only the reviewers that own open findings or findings closed since their last report, never the whole panel; run `/verify quick` on the diff's stacks before dispatching any reviewer.

### Enforcement kit (opt-in, per branch)

`python3 .claude/scripts/review_state.py init` turns the kit on for the current branch (or set `CLAUDE_ENFORCEMENT_KIT=1` for every branch); `disable` turns it off. State lives in `.claude/state/review/<branch>/` (gitignored). The hook `.claude/hooks/enforcement-kit.py` is registered for SubagentStart, SubagentStop, PreToolUse (Bash, Agent) and Stop, and is a no-op for the ledger until the kit is on.

| When | What the kit does |
|---|---|
| A reviewer starts (an agent whose frontmatter disallows Write and Edit) | Injects the contract: end the report with `FINDING: <SEVERITY> \| <path:line> \| <summary>` lines or `FINDINGS: none` |
| The reviewer stops | Records each FINDING line (idempotent per `agent_id`). No contract line: sent back once (bounded by `stop_hook_active`), then recorded as a MEDIUM "unparsed report" finding |
| A reviewer is dispatched again | Denied while it owns OPEN or INVESTIGATION_REQUIRED findings: fix, close with evidence, then re-dispatch to verify |
| The session tries to stop | Blocked once while findings block (round rule above); a second stop in a row only warns, so it cannot loop |
| `gh pr create`, `gh pr merge`, `gh api …/pulls` (write) | Needs a VALID `verify` stamp from `/verify full` or `pre-pr` (section 2; a quick stamp is INSUFFICIENT); a merge also needs a VALID `lessons` stamp (the end-of-PR lessons review, `/create-pr` Step 2.3). Kit on, both also need VALID `review` evidence: every reviewer's latest report was recorded by the SubagentStop hook on the current tree fingerprint, none has a blocking finding, and none is older than `REVIEW_STAMP_MAX_AGE_HOURS`. It is derived, never written: `stamp write review` is refused, a hand-made `review.json` is ignored, and Bash or Write/Edit into `.claude/state/` is denied while the kit is on. Kit off: advisory. Kit on: denied unless the command is prefixed with `REVIEW_GATE_OVERRIDE="<reason>"`, and the reason goes in the PR |
| UI files changed (always on) | One reminder per tree state when web UI or Flutter `lib/` files changed without a VALID `ui-web` / `ui-mobile` stamp: run Playwright (web) or Maestro (Flutter Android/iOS), or report NOT RUN / BLOCKED. Kit off: a `systemMessage`; kit on: one bounded block |

Ledger commands: `review_state.py findings list | add | close ID --class … --evidence … | fail ID --note … | dismiss ID --reason … | blocking | rereview`. Stamps: `review_state.py stamp check review` (read-only; see the PR row above), `stamp write <verify|lessons|ui-web|ui-mobile> [--mode <full|pre-pr|…>] --note "<command, counts>"` after the check PASSED, `stamp check <name> [--mode full,pre-pr]` (VALID / INSUFFICIENT / CHANGED / EXPIRED / MISSING / UNKNOWN). A stamp is a content fingerprint of the files in its scope (`ui-*` stamps cover only UI files), so it goes stale when content changes, not on a timer; `REVIEW_STAMP_MAX_AGE_HOURS` (default 72) is the backstop. Writing a stamp without running the check is a false completion claim (`verification-and-reporting.md`). `verify`, `lessons` and `ui-*` stamps are honour-system by design: a stamp written in one call and used in the next passes the local gate (the same pair in one compound command is denied). CI re-runs the checks and is the real gate. The `verify` stamp covers every untracked, non-ignored file too: write PR and commit bodies to `$TMPDIR` or the session scratchpad, never into the work tree, or the stamp goes CHANGED right before `gh pr create`. Limits: the PR gate parses the command text. It unwraps `bash`/`sh`/`zsh -c`, `eval`, `env -S`, runners such as `xargs`, `timeout`, `nice` and `sudo`, quoted `$(…)` and backticks, and computed names such as `$(which gh)` or `$GH`; it does not see script files, `python -c`, or shell aliases and functions defined in an earlier call. It is defence in depth against forgetting, not a sandbox: CI and branch protection stay the enforcement of record.

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

## 9. Paired manual QA (human + agent)

For a user-facing change that automated suites cannot judge (copy, feel, flows across devices), run a short paired session instead of an unstructured "click around":

1. **Charter (agent, 5 min):** the change, the risk list from the diff, the target (web: Playwright CLI; Flutter mobile: Maestro on an emulator or device, `testing-tool-selection.md`), the accounts and seed data, and 5–10 numbered scenarios including at least one error, one empty and one permission-denied path.
2. **Drive (human or agent):** one scenario at a time; the other side records. The agent captures evidence for each (screenshot, trace or Maestro output) and never marks a scenario passed on the human's word alone without an artifact, or on its own reading of code.
3. **Log each finding** in the ledger format (§4): `FINDING: <severity> | <screen or path:line> | <observed vs expected>`, plus the reproduction steps and the evidence file. Opinions on taste are LOW unless they block a task.
4. **Close:** every scenario is PASS / FAIL / NOT RUN (with why); FAIL findings get a regression test where one is possible (`systematic-debugging` Phase 4). Write the `ui-web` / `ui-mobile` stamp only after the automated suite passes too: a manual session is not a substitute for it.


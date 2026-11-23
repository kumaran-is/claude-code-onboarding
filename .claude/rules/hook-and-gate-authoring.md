---
paths:
  - ".claude/hooks/**"
  - ".claude/scripts/**"
  - ".github/workflows/**"
---

# Hook and gate authoring guardrails

Path-scoped: loads only when hook, script or workflow files are touched. A gate that cannot fail, or whose failure the model never sees, enforces nothing. Model implementations: `post-edit-format.sh` (check-and-report), `post-edit-python-lint-advisory.sh` (check-only advisory), `pre-bash-guard.py` (blocking, parse-based).

- **Delivery contract.** The stdout/stderr text of an exit-0 hook is NOT shown to the model. Advisories go out as `hookSpecificOutput.additionalContext` JSON (`PreToolUse` / `PostToolUse`) or `systemMessage`; blocking is exit 2 with the reason on stderr. Build JSON with `jq -n --arg`, never by `echo`/`sed` (a backslash or tab in a message makes invalid JSON).
- **Block only deterministic, safe shapes.** Heuristic or noisy checks are advisory and exit 0. Fail open when `jq` or the checker is missing, but say so once (throttle with a marker file in `$TMPDIR`); a hook that silently no-ops looks identical to one that works.
- **Never auto-fix inside an edit hook.** Check-only. `ruff check --fix` has deleted an import added one edit before its first use.
- **Every hook has `--selftest`:** control 0 is `bash -n` on itself; at least one positive (known-bad input must be flagged) and one negative (clean input must be silent) control; assert on message CONTENT, not only exit status (a crash also exits non-zero). Zero findings needs a positive control that proves the scan can see; a scan that matched zero files fails. Mutate the hook once (revert the fix) and confirm a control fails. Reusable harness and pitfalls: `.claude/skills/verification-before-completion/reference/positive-control-harness.md`.
- **Bash 3.2 compatible (macOS).** POSIX `grep`/`sed`/`awk` only: no `grep -P`, no `timeout`, no `mapfile`, no `${var,,}`. Under `set -e` a BSD `grep -P` error kills the hook (exit 2) on every edit; prefer `set -uo pipefail` and handle statuses explicitly.
- **Read the tool's own exit code.** `out=$(cmd 2>&1); rc=$?`, never `cmd | head; if [ $? ...` (that tests `head`). `grep -c` prints `0` AND exits 1 on no match, so `$(grep -c ... || echo 0)` yields `"0\n0"`: use `|| true` then `${n:-0}`.
- **`set -o pipefail` + `producer | grep -q`** can report "no match" via SIGPIPE (141) on large output. Capture into a variable or use a here-string, and size one selftest fixture large enough to reach it.
- **A scan that aborts or finds zero inputs must fail, not report clean.** Check status in the parent shell (not inside `< <(...)`), and print what was scanned.
- **Widening or narrowing a detector** (to kill a false positive) is the likeliest moment to create a false negative: re-run on the live tree, diff the finding set, add a control for the new scope and prove it fails when the change is reverted.
- **Pin the interpreter** for any gate that parses the target language. `ruff format` at `target-version = "py314"` writes `except A, B:` (PEP 758), a SyntaxError on 3.13 and older, so an `ast.parse` gate under an older `python3` inspects nothing. Guard `sys.version_info` in the wrapper and name the cause; CI uses `python-version-file`.
- **A wrapper fails when a sub-step fails.** A "skipped" sub-step that still writes the success sentinel proves the gate ran, not that it passed. Never turn a non-zero exit into a friendly message.
- **Diff-aware gates are vacuously green on uncommitted work** (no changed files). State what the gate saw; run it against the real change set.
- **Thresholds:** a GOAL warns, a CEILING fails; ceilings only fall; allowlist entries are added with a written reason and only ever removed. A gate that cannot go green is deleted or fixed, not ignored.
- **Blocking hooks block their own test harness.** Put controls in a script file, feed probes as JSON on stdin, build probe strings from variables, and include negative controls.
- **Blocking Stop hooks must bound themselves** (iteration cap or `stop_hook_active` check) so they cannot loop; `stop-ralph-loop.sh` uses a counter.
- **One `_cleanup()` registered once** for `EXIT INT TERM`; `trap` replaces rather than chains.
- **A consistency check between two sources is a biconditional:** check A⊆B and B⊆A; a one-way check reports clean while the other half drifts.
- **A gate that greps a file must model that file's format:** prose mentioning the token satisfies a naive grep and quoting defeats it; parse the structure (YAML/JSON/table) or anchor the pattern.
- **A budgeted gate's baseline is seeded from the merge target,** never from your branch (otherwise every regression on the branch becomes the new allowance).
- **Preflight health is scoped to what the caller depends on:** derive the expected set from the same source that provisions it, name each missing instance, and prove the arm engages on live data (an empty derived set silently degrades to the weak check).
- **A gate that serves an artifact over a port proves identity, not reachability:** stamp a run-unique token into the build and require the server to return it; check liveness after the probe; one lsof per port.
- **A probe that emulates a gate sources the gate's helpers** (or calls the gate with different inputs); a re-implementation drifts.
- **A prose scraper matches a shape, not a finding:** ordinary words (HIGH, CRITICAL) in tables become false findings; anchor on the reviewer's own finding format and pin negative controls.
- **CI workflows:** the same rules apply to `run:` steps (read the tool's exit code, no `| tail` after the gate), and a path-filtered workflow that runs tests must also trigger on `conftest.py`, `pyproject.toml` and the lockfile. See `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.

Evidence rules for claims about gates live in `verification-and-reporting.md`.

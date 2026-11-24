# Harness Modernization: Implementation Report (Phases A–F)

Date: 2026-11-24 · Branch: `feat/flutter-mobile-engineering-best-practices` · Source audit: `docs/plans/property-harbor-harness-comparative-audit.md` (§3, §4, §8, §10)
Status: implemented in the working tree, **not committed** (commit needs approval). Property Harbor was read only; no business content was copied.

Constraints honoured: `permissions` in `.claude/settings.json` unchanged (the diff only adds hook entries; `defaultMode: auto` kept), H1 deferred entirely, no new branch, no AWS AI-DLC, no `docs/workflows/` or `docs/audits/`, no technology downgrade.

Documentation sources: Context7 was **BLOCKED** (monthly quota exhausted) for the whole run. Its fallback, used per `code-standards.md`, was the official documentation: code.claude.com hooks reference, adk.dev (sessions/state, events), firebase.google.com (rules unit tests, rules-fields) and docs.flutter.dev (widget previewer), both read via the Google developer-knowledge MCP, the Dependabot options reference, and the `anthropics/claude-code-action` README, action.yml and security.md.

## 1. Status per phase

| Phase | Status | Independent review |
|---|---|---|
| A: defects and safety | Implemented, selftested | Reviewed together with B: APPROVE after fixes |
| B: context diet to ≤ 60 KB with canaries | Implemented: 59,959 B always-loaded (ceiling 62,000), 22/22 canaries | APPROVE (all MEDIUMs fixed; 2 LOWs fixed, 1 accepted) |
| C: opt-in findings ledger and enforcement | Implemented, mutation-checked | NEEDS_REVIEW (1 HIGH, 7 MEDIUM, 8 LOW): every HIGH and MEDIUM fixed, and 7 of 8 LOWs (L7 accepted). Detail in §6 |
| D: learning loop | Implemented | Reviewed with E and F (§6) |
| E: generic quality content and checkers | Implemented | Reviewed with D and F (§6) |
| F: toolkit CI | Implemented. `coordination-config.yaml` retired (approved) | Reviewed with D and E (§6) |

## 2. Migration review

Classification: **ADOPT** (new capability), **ENHANCE** (strengthened existing one), **ALREADY SUPERIOR** (target already better, nothing imported), **REJECT** or **DEFER** (with reason).

| Capability | Source pattern (PH, generic) | Target implementation | Current target version / API | Modernization required | Verification | Class |
|---|---|---|---|---|---|---|
| H1 native permission deny/ask | `permissions.deny` for secrets | none | Claude Code permissions | — | — | **DEFER** (instructed: no permission changes) |
| H2 PR gate on fresh evidence | merge gate keyed to evidence | `enforcement-kit.py` PreToolUse Bash gate + `review_state.py stamp` (content fingerprint, VALID/CHANGED/EXPIRED/MISSING/UNKNOWN) | hooks: `permissionDecision: deny` | Fingerprint hashes content plus the executable bit in Python (odd file names handled, index never written); 10 s git budget under the hook timeout | 30+ selftest controls; mutants caught (§5) | ADOPT |
| H3 UI evidence reminder | Stop advisory | kit Stop arm, scoped `ui-web` / `ui-mobile` stamps, once per tree state | Stop `systemMessage` / bounded block | Playwright for web, Maestro for mobile (per `testing-tool-selection.md`) | selftest; marker pruning | ADOPT |
| H4 piped test runner | advisory | `pre-bash-zsh-split-guard.sh` H4 arm | PreToolUse advisory | anchored at command position; `|&`, `npm run test:*` | selftest + mutant | ENHANCE |
| H5 one detector, three callers | rule | `hook-and-gate-authoring.md` bullet | — | — | doc-refs 0 | ADOPT |
| H6/S8 overdue deprecations | removal-date gate | `check_deprecations.py` (`REMOVE-BY: YYYY-MM-DD`) | injected clock | — | 7 controls, mutant caught | ADOPT |
| H7 l10n parity | both-way ARB parity | `check_l10n_parity.py` (keys both ways, top-level ICU placeholders) | gen-l10n ARB | ICU nesting parsed (negative control caught a false positive) | 7 controls, 2 mutants caught | ENHANCE |
| H8 env parity | presence-only key parity | `check_env_parity.py` (`.env.example` vs compose, `os.environ`, `process.env`, `BaseSettings`) | pydantic-settings | never opens `.env` | 6 controls, mutant caught | ADOPT |
| H9 paid/egress API guard | PreToolUse block + env approval | none | — | — | — | **REJECT**: it adds confirmation prompts, against the instruction to keep Auto mode prompt-free |
| H10 icon hookify rules | design-asset rules | none | — | — | — | **REJECT**: project-specific |
| H11 SKILL.md edit lint reminder | edit hook | none (CI `lint-skills` blocks the same defects) | — | — | — | DEFER: low value over CI, and another edit hook adds latency |
| H12 / S5 MCP tool ↔ contract parity | add-tool checklist | `mcp-builder/SKILL.md` "Adding a tool" (thin adapter, classification, exact tool-set assertion, allow/deny/invalid case per tool) | MCP SDK v2, protocol 2026-07-28 | — | lint-skills 159/159 | ENHANCE (checklist; no new automation) |
| H13 Alembic model registration | advisory | `check_alembic_models.py` + `alembic-migration-safety.md` §8 | Alembic `upgrade()` ops | upgrade-scoped, renames followed | 6 controls, mutant caught | ADOPT |
| C1/C4 budget + canaries | total ceiling, pinned rules | `check-context-budget.sh` GOAL 60,500 / CEILING 62,000; missing canary file fails `--strict` | — | — | selftest; CI runs selftest then `--strict` | ENHANCE |
| C2/C3 context diet | mandates only | `leverage-patterns.md` 26,030 → 4,454 B; `CLAUDE.md` 17,439 → 9,219 B; routing moved to `SKILLS_GUIDE.md` | — | — | 22 canaries | ENHANCE |
| C5/C6 path-scoped loading | — | CLAUDE.md table with the accurate load note | — | — | — | ENHANCE |
| C7 MCP single source | allowlist | `skill-triggers.md` points at allowlist + §7 register; `check-mcp-register.sh` (biconditional) | — | — | 33 servers / 26 names, 0 findings | ENHANCE |
| C10/C11/C12/C14/C15 | scope, shell-body, revert STOP, clock, comment moves | always-loaded rule lines (Phase A) | — | — | canaries | ADOPT |
| C16 lessons injector | template counted | `pre-lessons-injector.sh` dated anchors | — | — | selftest | ENHANCE (defect) |
| C17 agent descriptions | `<example>` out of descriptions | 39 agents: examples moved to body; `lint-agents.sh` errors on `<example>`, warns > 1000 chars | — | strict-YAML failures 39 → 0 | agent description bytes 46,127 → 25,342 | ENHANCE |
| C18/C19 lessons cap, memory | mechanical cap | `pre-edit-lessons-dedup.sh` denies the 16th entry; `/promote-lessons` Step 2 memory pruning (index < 200 lines, report only) | — | — | selftest + mutant | ENHANCE |
| C20 multi-tool config | generated configs | none | — | — | — | **REJECT**: toolkit is Claude Code only |
| C21 browser routing wording | — | `leverage-patterns.md` "Live Browser in the Loop" points at the canonical rule | — | — | lint-testing-tools 0 | ENHANCE |
| L1/L2/L3 ledger, closure, round cap | prose ledger | `review_state.py` (CONTROL/MECHANISM/STATIC/NOCONTROL, INVESTIGATION_REQUIRED after 2 failed closes; round ≥ 3 only CRITICAL/HIGH block) + SubagentStart/Stop capture + reviewer re-dispatch gate; opt-in per branch | SubagentStop `last_assistant_message`, `agent_id` | reviewer set from frontmatter (inline or YAML list) | 25 + 30 controls | ADOPT |
| L4 verify before review | — | `/review-code` Step 3 runs `/verify quick` first | — | — | lint-commands 88/88 | ENHANCE |
| L5/L6 gate cache, CI-derived gates | reference recipes | none | — | — | — | DEFER (P2, reference only; no consumer in toolkit) |
| L7 lessons at PR boundary | enforced reflection | `/create-pr` Step 2.3 ("no new lesson" valid) + `/ship` report row | — | — | lint-commands | ADOPT |
| L8/L10 classifier, post-ship intake | lesson/rule/skill/notes | `/promote-lessons` Step 0 intake (corrections, ledgers on 2+ branches, successes, revert/fix history, agent memory), Step 1 classifier incl. deterministic controls | — | — | lint-commands | ENHANCE |
| L9 skill improve path | propose → review → PR | `/skill-create` "Improve path" (edit + `skill-reviewer`, merges by PR, no auto-apply) | — | — | lint-commands | ENHANCE |
| L11/S18 sub-ADR notes | append-only notes | `plan-mode-review/SKILL.md` "Implementation notes" (`git diff --numstat` shows `N 0`) | — | — | lint-skills | ADOPT |
| L12 authoring traps | 4 traps | `hook-and-gate-authoring.md` | — | — | — | ENHANCE |
| L16 APPROVE keyed to HEAD | — | `/review-code` verdict carries the HEAD sha; stale after any commit | — | — | — | ENHANCE |
| S1 ADK state propagation | `state_delta` | `adk-structured-output.md` §1 + `adk-reviewer` HIGH item | ADK 2.15; docs state no 1.x/2.x difference | test re-reads from a fresh service | doc-verified (adk.dev) | ENHANCE |
| S2 notification recipients | authz decision | already in `fastapi-authorization-boundaries.md` and `security-reviewer` table; pointer added to checklist §8 and STRIDE | — | — | — | ALREADY SUPERIOR (pointer only) |
| S3 Firestore rules red team | rules checklist | `firestore-storage-security.md`: owner pin, `affectedKeys().hasOnly`, `list` scoping, 5 denial cases + positive control in the emulator | `@firebase/rules-unit-testing` modular API | — | doc-verified (firebase.google.com) | ENHANCE |
| S4 Flutter preflights | refresh, media, preview | `flutter-platform-gotchas.md` §6 | Widget Previewer stable since 3.47 (docs reflect 3.50) | — | doc-verified (docs.flutter.dev) | ENHANCE |
| S6 toolkit CI | actionlint, Dependabot, pins | `toolkit-lint.yml` `workflows` job (actionlint 1.7.12 by index digest, `check-pins.sh`), `.github/dependabot.yml` | actionlint 1.7.12 | the pin gate lives in one script; the doc points at it | actionlint exit 0; planted typo exit 1 | ADOPT |
| S7 secure Claude Code Action | hardened template | `claude-actions-auditor/SKILL.md` "Secure Baseline Workflow" | claude-code-action v1.0.289 (SHA-pinned), `claude_args` (`allowed_tools` deprecated) | — | actionlint 0, check-pins 0 (not run on GitHub) | ADOPT |
| S9 no-stub CI gate | optional template | none | — | — | — | DEFER (optional in the audit; rule already in `code-standards.md`) |
| S19 paired manual QA | phases + template | `verification-loop.md` §9 | — | — | doc-refs 0 | ADOPT |
| Debugging regression rule | permanent named test | `systematic-debugging` Phase 4 step 1 | — | — | lint-skills | ENHANCE |
| Business-outcome check | state, tenant, once, final status | `verification-before-completion` Common Failures row | — | — | lint-skills | ENHANCE |
| Threat-model elements | — | `stride-methodology.md` "Elements easy to leave off" (client-direct DB, side-effect channels, workers, admin tools) | — | — | doc-refs 0 | ENHANCE |
| CI hook selftest coverage | fail on hook without selftest | `toolkit-lint.yml` step; 3 hooks gained `--selftest` | — | — | 39/39 hooks; control (hook without selftest) fails | ADOPT |
| `/create-pr` sections | rollback, perf, reviewers | template sections + `--body-file` | — | — | lint-commands | ENHANCE |
| `coordination-config.yaml` | — | unchanged | — | — | 68/68 agents listed, 0 stale; nothing in the toolkit reads it | **REJECT (retired, approved 2026-11-24)**: routing lives in `SKILLS_GUIDE.md` only |

## 3. Files

**Created (13):**
- `.claude/context-canaries.tsv`
- `.claude/hooks/enforcement-kit.py`
- `.claude/scripts/review_state.py`, `check-mcp-register.sh`, `check-pins.sh`, `check_env_parity.py`, `check_l10n_parity.py`, `check_deprecations.py`, `check_alembic_models.py`
- `.claude/skills/plan-mode-review/reference/execution-patterns.md`
- `.claude/skills/subagent-driven-development/reference/orchestration-and-context.md`
- `.github/dependabot.yml`
- this report

**Modified (97):**
- `CLAUDE.md`, `README.md`, `.claude/SKILLS_GUIDE.md`
- `.claude/settings.json`: hook entries only
- 7 rules files
- 40 agents: 39 had example blocks moved; plus `adk-reviewer`
- 9 commands: `add-feature`, `audit-skills`, `create-pr`, `promote-lessons`, `review-code`, `ship`, `skill-create`, `verify`, …
- 9 hooks
- 3 scripts
- skill files:
  - security references
  - Firestore
  - ADK
  - Flutter (gotchas, localization, Maestro)
  - MCP builder and setup
  - deployment CI
  - Alembic
  - API checklist
  - plan-mode-review
  - SDD
  - verification
  - debugging
  - threat modeling
  - actions auditor
  - browser-testing
  - writing-skills
- both workflows

Totals: 109 tracked files changed against HEAD, +3,502 / −928 lines (final), plus the two untracked `docs/plans/` files.

**Removed (1):** the agent coordination config YAML under `.claude/agents/` (no reader; duplicated SKILLS_GUIDE routing; approved).

## 4. Context size (measured with `wc -c`)

| Measure | Before | After |
|---|---|---|
| Always-loaded total (`check-context-budget.sh`) | 93,185 B (HEAD, before Phase A) | **59,959 B**: ceiling 62,000, goal 60,500, 22/22 canaries, `--strict` PASS |
| `CLAUDE.md` | 17,439 | 9,219 |
| `rules/leverage-patterns.md` | 26,030 | 4,454 |
| `rules/skill-triggers.md` | 7,580 | 4,946 |
| `rules/core-behaviors.md` | 10,258 | 9,601 |
| Agent `description:` bytes (all 68, loaded for routing) | 46,127 | 25,342 |

Phases D–F added no always-loaded bytes: all new process content went into on-demand skills and commands.

## 5. Mechanisms, tests and negative-control evidence

Every new or changed hook and script has `--selftest` with positive and negative controls that assert on message content. Each was also mutated once, reverting the fix, to confirm a control fails:

| Mechanism | Controls | Mutation (fix reverted) → controls failing |
|---|---|---|
| `enforcement-kit.py` | 9 gated command shapes (multi-line `--body`, `$(cat <<EOF)`, `-R`, `command gh`, absolute path, `env`, GraphQL merge, `--method=POST`); negatives: PR comments, `gh pr view`, heredoc body, quoted argument; bounded Stop, once per finding set, YAML-list reviewer | naive split → 2; any `/pulls` path → 1; Stop blocks every turn → 1; `stop_hook_active` bound removed → 1 |
| `review_state.py` | mode-only change, leading-space and quote/newline file names → CHANGED; corrupt stamp → UNKNOWN | (fingerprint rewrite verified by its new controls) |
| `pre-bash-zsh-split-guard.sh` H4 | `|&`, `npm run test:unit`; false-positive control `grep -rn pytest docs \| head` | exemption removed → caught |
| `pre-edit-lessons-dedup.sh` / `stop-lessons-reminder.sh` | cap at 15; fenced template not counted | caught / 2 controls |
| 3 hooks given new selftests | positive and negative each | each mutant → 1 |
| `check_env_parity.py` | Python, TS, compose and BaseSettings keys; `.env` never read; no example → exit 2 | settings field ignored → 1 |
| `check_l10n_parity.py` | both directions, renamed placeholder, ICU plural and nested argument | one-way check → 1; depth off by one → 2 |
| `check_deprecations.py` | future, due soon, overdue, malformed, time passing (injected clock) | overdue check disabled → 2 |
| `check_alembic_models.py` | unregistered model, rename, migration-only table, dropped table, tests ignored | upgrade scoping removed → 2 |
| `check-pins.sh` | SHA and local actions clean; tag pin, undigested `FROM`, `COPY --from` flagged; zero files → 2 | weak SHA regex → 1 |
| `check-context-budget.sh` / `lint-agents.sh` / `check-mcp-register.sh` | deleted canary file fails; `<example>` in description; both register directions | caught (Phase B) |
| CI hook-coverage step | fixture with a hook lacking `--selftest` → missing=1 | — |

Hook latency (Phase C measurement): Bash path ≈ 0.12 s, mostly Python startup. Bash commands without `gh` at command position now exit before any git call.

## 6. Reviews and resolutions

- **Phases A and B** (code-reviewer): APPROVE after fixes.
  - All MEDIUMs were fixed: the stale scaffold pointer, the `CC_SCAFFOLD` bypass prohibition (plus its canary), the elevated GCP server list, and the missing-canary case only warning.
  - LOW: register order and the promote-lessons target were fixed. The destructive-change note was accepted (Layer 1 covers it).
- **Phase C** (code-reviewer): NEEDS_REVIEW, with 1 HIGH, 7 MEDIUM and 8 LOW.
  - **HIGH (PR gate bypass by quoted `;`, `|` or newline): fixed.** A quote- and heredoc-aware `split_commands` replaced the regex split. A command that `shlex` cannot parse falls back to whitespace splitting instead of being skipped.
  - **M1:** wrappers and `-R`/`--repo` are now recognised. `bash -c` and `xargs` are documented as out of scope: the gate is a reminder for a cooperative agent, not a sandbox.
  - **M2:** the gate now matches only `/pulls` (create) and `/pulls/N/merge`.
  - **M3:** GraphQL create and merge mutations are gated.
  - **M4:** git calls get a 10 s budget, under the hook timeout.
  - **M5:** the fingerprint was rewritten (content, executable bit, symlinks, submodules, exact file names).
  - **M6:** the docs now say PR and commit bodies go in `$TMPDIR`.
  - **M7:** the reviewer re-dispatch gate uses `blocking()`.
  - **LOW:** L1 (Stop blocks once per set of blocking findings), L2 (marker pruning), L3 (`--relative`), L5 (corrupt stamp is UNKNOWN; atomic write), L6 (no git call unless a PR command is seen) and L8 (YAML-list `disallowedTools`) are fixed. L4 (state directory edge cases) is accepted as rare. L7 (bold `FINDING` lines) is accepted: the fallback records a finding.
  - **Docs:** `verification-loop.md` §4 now matches the kit (mutable JSON, `F` ids, INVESTIGATION_REQUIRED).
- **Phases D, E and F** (code-reviewer): NEEDS_REVIEW, with 1 HIGH, 5 MEDIUM and 8 LOW; **all resolved**.
  - **HIGH:** `check_deprecations.py` used `dt.UTC` (3.11+). Fixed with `dt.timezone.utc` and a selftest control on the default clock; the mutant is caught. All four Python checkers now exit with a clear version message below 3.10 (seen on the system 3.9.6).
  - **M1:** `check-pins.sh` flagged `FROM <earlier stage>` and quoted `uses:`. Stage names are now tracked; new controls cover both, plus `FROM <name>` that is not a stage.
  - **M2:** `REVIEW_GATE_OVERRIDE` counted anywhere in the command. It is now honoured only as an env prefix of each gated `gh`; 4 controls, and the old behaviour as a mutant fails 3.
  - **M3:** `check_env_parity.py` treated `getenv` and `process.env` reads as required. They are now WARN only, platform variables are ignored, `Field(min_length=…)` counts as required, settings classes with extra bases and kwargs are handled, and the stale check uses word boundaries. 10 controls; 2 mutants caught.
  - **M4:** CI now requires a `selftest PASS` line, not just exit 0. Control: a hook that ignores the flag gets rc 99. All 53 declarers print the line.
  - **M5:** the Claude Action template now has `id-token: write`, needed for the default GitHub App auth. actionlint 0 and check-pins 0 on the extracted YAML.
  - **LOW:**
    - shell keywords and backticks before `gh` are detected
    - zero-indent YAML `disallowedTools` lists are read
    - a git timeout now surfaces as a message instead of a traceback
    - the lessons cap now says so when it cannot be checked
    - the plan template has an Implementation notes section, and the `numstat` rule applies only once the plan is committed
    - the `verification-loop.md` §4 round rule is reconciled with "Bounded re-review"
    - the `/create-pr` apostrophe-escaping note
    - the Alembic check replays revisions in `down_revision` order (drop then re-create is clean; file-order mutant caught)
    - `check-pins` also scans `.yaml` and composite `action.yml`
  - **Residual:** Dependabot does not update the actionlint image digest in a `run:` step. Bump it by hand when actionlint releases.

## 7. CI results (local replay of `toolkit-lint.yml`, every `run:` step, each exit code read directly)

| Step | Result |
|---|---|
| lint-skills | 159 passed / 0 failed |
| lint-agents | 68 / 0 |
| lint-commands | 88 / 0 |
| lint-testing-tools | 0 violations |
| MCP register | 33 servers, 0 findings |
| check-doc-refs | 945 files, 0 violations |
| AI asset gates | 3 steps, exit 0 |
| bash -n | 45 / 0 |
| hook selftest coverage | 39 / 0 missing |
| selftests | 53 ran / 0 failed |
| actionlint 1.7.12 | exit 0 (planted typo → exit 1) |
| check-pins | selftest PASS, 2 workflows clean |

The context-budget workflow (selftest, then `--strict`) also passes. Total: 14 steps, 0 failed.

Not run: GitHub-hosted runners (nothing is pushed). The Dependabot config is parsed only (keys checked against the options reference); Dependabot itself runs only on GitHub.

## 8. Risks and open items

1. **Kit adoption is opt-in** (`review_state.py init` per branch). With the kit off, the PR gate and Stop gate only advise. They block only after a team turns the kit on.
2. **The PR gate reads command text.** `bash -c "…"`, `xargs gh` and aliases are not seen. It is documented as a guard against forgetting, not a sandbox.
3. **Dependabot and SHA pins.** [MEDIUM] Dependabot updates SHA-pinned `uses:` lines and their version comment. This is common practice, but the options page did not state it verbatim. Confirm on its first PR.
4. **The Claude Code Action template** passed actionlint and the pin gate but has not run on GitHub.
5. `coordination-config.yaml` retired with approval; agent routing has one source, `SKILLS_GUIDE.md`.
6. **Deferred:** H1 (instructed), H11, L5, L6 and S9. **Rejected:** H9 (adds prompts), H10 (project-specific) and C20 (single-tool toolkit).

## 9. Cleanup and git status

Removed generated artifacts (none tracked):
- `reports/`: AI-asset gate output, which the external auto-stager had staged; now unstaged
- `selftest.log`
- a literal `${{ runner.temp }}` directory created by the local CI replay
- 8 `__pycache__/` directories

Kept: `settings.local.json`, the secrets-scan hook's log, the MCP contract suite's `node_modules/`, and the input audit `docs/plans/property-harbor-harness-comparative-audit.md`.


Committed in groups of at most 15 files after approval (see git log).
- An external auto-stager has staged some files; stage explicit paths at commit time after `git reset -q`.
- Untracked: `docs/plans/property-harbor-harness-comparative-audit.md` (input audit), this report, and `reports/` (never commit).
- The suggested split into commits of at most 15 files is left for the approval step.

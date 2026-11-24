# Comparative Audit: Property Harbor harness vs. Claude Code Onboarding

| | |
|---|---|
| **Date** | 2026-11-24 |
| **Type** | Analysis only. Nothing was implemented, and neither repository was modified apart from creating this file. |
| **Source (read-only)** | Property Harbor's `.claude/`, `scripts/`, `.github/`, `CLAUDE.md`, `AGENTS.md`. Referenced here as `PH:<repo-relative path>`. |
| **Target (read-only)** | This repository. Referenced here as `T:<repo-relative path>`. |
| **Excluded** | `.env*`, `settings.local.json`, `*-detected.log`, keys and credentials (never opened); application business logic; customer data; internal issue content. |
| **Method** | Four parallel read-only audits, one per capability group: (1) loops, learning and self-healing; (2) hooks and deterministic enforcement; (3) rules, CLAUDE.md and context; (4) skills, agents, commands, CI and security. Each audit read the actual scripts and wiring, not just names. The main session then re-checked the claims that drive P0 and P1 recommendations (see §9.1). |

**Confidence key** (as defined in `T:.claude/rules/verification-and-reporting.md`):
- **[HIGH]**: re-verified with a tool this session.
- **[MEDIUM]**: read by an auditor, not re-run.
- **[LOW]**: needs checking before anyone acts on it.

---

## 1. Executive summary

The two repositories are mature in different ways.

**Property Harbor (PH) is stronger at enforcement, the learning loop and context economy:**
- **Findings ledger.** A per-branch reviewer-findings ledger is enforced by three hooks: SubagentStop records findings, a bounded Stop gate blocks while any are OPEN, and a PreToolUse(Agent) gate blocks re-reviews. It has processed **930 findings (897 CLOSED, 33 DISMISSED, 0 OPEN)** across 42 branch ledgers [HIGH].
- **Content-fingerprint sentinels.** Evidence counts only while the hash of its inputs is unchanged. These sentinels gate `gh pr create` and `gh pr merge`.
- **Lessons review before merge.** A merge guard requires a lessons-review sentinel that is newer than HEAD. A "no lesson" outcome is allowed.
- **Severity-capped re-review.** From round 3, only CRITICAL and HIGH findings block, and only the owning reviewers are re-dispatched.
- **Hard context budget.** A total ceiling that can only be lowered, plus "canaries" that fail CI if a pinned critical rule is deleted. One prune cut always-loaded context from 140k to 46k bytes.
- **Native `permissions.deny` / `ask` rules** in `settings.json`.

**The target (T) is stronger at authoring quality, version freshness and breadth:**
- **Hook quality.** 33 of 37 T hooks have a `--selftest` and CI discovers them all. PH has 2 of 94 [HIGH]. About 60 PH hooks send advisories to stderr or stdout with exit 0, which the model never sees [MEDIUM]. T's delivery contract prevents this.
- **Command depth.** `/verify` (508 vs 114 lines), `/ship`, `/review-code`, `reality-checker`, `eval-guide`, `flutter-genui`, `browser-testing` and `.mcp.json` pinning are all more rigorous and more current in T. PH still installs `@playwright/mcp@latest` and the discontinued `genui`.
- **Lessons tooling.** T's lessons hooks (`pre-lessons-injector`, `pre-edit-lessons-dedup`, the `systemMessage` stop reminder) and its correction detector are correct where PH's copies are probably inert.
- **Doctrine exists.** T already documents most PH doctrine in prose, for example `T:.claude/skills/verification-before-completion/reference/verification-loop.md` §4 for the ledger and §2–3 for gate caching. What T lacks is the mechanism.

**Headline gaps in the target:**
- No permission deny rules. `T:.claude/settings.json` has only `"defaultMode": "auto"` [HIGH].
- No mechanical gate ties `gh pr create` or `gh pr merge` to fresh verification evidence.
- The findings ledger is documented, but hook enforcement is explicitly "optional" (verification-loop.md §4).
- **93,185 bytes always loaded** (~23k tokens) with no total ceiling, versus PH's 51,383 [HIGH]. `T:.claude/rules/leverage-patterns.md` alone is 26,030 bytes.
- There is no reflection step at the PR boundary. Lessons are captured only from real-time corrections and periodic `/promote-lessons` runs.
- **Defect:** `T:.claude/hooks/pre-lessons-injector.sh:24` uses `sed -n '/^## \[/,$p'`. That first matches the template line `## [YYYY-MM-DD]` inside the code fence at `T:.claude/rules/lessons.md:15`, so subagents get the format boilerplate instead of only the lessons [HIGH].

**Recommendation in one line:** adopt PH's enforcement mechanisms (ledger, fingerprint sentinels, PR and merge gate, deny rules, context ceiling with canaries, PR-boundary lessons review), rebuilt to T's authoring standard. Do not adopt PH's hook implementations, its ~57 separate edit hooks, or its app-specific gates.

---

## 2. Capability-by-capability comparison

| Capability area | Stronger | Evidence summary |
|---|---|---|
| Skills (content) | **T** overall; PH has some specific lessons | T has 162 skills, newer pins and more selftested validators. PH has generic additions worth porting: S1 (ADK `state_delta`), S2 (notification-recipient authz), S3 (Firestore red-team), S4 (Flutter preflights), and the `systematic-debugging` regression-test rule. |
| Specialized agents | **T** | T has 70 agents. PH's only extra, `rag-pipeline-reviewer`, is already merged into `T:rag-implementation-reviewer`. T's `reality-checker` routes per target; PH's is web-only. |
| Slash commands | **T** for gates, **PH** for the loop | T's `/verify`, `/ship` and `/review-code` are stronger. PH has `/lessons-review`, `/post-ship-review`, `/skill-propose` and `/implement-with-notes`, which T lacks (§6). |
| Rules | Mixed | T is better layered and its path-scoped packs are smaller (38.5 KB vs ~283 KB). PH's always-loaded set is smaller (51 KB vs 93 KB) and it has budget canaries and several generic constraints (§3). |
| Hooks: count and coverage | PH has more (94 vs 37) | Most PH-only hooks are app-specific (§7 SKIP list). About 12 are generic and worth generalising. |
| Hooks: authoring quality | **T** | Selftests (33/37 vs 2/94), `additionalContext` delivery, `jq -n --arg`, no auto-fix, bash 3.2 compatibility. PH's `post-edit-format.sh` runs `ruff check --fix`, and 12 PH hooks use `set -e`, one of them with `grep -P` [MEDIUM]. |
| Scripts and validators | **PH** for gate tooling, **T** for toolkit validators | PH has `findings.sh`, `sentinel-freshness.sh`, `gate-cache.sh`, `gates_for_diff.py`, `rereview_needed.py`, `ready-for-review.sh` and a check-script + selftest + CI pattern. T has `lint-testing-tools`, `check-doc-refs`, `check-ai-assets`, `check-context-budget` and its run-CI tooling. |
| CLAUDE.md and settings | **PH** | PH: 6.8 KB CLAUDE.md, 18 deny rules, an `ask` list. T: 17.4 KB CLAUDE.md, no permission rules. |
| Harness and autonomous execution | **PH** | PH has ledger + Stop gate + reviewer-launch gate + PR/merge sentinels. In T, the same doctrine is in prose plus `stop-ralph-loop.sh` (bounded, with a selftest). |
| Orchestration and parallel execution | **T** (docs), **PH** (enforced scopes) | T has `subagent-driven-development`, `parallel-agents` and Agent Teams. PH adds `review-scopes.json` with a re-review firewall and a round cap. |
| Continuous feedback and self-learning | **PH** | Classifier, PR-boundary sentinel, post-ship intake, skill staging (§6). |
| Self-healing and failure recovery | **PH** | An `INVESTIGATION_REQUIRED` escalation after 2 failed closes, scoped re-review, and a pre-review cheap gate. |
| Error prevention and lessons | Mixed | T's lessons hooks are correct and PH's are partly inert. PH turns recurring lessons into blocking hooks (pytest pipe guard on the 3rd recurrence). |
| Context engineering and memory | **PH** for the always-loaded budget, **T** for path-scoped economy | §3, C1–C4, C16–C19. |
| Quality gates and verification | **T** (commands), **PH** (enforcement) | T's `/verify` is the better gate. PH ensures a gate actually ran before a PR. |
| Security and governance | **T** for MCP pinning and guidance, **PH** for permission rules | T: every npx/uvx MCP package pinned, newer `security-patterns.yaml`. PH: `permissions.deny`. PH's `claude-security-guidance.md` is a stale fork of T's. |
| CI/CD integration | **T** hygiene, **PH** volume and patterns | T's 2 workflows: `permissions: contents: read`, concurrency, `persist-credentials: false`. PH's 113 workflows run `--selftest` before every gate. T has no actionlint and no `dependabot.yml` [HIGH]. |
| Developer productivity and tokens | **PH** | Always-loaded ~12.8k vs ~23.3k tokens. Descriptions: PH skills 44.6 KB / agents 31.2 KB, T skills 49.7 KB / agents 47.0 KB [MEDIUM]. |

---

## 3. Missing capabilities

Ordered by priority. Full rows, with source and target references, are in §8.

| ID | Pri | Capability |
|---|---|---|
| H1 | P0 | Native `permissions.deny` / `ask` rules. Stops `.env*`, keys, keystores and cloud credentials from being read into context before the read happens. |
| H2 | P1 | PR-create and merge gate bound to fresh, content-fingerprinted verification evidence. |
| H3 | P1 | Stop-time advisory when UI code changed without executed Playwright (web) or Maestro (Flutter) evidence. |
| C4 | P1 | Context-budget canaries: CI fails if a pinned critical rule is deleted during trimming. |
| L7 | P1 | Lessons review at the PR boundary (enforce that it happened, never that it produced output). |
| L8 | P1 | Learning classifier: prohibition → lesson or rule, procedure → skill, issue decision → notes. Successes are captured too. |
| C11 | P1 | Three scope disciplines: grep to confirm a constraint is real before designing around it; no ticket creation on an agent's suggestion alone; count the population before arguing to reduce scope. |
| H5 | P1 | One detector with three callers: edit hook (advisory), local target and CI (blocking), with `--selftest` first. |
| L5 | P2 | Content-addressed gate cache (reference recipe only). |
| L6 | P2 | Gate set derived from CI path filters. |
| L10 | P2 | Post-ship feedback intake. |
| H6 / S8 | P2 | Gate for deprecations past their removal date. |
| H7 | P2 | l10n catalog parity checked both ways, plus a hardcoded-string advisory. |
| H8 | P2 | Env-key parity across `.env.example`, compose, IaC and the config class (presence only, never values). |
| H9 | P2 | PreToolUse guard for paid or egress APIs, with a session approval env var. |
| S5 | P2 | "Add a tool to an existing MCP server" checklist, keeping the tool a thin adapter. |
| S7 | P2 | Hardened Claude Code GitHub Action template. |
| C14 / C15 | P2 | "Inject the clock" test rule; "move comments and suppression markers with relocated code" rule. |
| C20 | P2 | One source of truth for other AI tools' config (generated, with a `--check` drift mode). Only if T adopts multi-tool support. |
| S19 | P2 | Paired human/agent manual QA protocol (generic phases and a findings template). |

---

## 4. Existing capabilities requiring enhancement

| ID | Pri | Target capability | Enhancement |
|---|---|---|---|
| L1 | P0 | `verification-loop.md` §4 findings ledger (prose, hooks "optional") | Ship an opt-in enforcement kit: ledger script, SubagentStop recorder, bounded Stop gate, reviewer-launch gate, each with a selftest. Build the reviewer set from agent frontmatter. |
| C1 | P0 | `check-context-budget.sh` (per-file 150k cap only) | Add a total GOAL (warns) and CEILING (fails), a committed baseline, and a rule that the ceiling is only lowered. |
| C2 | P0 | `rules/leverage-patterns.md` (26 KB always loaded) | Keep 2–3 KB of mandates; move the procedure into a skill. |
| C16 | P0 (defect) | `hooks/pre-lessons-injector.sh` | Anchor on real entries (`^## \[[0-9]{4}-`), not the template. Limit injection to agents that do not load CLAUDE.md (Explore, Plan). |
| L2 | P1 | Ledger closure | Five evidence classes (CONTROL / MECHANISM / STATIC / NOCONTROL / DISMISSED); `INVESTIGATION_REQUIRED` after 2 failed closes. |
| L3 | P1 | `subagent-driven-development` ("never skip a review loop") | From round 3 only CRITICAL/HIGH block; re-dispatch only the reviewers that own open findings. |
| H4 | P1 | `pre-bash-zsh-split-guard.sh` / pre-bash advisories | Advisory when a test runner is piped into grep/tail/head without `PIPESTATUS` or `pipefail`. |
| C3 | P1 | `CLAUDE.md` (17.4 KB, 8.7 KB conventions table) | Move the table to `SKILLS_GUIDE.md`; keep a pointer and the minimal routing rows. |
| C5 / C6 | P1 / P2 | CLAUDE.md path-scoped rule sentence | Say when packs load (on a file read, not Bash grep) [LOW: verify against current Claude Code docs]. Replace the sentence with a table. |
| C7 | P1 | `rules/skill-triggers.md` MCP table vs `mcp-allowlist.txt` | Make the allowlist the single source; the rule keeps only elevated and archived servers. |
| C10 | P1 | Commit and PR bodies via the shell | Always-loaded 2-line mandate: file content goes through Write/Edit; use `git commit -F` and `gh pr create --body-file`. Backticks in double quotes are executed by the shell. |
| C17 | P1 | Agent and skill descriptions | Cap length (around ≤400 B), move `<example>` blocks into the body, lint in `/audit-skills`. |
| L4 | P2 | Reviewer dispatch | Run `/verify quick` on the diff's stacks before dispatching any reviewer. |
| L11 / S18 | P2 | `plan-mode-review` | Append-only "sub-ADR" implementation notes (check with `git diff --numstat` that it shows `N 0`). |
| L12 | P2 | `rules/hook-and-gate-authoring.md` | Add 4 traps: GNU `stat -f` exits 0, so `stat -f || stat -c` never falls back; SubagentStop can fire twice (dedupe on `agent_id`); payload to a temp file when a heredoc already owns stdin; interpreter-version syntax silently disabling a hook. |
| L16 | P2 | `/review-code` | Key an APPROVE to HEAD, as the security Lock Document already does in `/ship`. |
| C12 | P2 | Layer 1 (`first-principles.md`) | STOP before reverting committed content (`reset --hard`, `checkout HEAD --`, `restore --source`). |
| C18 / C19 | P2 | `lessons.md` cap; agent memory | Enforce the 15-entry cap mechanically; `/promote-lessons` prunes per-issue memory and keeps the index under 200 lines. |
| S1 | P1 | `google-adk` references | State propagation: yield `EventActions(state_delta=…)`; direct `ctx.session.state` writes in a custom agent are lost on re-read. Re-verify on ADK 2.15. |
| S2 | P1 | `security-reviewer` | Treat who receives a notification (push, email, SMS) as an authorization decision. |
| S3 / S4 | P2 | `security-reviewer` / `flutter-mobile` | Firestore rules red-team checklist; Flutter refresh-strategy, media-input and widget-preview preflights, made generic. |
| S6 | P2 | T's own CI | Add actionlint, a `dependabot.yml` for github-actions, and an executable SHA-pin test (T documents all three but does not run them). |
| S9 | P2 | No-stub rule | Optional CI template gate. |
| H10–H13 | P2 | hookify / skill lint / mcp-builder / python advisories | Icon hookify rules; SKILL.md edit → lint reminder; MCP tool ↔ contract-case parity; SQLAlchemy model not registered with Alembic. |
| — | P2 | `systematic-debugging` | The regression test is permanent, named for the bug, asserts the root cause and ships in the same PR. |
| — | P2 | `verification-before-completion` | "Check the business outcome, not API success": persisted state, right tenant, no duplicate, async work at its final status. |
| — | P2 | `/create-pr` body | Add rollback plan, performance impact and "reviewer agents dispatched" sections. Keep T's rule against ticking checkboxes after only reading the diff. |
| C21 | P2 | `rules/leverage-patterns.md` "Browser MCP in the Loop" | Contradicts `testing-tool-selection.md`, which says Playwright CLI for interaction. Reword to point at the canonical rule. |
| — | P2 | CI hook-selftest discovery | Fail CI when a hook lacks `--selftest`. Four T hooks have none: `changelog-version-guard`, `prompt-correction-detector`, `stop-lessons-reminder`, `stopfailure-api-error-notice`. |

---

## 5. Harness, loop engineering and self-healing findings

### 5.1 PH mechanisms (as implemented)

| Mechanism | How it works (PH evidence) | Verdict for T |
|---|---|---|
| **Findings ledger** | `PH:scripts/findings.sh` keeps `PH:.claude/review-state/<branch>/findings.json`, gitignored. Each finding has id, reviewer, severity, state, attempts, scope and resolution. `PH:.claude/hooks/subagent-stop-findings-ledger.sh` records reviewer findings at SubagentStop. `PH:.claude/hooks/stop-open-findings-gate.sh` blocks Stop while any is OPEN, honours `stop_hook_active`, and exempts subagents. `PH:.claude/hooks/pre-agent-review-gate.sh` blocks a reviewer launch whose scope (`PH:.claude/review-scopes.json`) overlaps an open finding. | **Adopt (L1, L2).** The PH header says the prose rule failed three times before these hooks went in [MEDIUM]. Ledger outcome: 930 findings, 0 OPEN [HIGH]. |
| **Escalation after repeated failure** | After 2 failed close attempts a finding becomes `INVESTIGATION_REQUIRED`, which routes to a read-only investigation. | **Adopt (L2).** Pairs with T's 3-attempt hard stop. |
| **Convergence cap** | `PH:scripts/rereview_needed.py`: rounds 1–2 block on any OPEN finding; from round 3 only CRITICAL/HIGH; fails closed; names the owning reviewers. | **Adopt (L3).** Every finding is still fixed; MEDIUM/LOW go into the PR body. |
| **Pre-review cheap gate** | `PH:scripts/ready-for-review.sh` derives the affected packages from the diff and runs fast gates before reviewers are dispatched. | **Adopt as process (L4)** using T's `/verify quick`. |
| **Fingerprint sentinels** | `PH:scripts/sentinel-freshness.sh` reports VALID / CHANGED / EXPIRED / MISSING from a hash of each gate's input scope. Tooling failure degrades to the legacy check and never passes silently. Consumed by `PH:.claude/hooks/pre-pr-docker-health-guard.sh` (blocks `gh pr create` and `gh api …/pulls`). | **Adopt (H2).** `/verify` writes the stamp; a PreToolUse Bash hook checks it. |
| **Merge-time sweep** | `PH:.claude/hooks/pre-merge-ci-parity-guard.sh` runs about 64 gate scripts at `gh pr merge` (~18 s). Overriding it requires a stated reason. | **Optional.** It exists because PH's CI was quota-limited. Generic for teams with path-filtered or limited CI. |
| **Gate cache** | `PH:scripts/gate-cache.sh`: entries keyed by content, a TTL backstop, every failure path means "not cached". | **Reference recipe only (L5).** |
| **CI-derived gate selection** | `PH:scripts/gates_for_diff.py` reads workflow `on.pull_request.paths` and their `make check-*` steps. | **Document the pattern (L6).** |
| **Recurring lesson promoted to a blocker** | `PH:.claude/hooks/pre-bash-pytest-gate-guard.sh` blocks the one shape that has no legitimate use. The other checks stay advisory. Has an escape env var; controls live in a separate script. | **Adopt the policy, not the hook (H4).** |

### 5.2 T equivalents already present (do not duplicate)

- **Ledger doctrine:** `T:.claude/skills/verification-before-completion/reference/verification-loop.md` §4. Gate-cache doctrine is in §2–3, and the phase report line in §5.
- **Bounded loops:** `T:.claude/hooks/stop-ralph-loop.sh` (selftest, transcript completion check) and `/ralph-loop`.
- **Correction capture:** `T:.claude/hooks/prompt-correction-detector.sh` reads `prompt` and emits `hookSpecificOutput`. PH's copy reads `.message`, so it is probably inert [MEDIUM].
- **Lessons hooks:** `pre-lessons-injector.sh` (SubagentStart), `pre-edit-lessons-dedup.sh` (selftest), `stop-lessons-reminder.sh` (`systemMessage`).
- **Destructive-restore guard:** `T:.claude/hooks/pre-bash-destructive-restore-guard.sh`. It is stronger than PH's prose rule for uncommitted work.

### 5.3 Anti-patterns in PH not to copy

1. **Advisories the model never sees:** stderr or stdout on exit 0, or a top-level `additionalContext`. This affects about 60 PH hooks, including scope-monitor, boy-scout, skill-review-reminder, l10n and deprecation.
2. **Hard-coded reviewer lists duplicated in two hooks.** These drift (PH lists `rag-pipeline-reviewer`). Derive the set from agent frontmatter instead.
3. **A PostToolUse hook that polls CI for up to 660 s** (`PH:.claude/hooks/post-pr-ci-gate-check.sh`). Leave CI watching to `/iterate-pr` and `/steward`.
4. **Auto-fix inside an edit hook** (`ruff check --fix` in PH's `post-edit-format.sh`), and **blocking on heuristic lint** per edit (`post-edit-ruff-check` exits 2).
5. **About 57 separate `Write|Edit` PostToolUse entries.** Each spawns a process on every edit (estimated 1–3 s per edit [LOW, not measured]). Above ~15 hooks, use one path-dispatching hook.
6. **State that is never cleaned up:** 198 agent-memory files, 155 review-state directories, 121 cache entries.
7. **Blocking PreToolUse via a top-level `"decision":"block"`.** T uses `permissionDecision` or exit 2. [LOW: confirm the current PreToolUse output schema before relying on either.]
8. **Auto-applying changes to shared skills without human review** (`/skill-propose`). That suits one maintainer, not a team kit.

---

## 6. Continuous learning and feedback mechanisms

### 6.1 PH end-to-end loop
1. **Capture.** Real-time capture by a correction detector (probably inert in PH). The `learning-loop` skill says to capture at discovery, including successes and enforcement gaps. Reviewer findings are captured automatically by the SubagentStop recorder.
2. **Evidence.** Findings close only with an evidence class. A lessons review writes `PH:.claude/lessons-evidence/<branch>.ok` (33 sentinels) [HIGH]. Gate results go to the gate cache.
3. **Classify.** Per `PH:.claude/skills/learning-loop/SKILL.md`:
   - prohibition → `lessons.md` or a rule
   - procedure → `/skill-propose`, staged in `skills-pending/`
   - issue decision → implementation notes
   - root-cause class → mechanical gate, built in the same session
4. **Approve.** skill-reviewer PASS auto-applies. FAIL stays staged and is surfaced again after 7 days.
5. **Promote.** A lesson becomes a rule at `[x3]` or earlier. Steady state is a near-empty `lessons.md`.
6. **Backstops.** `PH:.claude/hooks/pre-merge-lessons-guard.sh` blocks `gh pr merge` unless the sentinel is newer than HEAD. `/end-session` and `/post-ship-review` feed production outcomes back.

### 6.2 Target today
- **Capture:** `prompt-correction-detector.sh` plus the CLAUDE.md Self-Improvement Loop. Only prohibitions are routed, and only to `lessons.md`.
- **Promote:** `/promote-lessons` (periodic): x3 promotion, agent-memory consolidation, pruning.
- **Missing:**
  - A PR-boundary reflection (L7).
  - A route for procedures and successes (L8).
  - A production-outcome intake (L10).
  - A sub-ADR decision log (L11).
  - Mechanical enforcement of the lessons cap (C18).

### 6.3 Recommended target shape (no new skill needed)
- **Fold the classifier** into `/promote-lessons` or `writing-skills` (L8). Use a pairing format: "avoid X, do Y, because Z".
- **Add a lessons-review step to `/ship` or `/create-pr`.** It may record "no lesson". Optionally add a sentinel and a merge guard (L7). Trigger agent-memory consolidation at the same boundary (C19).
- **Merge "propose → skill-reviewer PASS → apply"** into `skill-create`, ending in a reviewed PR rather than an auto-commit (L9).
- **Lessons from PH's own drift:**
  - A budget that is permanently red stops being read: PH is 1,383 bytes over its own ceiling.
  - Its hand-maintained `AGENTS.md` is stale.
  - Its lessons cap is exceeded (16/15).
  - So every limit T adopts needs a CI gate that can actually turn green.

---

## 7. Duplication and consolidation opportunities

### 7.1 Inside the target (found by this comparison)
1. **Session-resume protocol, 3 copies:** CLAUDE.md "Resuming Tasks", `core-behaviors.md` §9, `hooks/session-start.sh`. Keep one.
2. **Self-improvement loop, 3 copies:** CLAUDE.md, the `lessons.md` hygiene section, `first-principles.md` Layer 3. Keep `lessons.md` as the home.
3. **Documentation First:** CLAUDE.md and `code-standards.md`.
4. **Rule precedence** is stated in CLAUDE.md, `first-principles.md` and `skill-triggers.md`. State it once.
5. **MCP trust:** the `skill-triggers.md` table, `mcp-allowlist.txt` and `mcp-config.sha256` (C7).
6. **Skill and agent mapping on 4 surfaces:** CLAUDE.md tables, leverage-patterns "Skill and Agent Selection", descriptions, `SKILLS_GUIDE.md` (C3).
7. **Lessons injection** into subagents that already load rules (C16).
8. **Browser routing:** leverage-patterns vs `testing-tool-selection.md` (C21).
9. **The CLAUDE.md "Pre-Task Checklist"** adds nothing beyond its two pointers.
10. **`T:.claude/agents/coordination-config.yaml`:** no hook, script, skill or command references it, and its header says 68 agents while the folder has 70 [MEDIUM]. Either wire it to a parity check or retire it (needs approval).

### 7.2 PH capabilities with a target equivalent under another name (do not port)

| PH | Target equivalent |
|---|---|
| `ai-golden-evaluation` | `eval-guide`, `llm-evaluation` |
| `genui` | `genui-contract` (suitability reference) |
| `property-harbor-drift-offline`, `/drift-offline-review` | `flutter-mobile/reference/flutter-offline-*` |
| `sync-native-e2e`, `propertyharbor-native-e2e` | `flutter-mobile/reference/flutter-e2e-maestro.md` |
| `seo-audit` | `web-performance-optimization` |
| `rag-pipeline-reviewer` | `rag-implementation-reviewer` |
| `infra-env-ssot`, `/infra-review` | `deployment-ci-cd/reference/env-config-validation.md`, `docker` |
| `cicd` | `deployment-ci-cd`, `gcp-cloud-run`, `terraform-skill` |
| `cloud-sql` | `postgresql`, `gcp-finops` |
| `monorepo-commands` | `flutter-mobile/reference/flutter-build-and-workspace.md` |
| `/verify-before-merge` | `iterate-pr` (local-authoritative mode) |
| `adk-cheatsheet` (ADK 1.x) | `google-adk`, `adk-dev-guide` (2.15) |
| `positive-control-harness` | T version (more general) |
| Same-named hooks: pre-bash guard, secrets, injection, MCP governance, PII logs, quota, timeout, restore | T versions (larger, selftested) |

### 7.3 SKIP (Property Harbor-specific, stale or unsafe)
- **Skills:**
  - `agent-flow-docs`, `dev-workflow`, `email-qa`, `fcm-push`, `sms`
  - `notification-producer-coverage`: its generic core becomes S2
  - `generate-demo-video`, `github-issues`, `ios-push-notification-testing`, `jev-*`
  - `location-maps-address`, `screen-guide`, `wireframe-app-parity`
  - `graphify`: unpinned `--upgrade` install and an over-broad trigger, so it would fail T's P0 skill scan
  - `learning-loop-appendix`: folded into L8
- **Commands:**
  - `aidlc`, `scaffold-github-issues`, `landlord-issue`, `staging-devices`, `run-*-golden-eval`, `run-eval`, `clean-slate-devsetup`, `architecture-html`
  - `skills-diff`, `skills-pending` and `skills-reject` are folded into L9
- **Hooks:**
  - AI-service layout: `adk-callback-wiring`, `agent-init`, `agent-uniformity`, `agent-seed-coverage`, `agent-flow-staleness`, `prometheus-scrape`, `observability`, `ai-shared-usage`, `embedding-purity`, `reranker-env-split`
  - Stripe and MCP server paths: `stripe-*`, `mcp-concurrent-gate`, `mcp-log-pii` (T's TS PII hook covers the generic part)
  - App constitution: `auth-boot-gate`, `offline-arch`, `font-package-scope`, `apps-design-compliance`, `flutter-app-consistency`, `flutter-api-contract`, `flutter-test-parity`, `shared-test-types`, `flutter-structure`, `flutter-e2e-reminder`, `flutter-e2e-offline`
  - PH documents: `design-md-sync`, `wireframe-*`, `brain-rules-stale`, `genui-sdk`
  - PH Makefile targets: `backend-smoke-reminder`, `docker-context-skill`, `pre-edit-infra-parity`, `flutter-gate-freeze`, `flutter-baseline-guard`, `pre-pr-checklist-guard`
  - `post-gh-board-sync`: hard-coded project IDs
  - `smart-suggest`: already retired in T
  - `post-pr-ci-gate-check`: blocking poll
- **Other:**
  - PH's `.agents`, `.qoder` and `.hermes` folders (leftovers)
  - PH's §-numbering citation checker (T's `check-doc-refs.sh` covers reference resolution)
  - PH's 15 auto-ticked PR checkboxes (checkbox theatre; T forbids ticking boxes from reading the diff)

---

## 8. Prioritized recommendations

Each row combines findings from §3–§7. "Source evidence" uses PH paths; "Existing target coverage" uses T paths.

### P0

| Priority | Capability | Source evidence | Existing target coverage | Gap | Recommended action | Expected benefit |
|---|---|---|---|---|---|---|
| P0 | Permission deny/ask rules (H1) | `PH:.claude/settings.json` `permissions.deny`: 18 rules (Read of `.env.local`, keys/keystores, secrets dirs; force-push, sudo, ssh, eval, chmod 777). `ask`: `git reset/clean/restore`, `rm` [HIGH] | `T:.claude/settings.json` `permissions` = `{"defaultMode":"auto"}` only [HIGH]. `T:.claude/hooks/output-secrets-scanner.sh` runs after the read. `T:.claude/hooks/pre-bash-guard.py` covers Bash only. | The Read tool can pull `.env*`, keys or keystores into context with nothing stopping it first. | Add a stack-neutral deny list: Read of `.env*` (except `*.example`), `*.pem/*.key/*.p12/*.jks/*.keystore`, cloud credential files, `*.tfstate`/`*.tfvars`; Bash force-push. `ask` for `rm`, `git clean`, `git reset`. Keep the existing hooks. | Secrets are never read in the first place, instead of being detected afterwards; a defence-in-depth layer native to Claude Code. |
| P0 | Enforced findings ledger, opt-in kit (L1, L2) | `PH:scripts/findings.sh`; `PH:.claude/hooks/subagent-stop-findings-ledger.sh`, `stop-open-findings-gate.sh`, `pre-agent-review-gate.sh`; `PH:.claude/review-scopes.json`. 930 findings, 0 OPEN [HIGH] | `T:.claude/skills/verification-before-completion/reference/verification-loop.md` §4. Hook enforcement "optional" (line ~49) [HIGH] | Doctrine with no mechanism; no closure evidence classes; no escalation. | Add the kit as opt-in hooks to T's standard: a selftest each, `additionalContext`/exit-2 delivery, `stop_hook_active` bound, reviewer set from agent frontmatter, default scope `*`. Add the 5 evidence classes and the 2-attempt escalation to §4. | Review rounds become bounded transactions; findings can't be abandoned or closed without evidence. |
| P0 | Total context ceiling with canaries (C1, C4) | `PH:scripts/check-context-budget.sh`: GOAL 48,000 / CEILING 50,000, only ever lowered; canaries proven both ways (delete the pin → red, delete a neighbour → green) | `T:.claude/scripts/check-context-budget.sh` and `T:.github/workflows/context-budget-gate.yml`: per-file 150k cap only, no total, no baseline [HIGH] | 93,185 B always loaded with no ceiling [HIGH]. Trimming could delete Layer-1 STOP rules unnoticed. | Add a total GOAL and CEILING set just above the post-trim size, a committed baseline, and canaries for the Layer-1 rules and the SKILL-INJECT scan. | Stops silent growth of a cost every session and subagent pays; makes trimming safe. |
| P0 | Always-loaded diet (C2, C3, §7.1) | PH commit "67fdc16" moved leverage-patterns into a skill and pruned CLAUDE.md: 140k → 46k B [MEDIUM] | `T:.claude/rules/leverage-patterns.md` 26,030 B; `T:CLAUDE.md` 17,439 B [HIGH] | ~28% of T's always-loaded bytes are procedure, plus 9 duplicated topics. | Move leverage-patterns procedure into a skill (keep 2–3 KB of mandates); move the conventions table to SKILLS_GUIDE; remove the §7.1 duplicates. Do this after the canaries exist. | ~25–35 KB (~6–9k tokens) less per session and per subagent. |
| P0 | Lessons-injector defect (C16) | PH removed its copy because of the duplication. | `T:.claude/hooks/pre-lessons-injector.sh:24` `sed -n '/^## \[/,$p'` matches the template `## [YYYY-MM-DD]` at `T:.claude/rules/lessons.md:15` [HIGH] | Subagents receive format boilerplate, and the 60-line limit truncates the real lessons. | Anchor on `^## \[[0-9]{4}-`; inject only into agents that skip CLAUDE.md; add a selftest with the template as a negative control. | Correct and smaller subagent context. |

### P1

| Priority | Capability | Source evidence | Existing target coverage | Gap | Recommended action | Expected benefit |
|---|---|---|---|---|---|---|
| P1 | PR/merge gate on fresh verification (H2, L16) | `PH:scripts/sentinel-freshness.sh` (selftest; VALID/CHANGED/EXPIRED/MISSING); `PH:.claude/hooks/pre-pr-docker-health-guard.sh`; `PH:scripts/record-reasoning-review.sh` | `T:.claude/commands/verify.md`, `ship.md`, `create-pr.md`: prose; `/ship` security Lock Document keyed to the commit | Nothing stops `gh pr create`/`merge` on an unverified or changed tree. | `/verify` writes a stamp with the tracked-tree hash. A PreToolUse Bash hook, anchored at command position, blocks on CHANGED or MISSING and fails open on missing tooling. Optionally key a `/review-code` APPROVE to HEAD. | "Verify before PR" becomes a gate; evidence goes stale when the content changes, not on a timer. |
| P1 | "UI changed, no executed test evidence" Stop advisory (H3) | `PH:.claude/hooks/stop-flutter-e2e-guard.sh` (branch + staged + unstaged; flags checks that pass only because nothing is committed yet) | `T:.claude/rules/testing-tool-selection.md` (prose); T Stop hooks cover secrets, lessons, ralph, notify | Sessions can report done without Playwright or Maestro evidence. | `systemMessage` advisory per target, using the same checker as the PR gate; bounded by `stop_hook_active`. | Enforces the BLOCKED/NOT RUN honesty rule mechanically. |
| P1 | Severity-capped, scoped re-review and pre-review gate (L3, L4) | `PH:scripts/rereview_needed.py`, `PH:scripts/ready-for-review.sh` | `T:.claude/skills/subagent-driven-development/SKILL.md` (~line 309, "never skip"); verification-loop.md (scoped re-review in prose) | Review rounds can repeat without limit; reviewers may see trees that already fail. | Add the round-3 cap and owner-scoped re-dispatch to SDD and verification-loop; require `/verify quick` before reviewer dispatch. | Much less reviewer wall-clock time with the same rigor. |
| P1 | Lessons review at the PR boundary and learning classifier (L7, L8, C19) | `/lessons-review`; `PH:.claude/hooks/pre-merge-lessons-guard.sh`; `PH:scripts/check-lessons-sentinel.sh`; `PH:.claude/skills/learning-loop/SKILL.md` | `T:.claude/commands/promote-lessons.md` (periodic); CLAUDE.md loop (corrections only); grep of `ship.md`/`create-pr.md` for "lesson": none | No reflection at merge; procedures and successes have nowhere to go. | Lessons-review step in `/ship` or `/create-pr` ("no lesson" allowed); classifier table and pairing format in `/promote-lessons`; memory consolidation at the same boundary. Sentinel and merge guard optional. | Durable learning, including procedures, without padding `lessons.md`. |
| P1 | Test-output pipe advisory (H4) | `PH:.claude/hooks/pre-bash-pytest-gate-guard.sh` (3 recurrences of ~40 min hangs; promoted to blocking on the 3rd); `PH:scripts/test-pytest-gate-guard.sh` | `T:.claude/hooks/pre-bash-zsh-split-guard.sh` (other shapes); `hook-and-gate-authoring.md` (CI `run:` steps only) | The agent's own `<test runner> \| tail/grep` calls lose the exit code without any warning. | Add an advisory arm for pytest, flutter test, vitest, jest, `mvn test`, `ng test` and `playwright test` piped without `PIPESTATUS`/`pipefail`. | Applies the "tool's own exit code" rule at the moment the command runs. |
| P1 | Shared-detector pattern (H5) | 22 PH hooks call `scripts/check-*.sh`; 56 of 120 checkers have selftests; 42 workflows run `--selftest` first | `T:.claude/hooks/post-edit-python-log-pii-advisory.sh` keeps a second copy "in sync" | Edit-time and CI detectors drift. | Add the pattern to `hook-and-gate-authoring.md` and the scaffold commands: one checker, three callers, selftest first. | No drift between the editor warning and the CI block. |
| P1 | Always-loaded behaviour additions (C10, C11, C5) | `PH:.claude/rules/core-behaviors.md` §4/§5/§6.5; PH CLAUDE.md note on when path-scoped packs load | `T:.claude/skills/verification-before-completion/reference/verification-loop.md` (lazy-loaded); `T:CLAUDE.md:51` | Shell-quoting corruption of commit and PR bodies; phantom constraints; unapproved tickets; packs not loaded when working via Bash. | ~6 short lines in core-behaviors and CLAUDE.md. C5 needs checking against Claude Code docs first [LOW]. | Fewer silent corruptions and scope errors. |
| P1 | Description length cap (C17) | PH shortened 10 skill descriptions from ~870 B to ~270 B | T skills 49.7 KB / agents 47.0 KB, with `<example>` blocks in agent descriptions [MEDIUM] | Tool and skill listings are large. | Cap around ≤400 B, move examples to the body, lint it in `/audit-skills` and `lint-skills.sh`. | ~20 KB+ smaller listings. |
| P1 | MCP trust single source (C7) | `PH:.claude/rules/skill-triggers.md` points at `mcp-allowlist.txt` | `T:.claude/rules/skill-triggers.md` P0 table (~3.5 KB) plus `T:.claude/mcp-allowlist.txt` and `session-mcp-governance.sh` | Two sources that can drift. | Allowlist + hook are the source; the rule keeps only elevated and archived servers. | ~3 KB less, one source of truth. |
| P1 | Security and ADK review content (S1, S2) | `PH:.claude/skills/google-adk/reference/adk-state-propagation.md`; `PH:.claude/skills/security-reviewer/SKILL.md` (recipient authz) | `T:.claude/skills/google-adk/reference/*` (no `state_delta`); `T:.claude/agents/security-reviewer.md:66` (side effects only) | Silent state-loss bug; wrong-recipient notifications. | Add both in generic form; re-verify ADK guidance on 2.15 via MCP or Context7 first. | Catches two classes of P0 production defects. |

### P2

| Priority | Capability | Source evidence | Existing target coverage | Gap | Recommended action | Expected benefit |
|---|---|---|---|---|---|---|
| P2 | Gate cache and CI-derived gate set (L5, L6) | `PH:scripts/gate-cache.sh`, `PH:scripts/gates_for_diff.py` | verification-loop.md §2–3 (doctrine only) | No mechanism. | Reference recipe plus the "CI path filters decide which gates apply" pattern in deployment-ci-cd. | Expensive gates stop re-running; new gates enrol themselves. |
| P2 | Skill-improvement path (L9) | `/skill-propose` with `PH:.claude/skills-pending/` | `T:.claude/commands/skill-create.md`, `skill-reviewer` | No staged proposal step. | Fold propose → review → apply into `skill-create`, ending in a reviewed PR. | Self-improvement without four extra commands. |
| P2 | Post-ship intake (L10) | `/post-ship-review` | `ai-incident-response` (AI only) | Production outcomes don't feed back into rules. | Short generic section that routes through the classifier. | Closes the loop after merge. |
| P2 | Sub-ADR implementation notes (L11, S18) | `/implement-with-notes` | `architecture-decision-records`, `plan-mode-review` | No home for decisions too small for an ADR. | Paragraph plus append-only check in `plan-mode-review`. | Reviewers can see why choices were made. |
| P2 | Hook-authoring traps (L12) | `PH:.claude/rules/gate-script-authoring.md` | `T:.claude/rules/hook-and-gate-authoring.md` (~80% covered) | 4 traps missing. | Add 4 bullets. | Prevents hooks that look installed but do nothing. |
| P2 | Deprecation, l10n and env-key parity checkers (H6, H7, H8, S8) | `PH:scripts/check-expired-deprecations.sh`; `post-edit-l10n-*`; `PH:scripts/check-env-sync.sh` | Prose only (`flutter-localization.md`, `env-config-validation.md`) | Defect classes no compiler catches. | Stack-neutral checkers, each checked both ways, with selftests; advisory hook plus CI. | Mechanical enforcement of the zero-deprecated rule and config parity. |
| P2 | Paid/egress API guard (H9) | `PH:.claude/hooks/jev_guard.py` with `PH:scripts/test-jev-guard.sh` | `T:.claude/hooks/output-llm-quota-guard.sh` (after the call) | No pre-call approval. | Configurable host/SDK deny list with a session approval env var; never echo keys. | Prevents surprise spend and key leaks. |
| P2 | Edit-time design and toolkit reminders (H10, H11, H12, H13) | `post-edit-shared-ui-reuse`, icon hookify rules, `post-edit-skill-review-reminder`, `post-mcp-tool-scenario-check`, `post-edit-shared-model` | 7 T hookify rules; `lint-skills.sh` in CI; mcp-builder contract scripts; `alembic-migration-safety.md` | Feedback arrives late. | Icon hookify templates; SKILL.md → lint advisory; MCP tool ↔ contract-case parity; model-registration check in the Python advisory. Keep under the ~15-hook dispatch threshold. | Shorter feedback loops. |
| P2 | T's own CI dogfooding (S6, CI selftest enforcement) | `PH:tests/arch/test_supply_chain_pins.py`, `PH:.github/workflows/supply-chain-pins-gate.yml`, `PH:.github/dependabot.yml` | `T:.github/workflows/` has `context-budget-gate.yml` and `toolkit-lint.yml` only; no actionlint, no `dependabot.yml` [HIGH] | T documents these gates but does not run them on itself. | Add actionlint, a SHA-pin check, Dependabot for actions; fail CI when a hook lacks `--selftest`. | Proves the guidance with gates that actually run. |
| P2 | Claude Code Action template (S7) | `PH:.github/workflows/claude-review.yml`, `claude.yml` (do not copy as-is: no `author_association` check while holding write and id-token permissions) | `claude-actions-auditor` skill (no template) | No secure starting point. | Template with author-association gating, least privilege, no `pull_request_target`, SHA pin. | A secure default. |
| P2 | Content ports (S3, S4, S5, S19, C14, C15, C12, debugging, business-outcome, create-pr sections) | §4 rows | §4 rows | Missing in generic form. | Port into existing skills and rules; no new skills. | Fewer repeated mistakes. |
| P2 | Multi-tool single source (C20) | `PH:scripts/sync-cursor-from-claude.py` (generated); `PH:AGENTS.md` (hand-written, stale) | none | Only matters if T supports other tools. | If adopted: generate every per-tool file and add a CI `--check` drift mode. | Avoids PH's drift. |

---

## 9. Evidence references

### 9.1 Re-checked this session [HIGH]

| Claim | Command or evidence |
|---|---|
| T has no permission rules | `jq '.permissions' T:.claude/settings.json` → `{"defaultMode":"auto"}` |
| PH has 18 deny rules and 4 ask rules | `jq` on `PH:.claude/settings.json` |
| T always-loaded = 93,185 B | Byte sum of CLAUDE.md plus rules without `paths:`: leverage-patterns 26,030; CLAUDE.md 17,439; core-behaviors 10,258; verification-and-reporting 9,873; code-standards 8,389; skill-triggers 7,580; first-principles 6,972; testing-tool-selection 4,276; lessons 2,368 |
| T budget script has only the 150k cap | `T:.claude/scripts/check-context-budget.sh:14,53-58` |
| Injector defect | `T:.claude/hooks/pre-lessons-injector.sh:24`; `T:.claude/rules/lessons.md:15` is the template inside the fence, real entries start at line 44 |
| Ledger hooks wired in PH | `PH:.claude/settings.json` references `subagent-stop-findings-ledger.sh`, `stop-open-findings-gate.sh`, `pre-agent-review-gate.sh`, `pre-merge-lessons-guard.sh`, `pre-pr-docker-health-guard.sh` |
| Ledger outcome | Across every `findings.json` under `PH:.claude/review-state/`: 897 CLOSED, 33 DISMISSED, 0 OPEN |
| PH gate scripts exist | `PH:scripts/{findings.sh, sentinel-freshness.sh, gate-cache.sh, gates_for_diff.py, rereview_needed.py, ready-for-review.sh, check-lessons-sentinel.sh, write-lessons-sentinel.sh}` |
| 33 lessons sentinels | `ls PH:.claude/lessons-evidence` |
| Hook selftests | PH 2 of 94 `.sh` hooks contain `--selftest`; T 33 of 37 |
| T CI | `T:.github/workflows/{context-budget-gate.yml, toolkit-lint.yml}`; no `dependabot.yml`; no actionlint |
| T ledger enforcement optional | `T:.claude/skills/verification-before-completion/reference/verification-loop.md` §4 closing paragraph |

### 9.2 From the auditors, not re-run [MEDIUM]
- About 60 PH hooks deliver advisories that the model never sees; 14 build JSON by hand; 12 use `set -e`.
- PH correction and end-session detectors read `.message` and are probably inert.
- PH description totals; T description totals.
- The `coordination-config.yaml` header count and the fact that nothing references it.
- PH `.mcp.json` uses `@latest` for several servers; T pins all of them.
- The PH prune commit reduced always-loaded from 140k to 46k.

### 9.3 Must be checked before implementation [LOW]
- **C5:** do path-scoped rules load on a Read but not on a Bash grep? Check against current Claude Code memory/rules docs.
- **PreToolUse output shape:** is top-level `decision: block` legacy, or still valid next to `permissionDecision`? Check against current hooks docs.
- **SubagentStop payload:** do `agent_id` presence and absence reliably tell a subagent from the main agent? A Stop-gate exemption depends on it; re-probe.
- **S1:** check the ADK `state_delta` behaviour on google-adk 2.15 (PH wrote it for 1.29).
- **H9 / C14 / C15 / constraints marked LOW by the rules auditor:** "MCP thin adapter" and "local compose equivalent for every cloud dependency" may already exist in `mcp-builder` / `docker`. Grep again before porting.
- **Per-edit hook overhead** of 1–3 s is an estimate; measure before choosing a dispatch design.

Context7 was not used for this audit; it was BLOCKED (monthly quota) earlier in this session. Every technology-specific item above is marked as needing verification against official docs before implementation.

---

## 10. Proposed future implementation phases

Each phase is a separate branch and PR, with at most 15 files per commit, the toolkit's own run-CI tooling green, and positive and negative controls for every new gate. Nothing below is approved; this list is for review.

| Phase | Scope | Items | Exit criteria |
|---|---|---|---|
| **A: Safety and defects** (small) | Permission rules, injector fix, rule wording | H1, C16, C21, C10, C11, L12, C12 | Deny rules proven (a Read of a planted `.env.test-fixture` is denied, a `.env.example` read is allowed); injector selftest with the template as a negative control; lint and doc-refs green. |
| **B: Context diet** | Budget ceiling and canaries first, then trimming | C1, C4 → C2, C3, C6, C7, C17, §7.1 items 1–9 | Ceiling committed just above the new size; every canary proven both ways; always-loaded target ≤ 60 KB (from 93 KB); no Layer-1 rule lost (canaries). |
| **C: Enforcement kit** | Verification stamp, PR/merge gate, Stop advisory, pipe advisory, ledger hooks | H2, H3, H4, L1, L2, L16, H5 | Every hook has a selftest with a mutation check; a bounded Stop gate is proven not to loop; the reviewer set derives from frontmatter; documentation updated in verification-loop §4 ("optional" becomes opt-in, with a how-to). |
| **D: Loop convergence and learning** | Re-review cap, pre-review gate, PR-boundary lessons, classifier, memory hygiene, post-ship intake, skill-propose path | L3, L4, L7, L8, L9, L10, L11, C18, C19 | `/ship` or `/create-pr` include the lessons step; `/promote-lessons` holds the classifier; the lessons cap is enforced by a hook with a selftest. |
| **E: Stack gates and content ports** | Optional checkers and skill content | H6–H13, S1–S9, S19, C14, C15, C20, debugging and verification additions | Each checker is checked both ways with a selftest and CI wiring; content verified against official docs or MCP; the testing-tool and doc-ref lints are green. |
| **F: T CI dogfooding** | actionlint, pin test, Dependabot, hook-selftest enforcement, Claude Action template | S6, S7, CI selftest rule, `coordination-config.yaml` decision | Workflows pass actionlint; the pin test fails on a planted `@v4`; a hook without `--selftest` fails CI. |

**Suggested order:** A → B → C → D, then E and F as capacity allows. B goes before C so the context added by new enforcement stays inside a ceiling that is already enforced.

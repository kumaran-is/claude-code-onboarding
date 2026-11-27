# Toolkit vs AWS AI-DLC ownership

The two systems are **independent**. `/setup-aidlc` configures upstream AI-DLC
for Claude Code; it does not replace `/next`.

| Surface | This toolkit | AWS AI-DLC | Rule |
|---|---|---|---|
| Story pick / implement / verify / ship | `/next`, `/verify`, `/ship`, `/review-code` | — | Do not start `/aidlc` from `/next` |
| Lifecycle phases, POD workflow | — | `/aidlc` | Do not start `/next` from `/aidlc` |
| Ralph inner retry, `/next --auto` | toolkit Stop hooks | — | Leave registered; official config must **merge** hooks, not replace the block |
| SDD execution ledger | `subagent-driven-development` | — | Not AI-DLC state |
| Stack skills / agents / standards | `.claude/skills/*`, `.claude/agents/*`, `.claude/rules/*` | AI-DLC agents under its runtime | Do not copy upstream into the toolkit |
| `model` | toolkit `sonnet` unless the team changed it | may suggest overrides in `settings.local.json` | Changing committed `model` is BLOCKED without a listed approval |
| `permissions.defaultMode` | `auto` in this kit | must not flip to skip-permissions | BLOCKED if dry-run changes it |
| `permissions.allow` | kit uses `defaultMode` only | official config **merges** shipped allow entries | WARN + human review; never `--force` |
| Stop / PreToolUse hooks | ralph, next-auto, enforcement, secret scan, … | AI-DLC engine hooks merged by event | BLOCKED if plan `hooks_mode=replace` |
| Commands `next.md` `verify.md` `ship.md` `ralph-loop.md` | toolkit | must not overwrite | BLOCKED |
| Command `/aidlc` | — | upstream after `aidlc config` | OK; not a toolkit command |
| `.mcp.json` | existing servers stay | `--mcp none` by default | `--mcp defaults` needs extra approval |
| `aidlc/` workspace, `.aidlc-version` | — | upstream | Do not reimplement |
| Stitch → DESIGN.md → prototype | `/startup-design` (`startup-design-to-code`, `--mode aidlc --bind-aidlc`) | Ideation / Inception / Construction | Consume approved Ideation/Inception; do not start `/aidlc`; do not write `aidlc/`; Construction stays `/aidlc` |

## Stop and offer alternatives

`--compat` exits 1 (`BLOCKED`) when the plan would:

- Pipe a remote installer into a shell
- Pass `aidlc config --force`
- Overwrite toolkit commands or skills
- Change `model` or `permissions.defaultMode`
- Replace the entire `hooks` object
- Rewrite an unreadable `settings.json`
- Run config while `aidlc` is missing

Safe alternatives:

1. Run `aidlc config --harness claude --dry-run` and paste the JSON/plan for review.
2. Keep toolkit files; let official merge add AI-DLC hook groups beside existing ones.
3. Put personal model/statusline overrides in `.claude/settings.local.json` (gitignored), not in committed `settings.json`.
4. If the official CLI is missing, install it first (download → inspect → attest → run).
5. If coexistence is unwanted, do not run `/setup-aidlc`; use `/next` only.

## After a successful setup

Both must still work independently:

- `/next` — unchanged human-in-the-loop (or `/next --auto` if that flag is used)
- `/aidlc` — official AWS workflow

Doctor and `/next` selftest are separate. A failure in one is not a failure of the other.

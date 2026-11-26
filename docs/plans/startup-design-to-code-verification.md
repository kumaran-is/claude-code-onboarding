# Startup design-to-code — verification (2026-11-26)

Orchestration skill for G0–G10. Does not commit. Property Harbor untouched. Always-loaded budget unchanged (60,342 / 62,000).

## 1. Workflow → skill / command

| Gate | Capability | Home |
|---|---|---|
| Invoke | `/startup-design`; NL “design my startup app” | `.claude/commands/startup-design.md`, skill description CSO |
| G0 brief | templates + manifest | `startup-design-to-code` |
| G1 Stitch | live MCP discovery; BLOCKED if missing | `reference/stitch-preflight.md` |
| G2 briefs | formula in SKILL.md | this skill |
| G3 screens | discovered tools only | this skill |
| G4 DESIGN.md | Google Labs 10 sections + toolkit addenda | `design-md-governance.md`; CLI `npx @google/design.md` |
| G5 prototype | HTML/Stitch preview contract | `reference/prototype.md` |
| G6 architecture | platform choice, no scaffold | `architecture-design`; Angular UI mode |
| G7–G10 production | after `production_approved` | `/scaffold-flutter-app`, `/scaffold-angular-app`, `/scaffold-react-app`; `/lint-design-system`; Playwright / Maestro |

## 2. Reused vs new

**New:** skill, `/startup-design`, `.startup-design/manifest.json` schema, `check-startup-design.py`.

**Reused:** design-system gate, Atomic/smart-dumb, three Angular modes, React+shadcn, Flutter scaffold, screenshot-to-*, reviewers listed in SKILLS_GUIDE. Official Stitch skills are optional and not vendored. No new agents, hooks, always-loaded rules, or `.mcp.json` / `.claude/settings.json` edits.

## 3. Example terminal

```bash
/startup-design LeafLog reminds apartment dwellers to water plants
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py --root . --status
/startup-design resume
# after G5 PROCEED and the human says approve production:
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py --root . --approve-production --approved-by "$USER"
```

## 4. Artifacts generated this session

- Skill tree under `.claude/skills/startup-design-to-code/`
- Command `.claude/commands/startup-design.md`
- LeafLog product in a temp dir (not in git): G0 brief, DESIGN.md skeleton, G1 BLOCKED manifest
- Official CLI lint of the skeleton: 0 errors (infos for declared omissions)

## 5. Tests

| Check | Result |
|---|---|
| `check-startup-design.py --selftest` | exit 0 |
| Mutation: `secret_findings` returns [] | selftest exit 2 |
| LeafLog G0 PASS, G1 BLOCKED, resume keeps brief | PASS |
| `--require-production` before approval | exit 1 |
| `--approve-production` before G5 | exit 1 |
| G3 PASS with `mcp_evidence: none` | exit 1 |
| `--check-prototype` with no HTML | exit 1 |
| `npx @google/design.md lint` on skeleton | exit 0, 0 errors |
| `check-design-system.py --selftest` | exit 0 |
| hookify `test_rules.py` | exit 0 |
| `lint-skills.sh` | 168 passed |
| `check-doc-refs.sh` | 0 violations |
| `check-context-budget.sh --strict` | 60342 ≤ 62000 |
| `skill-reviewer` | PASS 16/16 |
| Real Stitch MCP generate/edit | **NOT RUN** (server not in `.mcp.json`) |
| Interactive prototype in a browser | **NOT RUN** (G3 blocked; no fake screens) |
| Flutter/Angular/React production scaffold | **NOT RUN** (approval gate) |

Mocked MCP evidence is rejected unless `--allow-mock` (selftest only).

## 6. Missing / blocked

- Stitch MCP is **not** registered in this toolkit. G1 is BLOCKED until the human connects it from the live official setup page. This skill does not write endpoints or keys.
- Official `stitch.google.com/docs/mcp/setup/` fetch in this session returned empty body; preflight therefore requires a re-fetch at run time and forbids guessed URLs.
- No official Flutter/Angular Stitch translation skill is assumed.

## 7. Context budget

Always-loaded 60,342 / 62,000. No CLAUDE.md or `skill-triggers.md` growth.

## 8. Git

HEAD `feat/flutter-mobile-engineering-best-practices`. New skill/command untracked. Auto-stager staged prior P2 design-system files (index not empty). No commit/push.

## 9. Verdict

- **Toolkit orchestration:** READY for G0, G1-blocked recovery, resume, DESIGN.md skeleton, production refusal, and routing into existing scaffolds after approval.
- **Merge of a product that used Stitch:** BLOCKED until a live Stitch MCP session is discovered. Do not treat mocked selftest screens as MCP evidence.

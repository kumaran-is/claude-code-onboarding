---
name: startup-design-to-code
description: "Use when turning a startup idea into a product brief, Google Stitch screens, DESIGN.md, a clickable prototype, then Flutter, Angular or React production UI. Triggers: design my startup app, help me design my startup, startup idea, idea to production, Stitch MCP, Google Stitch, /startup-design, DESIGN.md from Stitch, interactive prototype, product brief then screens. Not for linting an existing app (design-system), not for screenshot translation of one screen (screenshot-to-flutter / screenshot-to-angular), not for lo-fi wireframes (/sketch-wireframe)."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch, Agent
metadata:
  triggers: design my startup app, startup idea, idea to production, Google Stitch, Stitch MCP, DESIGN.md, interactive prototype, /startup-design, product brief
  related-skills: design-system, flutter-mobile, angular-spa, react-spa, screenshot-to-flutter, screenshot-to-angular, accessibility-audit, architecture-design, feature-forge, mobile-design, frontend-design
  domain: frontend
  role: specialist
  scope: design
  output-format: document
last-reviewed: "2026-11-26"
---

## Iron Law

**NO PRODUCTION APP AND NO FAKE STITCH SCREENS.** Progress G0→G10 through the manifest. If Stitch MCP is missing, G1 is BLOCKED and artifacts stay. Production translation starts only after G5 `PROCEED` and an explicit human "approve production" in this session.

# Startup design to code

One orchestration skill. Command: `/startup-design`. Existing scaffolds, design-system gate, reviewers and Stitch skills stay where they are.

## When to use

| Say this | This skill | Not this |
|---|---|---|
| "Help me design my startup app" | Start G0 | `/new-project` (skips validation) |
| Stitch → DESIGN.md → prototype | G1–G5 | `/wireframe` (different fidelity) |
| "Build the Flutter/Angular/React app" after a prototype | G6–G7 after approval | scaffolding with no DESIGN.md |
| Lint tokens on an existing app | — | `/lint-design-system` |
| One screenshot → one screen | — | `screenshot-to-*` |

## Reuse vs new

**New here:** manifest, G0–G10 stage machine, Stitch preflight that discovers tools at runtime, prototype contract, production approval gate.

**Already in the toolkit — call, do not copy:** `design-system` (DESIGN.md, tokens, atomic, smart/dumb, async/refresh), `/scaffold-flutter-app`, `/scaffold-angular-app`, `/scaffold-react-app`, `screenshot-to-flutter` / `screenshot-to-angular`, `ui-standards-expert`, `design-system-reviewer`, `accessibility-auditor`, `architect`, `code-reviewer`, `security-reviewer`, Playwright vs Maestro per `testing-tool-selection.md`. Official Stitch skills (`stitch::generate-design`, `stitch::design-md`, …) if the human already installed them.

## Process

1. Load [reference/manifest.md](reference/manifest.md). `--init` if `.startup-design/manifest.json` is missing; otherwise `--status` and resume `current_stage`.
2. Run one gate from [reference/stages.md](reference/stages.md). Idempotent: a `PASS` gate is not regenerated unless the human asks.
3. Stitch: [reference/stitch-preflight.md](reference/stitch-preflight.md). Discover tools and schemas this session. No hardcoded MCP names or URLs.
4. DESIGN.md: Google Labs ten sections + toolkit addenda (`design-md-governance.md` §5). Tokens from approved screens. `npx @google/design.md lint DESIGN.md` when that CLI exists; otherwise G4 CLI evidence is `NOT RUN`.
5. Prototype: [reference/prototype.md](reference/prototype.md). Simulated banner required.
6. Enterprise bar: [reference/enterprise-mapping.md](reference/enterprise-mapping.md) (routes to files; does not vendor the 30-section standard).
7. Production: [reference/production-handoff.md](reference/production-handoff.md) only after approval.

### Screen brief formula (G2)

> Create a [device] screen for [user] to [single task]. Show [essential content] in [priority order]. Primary action is [action]. Secondary action is [action]. Use [tone] and [existing DESIGN.md tokens]. Include [states and a11y]. Do not add unrelated dashboards.

### Resume output

```
## Startup design
Stage: G<n> <status>
Next: <action>
Blocked: <reason or none>
Artifacts: <paths>
MCP: discovered <n tools> | none | mocked (tests only)
Production approved: yes|no
```

## Anti-patterns

- Scaffolding Flutter/Angular/React in G0–G5.
- Writing Stitch screen IDs that were not returned by a discovered tool.
- Marking `mcp_evidence: discovered` after a mock.
- Copying generated HTML into production widgets.
- Inventing a second palette beside DESIGN.md.
- Putting API keys in the manifest or `.mcp.json` from this skill.
- Adding always-loaded rules or a second design gate.

## Error handling

| Failure | Action |
|---|---|
| No Stitch server | G1 BLOCKED; keep G0/G2; tell the human to connect via the live official setup page |
| Tool call fails mid-batch | Keep inventory rows already saved; do not mark later screens approved |
| DESIGN.md CLI missing | Record NOT RUN; still require the ten sections and no `omitted` token families for G4 PASS |
| G5 ITERATE | Return to G2/G3; do not touch production |
| G5 STOP | Leave the manifest; stop |
| User asks for production too early | Refuse; show which gate is missing |

## Verify

```bash
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py --selftest
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py --root <product>
```

Exit 0 = manifest legal and secret-free. Exit 1 = workflow/secret/prototype failure. Exit 2 = usage or broken detector. `--selftest` must run first (exit 2 = the gate itself is broken).

## References

- [reference/stages.md](reference/stages.md)
- [reference/manifest.md](reference/manifest.md)
- [reference/stitch-preflight.md](reference/stitch-preflight.md)
- [reference/prototype.md](reference/prototype.md)
- [reference/production-handoff.md](reference/production-handoff.md)
- [reference/enterprise-mapping.md](reference/enterprise-mapping.md)
- Official: https://stitch.google.com/docs/mcp/setup/ · https://github.com/google-labs-code/design.md · https://github.com/google-labs-code/stitch-skills

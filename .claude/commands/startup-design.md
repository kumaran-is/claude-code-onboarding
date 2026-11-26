---
name: startup-design
description: "Run the startup idea → Stitch → DESIGN.md → interactive prototype workflow, then Flutter/Angular/React only after explicit production approval. Use for 'design my startup app', resume an interrupted stage, or check workflow status."
argument-hint: "[idea | resume | status | G0-G10]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch, Agent
---

# /startup-design

Load `.claude/skills/startup-design-to-code/SKILL.md` and follow it. Do not scaffold a production app in this command unless `decisions.production_approved` is true and the user approved production in this session.

**Request:** $ARGUMENTS

## 1. Locate or init

Product root = current workspace, unless `$ARGUMENTS` contains `--root <dir>`.

```bash
GATE="python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py"
$GATE --selftest; echo "STARTUP-DESIGN SELFTEST:$?"
```

Selftest must exit 0 before judging a product. Then:

- `status` or empty after an existing manifest → `$GATE --root <product> --status`
- `resume` → same, then continue `current_stage`
- an idea sentence → `$GATE --root <product> --init --slug <slug> --idea "..."` if the manifest is missing
- `G0`…`G10` → run only that gate

## 2. Run the requested gate

Follow `startup-design-to-code/reference/stages.md`. Stitch: discover live MCP tools (`reference/stitch-preflight.md`). No guessed tool names.

Natural-language equivalents: "help me design my startup app" / "design my startup" / "idea to prototype" start at G0 (or resume). "approve production" is the only phrase that may set production approval, and only when G5 is `PROCEED`.

## 3. Reviewers (existing)

After G4: `ui-standards-expert` if tokens changed. After G7: `design-system-reviewer` + stack reviewer + `accessibility-auditor`. After UI that users will see: `/lint-design-system` and `/verify`. Flutter device E2E is Maestro only.

## 4. Report

```
## Startup design
Stage: …
Next: …
Blocked: …
MCP: none | discovered | mocked
Production approved: yes|no
Gate: $GATE --root <product> → EXIT n
```

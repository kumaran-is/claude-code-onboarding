---
description: "Run the startup idea → Stitch → DESIGN.md → interactive prototype workflow (standalone or from present AWS AI-DLC Ideation/Inception files). Flutter/Angular/React only after explicit production approval in standalone mode; AI-DLC mode hands Construction back to /aidlc. Use for 'design my startup app', resume an interrupted stage, or check workflow status."
argument-hint: "[idea | resume | status | G0-G10 | --mode standalone|aidlc]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch, Agent
---

# /startup-design

Load `.claude/skills/startup-design-to-code/SKILL.md` and follow it. Dual mode: [reference/aidlc-and-standalone.md](../skills/startup-design-to-code/reference/aidlc-and-standalone.md). Do not scaffold a production app unless standalone mode, `decisions.production_approved` is true, and the user approved production in this session. Never start `/aidlc` from this command.

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
- an idea sentence → `$GATE --root <product> --init --slug <slug> --idea "..."` if the manifest is missing. Add `--mode aidlc --bind-aidlc` only when the user asked for the AI-DLC slice (or is already in `/aidlc`) **and** `aidlc/spaces/*/intents/*/aidlc-state.md` exists. An `aidlc/` folder alone stays standalone.
- `G0`…`G10` → run only that gate (G7–G10 are refused in `--mode aidlc`)

## 2. Run the requested gate

Follow `startup-design-to-code/reference/stages.md`. Stitch: discover live MCP tools (`reference/stitch-preflight.md`). No guessed tool names.

Natural-language equivalents: "help me design my startup app" / "design my startup" / "idea to prototype" start at G0 (or resume). "Stitch after AI-DLC inception" uses `--mode aidlc --bind-aidlc`. "approve production" is the only phrase that may set production approval, only in standalone mode, and only when G5 is `PROCEED`.

## 3. Reviewers (existing)

After G4: `ui-standards-expert` if tokens changed. After G7: `design-system-reviewer` + stack reviewer + `accessibility-auditor`. After UI that users will see: `/lint-design-system` and `/verify`. Flutter device E2E is Maestro only.

## 4. Report

```
## Startup design
Mode: standalone | aidlc
Stage: …
Next: …
Blocked: …
MCP: none | discovered | mocked
Production approved: yes|no
Gate: $GATE --root <product> → EXIT n
```

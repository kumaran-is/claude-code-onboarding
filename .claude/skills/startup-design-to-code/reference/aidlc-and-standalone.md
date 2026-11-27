# Standalone vs AWS AI-DLC execution

This skill is a **design slice** (Stitch → DESIGN.md → interactive prototype). It is not AWS AI-DLC and it is not `/next`.

Official AI-DLC artifact layout: [Artifacts Reference](https://awslabs.github.io/aidlc-workflows/guide/14-artifacts-reference/). Intent records live at `aidlc/spaces/<space>/intents/<YYMMDD>-<label>/`. Do not write into that tree from this skill (no `aidlc-state.md` edits, no Construction folders).

## Modes

| Mode | When | G0 | G1–G5 | G6 | G7–G10 / production |
|---|---|---|---|---|---|
| `standalone` (default) | User did not ask for the AI-DLC slice. An `aidlc/` folder alone is not enough. | Write `PRODUCT_BRIEF.md` from the idea | Same | Architecture, then human "approve production" | Existing `/scaffold-*` after approval |
| `aidlc` | User asked (`--mode aidlc`, "Stitch after AI-DLC inception") or is already in `/aidlc`, **and** `aidlc/spaces/*/intents/*/aidlc-state.md` exists | **Consume** present Ideation/Inception files; do not rewrite them | Same | Optional platform **recommendation** only — no scaffold | **Forbidden.** Hand back with `design/AIDLC_HANDOFF.md`. Tell the human to open `/aidlc` for Construction. Do not invoke `/aidlc`. |

AI-DLC is optional. Standalone never requires `/setup-aidlc`. A finished prototype is not production approval in either mode.

Neither `/startup-design` nor `/aidlc` starts the other. Compatibility table: `aws-aidlc-integration/references/compatibility.md`.

## Bind (AI-DLC mode)

```bash
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --init --slug <slug> --idea "<one paragraph>" --mode aidlc --bind-aidlc
# or, after init:
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --bind-aidlc [--intent aidlc/spaces/default/intents/<YYMMDD>-<label>]
```

`--bind-aidlc` **reads** these official paths when present. The product brief prefers Inception `requirements.md`, then `initiative-brief.md`, then the capture statement. Every present file is recorded in `consumed`. Stories and personas are both attached when they exist. `verification/phase-check-ideation.md` is required and must be non-empty. `phase-check-inception.md` is recorded when present and is not a G1 blocker.

| Job | Official files (relative to the intent dir) |
|---|---|
| Brief | `inception/requirements-analysis/requirements.md`, `ideation/approval-handoff/initiative-brief.md`, `ideation/intent-capture/intent-statement.md` |
| Journeys | `inception/user-stories/stories.md`, `inception/user-stories/personas.md`, `ideation/rough-mockups/user-flow.md`, `ideation/scope-definition/scope-document.md` |
| Phase evidence | `verification/phase-check-ideation.md` (required), `verification/phase-check-inception.md` (optional) |

If more than one intent exists, pass `--intent`. If `aidlc/` or a brief file is missing, the bind **BLOCKED** — do not invent requirements. Re-bind after G2+ `PASS` requires `--rebind-aidlc` and resets G2–G5. G0 `PASS` in this mode means those files were **present** and recorded as `aidlc.consumed`, not that this skill approved Ideation.

## Handoff (AI-DLC mode)

After G5 `PROCEED`:

```bash
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --handoff-aidlc
```

Writes `design/AIDLC_HANDOFF.md` in the **product** tree (not under `aidlc/`). Lists DESIGN.md, inventory, prototype, G5 decision, and the optional G6 platform note. Tell the human to open `/aidlc` for Construction. Do not invoke `/aidlc`. `--approve-production` is refused in `aidlc` mode.

## Resume

Re-running a `PASS` stage does not rewrite bound AI-DLC files or approved Stitch IDs. G1 `BLOCKED` (missing Stitch) keeps G0 evidence in place in both modes.

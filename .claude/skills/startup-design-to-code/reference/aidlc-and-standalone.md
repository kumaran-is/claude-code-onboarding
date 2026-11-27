# Standalone vs AWS AI-DLC execution

This skill is a **design slice** (Stitch → DESIGN.md → interactive prototype). It is not AWS AI-DLC and it is not `/next`.

Official AI-DLC artifact layout: [Artifacts Reference](https://awslabs.github.io/aidlc-workflows/guide/14-artifacts-reference/). Intent records live at `aidlc/spaces/<space>/intents/<YYMMDD>-<label>/`. Do not write into that tree from this skill (no `aidlc-state.md` edits, no Construction folders).

## Modes

| Mode | When | G0 | G1–G5 | G6 | G7–G10 / production |
|---|---|---|---|---|---|
| `standalone` (default) | No `aidlc/` workspace, or the team is not using `/aidlc` | Write `PRODUCT_BRIEF.md` from the idea | Same | Architecture, then human "approve production" | Existing `/scaffold-*` after approval |
| `aidlc` | Product already has an AI-DLC intent | **Consume** approved Ideation/Inception files; do not rewrite them | Same | Optional platform **recommendation** only — no scaffold | **Forbidden.** Hand back with `design/AIDLC_HANDOFF.md`. Construction stays `/aidlc`. |

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

`--bind-aidlc` **reads** these official paths when present (first hit wins):

| Job | Official files (relative to the intent dir) |
|---|---|
| Brief | `ideation/intent-capture/intent-statement.md`, `ideation/approval-handoff/initiative-brief.md`, `inception/requirements-analysis/requirements.md` |
| Journeys | `inception/user-stories/stories.md`, `inception/user-stories/personas.md`, `ideation/rough-mockups/user-flow.md`, `ideation/scope-definition/scope-document.md` |
| Phase evidence | `verification/phase-check-ideation.md`, `verification/phase-check-inception.md` |

If more than one intent exists, pass `--intent`. If `aidlc/` or a brief file is missing, the bind **BLOCKED** — do not invent requirements. G0 `PASS` in this mode means those files were found and recorded as `aidlc.consumed`, not that this skill approved Ideation.

## Handoff (AI-DLC mode)

After G5 `PROCEED`:

```bash
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --handoff-aidlc
```

Writes `design/AIDLC_HANDOFF.md` in the **product** tree (not under `aidlc/`). Lists DESIGN.md, inventory, prototype, G5 decision, and the optional G6 platform note. Tell the human to continue Construction with `/aidlc`. `--approve-production` is refused in `aidlc` mode.

## Resume

Re-running a `PASS` stage does not rewrite bound AI-DLC files or approved Stitch IDs. G1 `BLOCKED` (missing Stitch) keeps G0 evidence in place in both modes.

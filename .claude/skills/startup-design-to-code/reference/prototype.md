# Interactive prototype (G5)

A prototype is not a production app. Banner every surface:

`PROTOTYPE — simulated data. Nothing here is an authoritative confirmation.`

## Allowed media (smallest that can test the core journey)

1. Stitch's own preview/prototype tool, if a discovered MCP tool actually exposes it.
2. Standalone HTML/CSS/JS under `design/prototype/` using DESIGN.md tokens as CSS variables.
3. An existing web scaffold only when HTML cannot express the interaction.

Do not scaffold Flutter/Angular/React as the default pilot. Do not call `/scaffold-*` here.

## Minimum behaviour

| Must work | Notes |
|---|---|
| Navigation + back/cancel | Real links or history, not screenshots |
| Core task form | Validation, visible errors, no silent submit |
| Cold load | Layout-matched skeleton, `role="status"`, one visually hidden label |
| Empty and error | Distinct copy and a next action |
| Light and dark | Token pairs, not inverted screenshots |
| Responsive | Compact phone as default; desktop if the brief includes it |
| Accessibility | Labels, focus, 44px targets, `prefers-reduced-motion` |
| Offline (if the brief requires it) | Truthful banner; cached content stays if you simulate a cache |

High-risk actions (pay, approve, grant access) must say **simulated** in the success copy. Local `localStorage` is not persistence.

## Contract check

```bash
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --check-prototype
```

Looks for the prototype banner, navigation, a form, a `role="status"` (or skeleton), empty and error copy, and a dark-mode or `color-scheme` hook. It does not prove usability.

## G5 decision

After the human reviews evidence (even a founder-only walkthrough), set `decisions.g5` to `PROCEED`, `ITERATE` or `STOP`. Do not infer PROCEED from a pretty HTML file.

# Production translation (G6–G10)

G6 records the platform. G7–G10 write application code **in standalone mode only**. The gate refuses G7+ until `decisions.production_approved` is true **and** the user said so in this session. In **aidlc** mode, G7–G10 are forbidden; `--approve-production` is refused; run `--handoff-aidlc`, then tell the human to open `/aidlc` for Construction. Do not invoke `/aidlc`.

## G6 — architecture only

Choose from product needs, not from whichever screenshot looked nicest.

| Platform | Skill | Scaffold | Tokens |
|---|---|---|---|
| Flutter | `flutter-mobile` | `/scaffold-flutter-app` | DESIGN.md → ThemeData / ThemeExtension |
| Angular | `angular-spa` + `ui-mode-selection.md` | `/scaffold-angular-app [--ui=daisyui\|spartan\|hybrid]` | DESIGN.md → Tailwind v4 `@theme` |
| React | `react-spa` + `shadcn` | `/scaffold-react-app` | DESIGN.md → Tailwind v4 + shadcn tokens |

One token authority. Atomic Design + smart/dumb: `atomic-decision-tree.md`. Screenshot HTML is reference, not a template to paste.

Angular UI mode is chosen once. Hybrid ownership is `ui-mode-selection.md` §4.

Set `decisions.platform` with `--g5` for the human PROCEED/ITERATE/STOP (this does not set `production_approved`). Angular also needs `angular_ui_mode`. Still no app. In **aidlc** mode G6 only records that platform note — do not run `architecture-design` into API contracts or ADRs.

## Approval line (required)

The user must say they want production (for example: "approve production" / "build the Flutter app"). Then:

```bash
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --approve-production --approved-by "<user>"
```

## G7 — one screen at a time

1. Fetch the **approved** Stitch version with a discovered tool. If MCP is down: BLOCKED, keep code.
2. Read DESIGN.md sections this screen uses.
3. Record atoms / molecules / organisms and the smart container.
4. Map values to tokens. Run `/lint-design-system`.
5. Implement states from the brief, not only the happy screenshot.
6. Framework-native widgets. `screenshot-to-flutter` / `screenshot-to-angular` only as translators of *approved* references, still through tokens.

When G4 already passed, do **not** let `/scaffold-*` write a new `DESIGN.md`. Map the existing file into ThemeData / Tailwind `@theme` / shadcn tokens. A second `DESIGN.md` is drift — stop.

Standalone G7–G10 is **UI translation only**. Behaviour stories, the PR, and release stay on `/next` and `/ship`.

Do not install a second state library. Do not mix daisyUI and Spartan outside hybrid ownership. Do not import Stitch HTML into Flutter.

Official `stitch::react-components` may assist React **after** architecture review; it does not skip smart/dumb or this toolkit's React skill.

## G8–G10

G8: `interaction-contracts.md` §6b–6c. G9: `accessibility-auditor` + Playwright (web) or Maestro (Flutter device). Missing device → BLOCKED, never a browser substitute. G10: keep inventory IDs, DESIGN.md revision and implementation mapping together; `design.md diff` before token changes.

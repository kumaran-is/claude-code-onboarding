---
description: Run the design-system gate across Flutter and web (Angular, React) — DESIGN.md discovery, literal colours/spacing/typography, inline styles, daisyUI 4 classes, tier markers, presentational boundaries, icon family and isolation, animation runtimes and parallel token scales
allowed-tools: Bash, Glob, Grep, Read
---

# /lint-design-system

Run the project's design-system gate. One detector serves this command, `/verify` and CI: `.claude/scripts/check-design-system.py`. It proves every detector on planted fixtures before it reads a project file (exit 2 = a detector is broken; nothing was judged).

## 1. Run

```bash
python3 .claude/scripts/check-design-system.py --root . > /tmp/ds-gate.log 2>&1; echo "DESIGN GATE EXIT:$?"; cat /tmp/ds-gate.log
# changed files only (no project-level checks such as icon family or parallel scales):
python3 .claude/scripts/check-design-system.py --root . --files $(git diff --name-only --diff-filter=AM HEAD) ; echo "EXIT:$?"
# a project that has adopted DESIGN.md can make its absence an error:
python3 .claude/scripts/check-design-system.py --root . --require-design-md; echo "EXIT:$?"
```

Exit codes: `0` PASS (warnings may print), `1` FAIL (errors), `2` BROKEN (detector selftest failed or bad usage). `NOT APPLICABLE` prints when no Flutter, Angular or React source exists under the root. Report the gate's own exit code; never pipe it into `tail`/`grep` before reading it. The `--files` form is vacuous when nothing changed: say how many files it saw.

## 2. What it checks

| Rule | Stack | Flags | Use instead |
|---|---|---|---|
| `DS-COLOR` | all | `Color(0x…)`, `Color.from(…)`, `Colors.red`, any quoted string that is exactly a hex colour in web code (status maps, constants, ternaries, `statusColor="#E53935"`; lines with `href`/`fragment`/`routerLink`/`id` skipped), a theme variable re-declared with a literal outside the global stylesheet, `bg-[#…]`, `color: #…`, `oklch(…)` outside token definitions, Tailwind named palettes (`text-red-500`) | `colorScheme`/ThemeExtension roles; `bg-primary`, `text-base-content`, `text-muted-foreground`, `var(--color-…)` |
| `DS-SPACING` | all | `EdgeInsets.all(13)`, `SizedBox(height: 12)`, `SizedBox.square(dimension: 13)`, `p-[13px]`, `padding: 12px`, `style={{ margin: 8 }}` | `AppSpacing.*`; Tailwind numeric scale (`p-3`, `gap-2`) |
| `DS-SHAPE` | all | `BorderRadius.circular(12)`, `Radius.circular(8)`, `border-radius: 13px`, `rounded-[13px]`, `--radius-card: 3px` outside the global stylesheet | `AppRadius.*`; `rounded-box`/`rounded-field`, `var(--radius-…)` |
| `DS-TYPE` | all | `fontSize: 18`, `fontFamily: '…'`, `text-[15px]`, `font-[…]`, `font-size:`/`font-family:` in component styles | `TextTheme` roles; `text-sm`, `text-lg`, theme font |
| `DS-INLINE-STYLE` | Angular | `style="…"` in templates | utilities / component styles with tokens |
| `DS-DAISYUI4` | web | `input-bordered`, `form-control`, `label-text`, `card-bordered`, `btn-group` | v5 `input`, `fieldset`/`fieldset-legend`, `label`, `card-border`, `join` |
| `DS-SPACING-SHADOW` | web | `--spacing-xs…2xl:` (shadows `max-w-*` in Tailwind 4) | default `--spacing` multiplier |
| `DS-TIER` | all | shared-library component without line-1 `// Tier: Atom\|Molecule\|Organism` | decision tree: `design-system/reference/atomic-decision-tree.md` |
| `DS-PRESENTATIONAL` | all | shared-library component using Riverpod `ref`, repositories, `HttpClient`, injected services/stores, TanStack Query, global stores, `fetch`, `features/` imports | move data work to the smart container; pass tone/variant enums |
| `DS-ICON-ISOLATION` / `DS-ICON-FAMILY` | all | icon package imported in feature code; more than one icon family per app | the project icon wrapper; one family (DESIGN.md) |
| `DS-ANIM` | all | Lottie/Rive runtime imported outside a shared animation wrapper | the wrapper (lifecycle, static fallback, reduced motion) |
| `DS-SCALE` | Flutter | two classes for one token family anywhere in the workspace (`AppSpacing` + `SpacingTokens`, or `AppSpacing` in two packages) | one scale per family |
| `DS-AUTHORITY` | Flutter | colour literals in more than one token root (`lib/theme/` beside `design_system/`) | one token root |
| `DS-REDUCED-MOTION` | web | a daisyUI `loading-*` indicator in an app whose global stylesheet lacks the `.loading` reduced-motion override (SMIL ignores the media query) | the override in `src/styles.css` (`daisyui-v5-components.md`) or `motion-reduce:hidden` |
| `DS-MUTED-TEXT` | web (warning) | `text-base-content/10`…`/50` on text | `/60` on `base-100`, `/70` on `base-200`/`base-300` |

Out of scope by design: token-definition files and CSS custom-property declarations (that is where literals belong), generated files, tests, and CLI-owned UI-kit folders (`src/components/ui/`, Spartan `libs/ui/`). Literal `Duration(...)` values are not flagged (timeouts and debounces are legitimate): motion durations are a review item (`AppMotion`). Touch-target size, contrast in context and label association are runtime/accessibility checks and the `accessibility-auditor` agent's job.
- Flutter targets: widget tests with `androidTapTargetGuideline` / `textContrastGuideline`; device flows with Maestro.
- Web targets (Angular, React): Playwright + axe.

## 3. Report

```
## Design System Lint Report
DESIGN.md: <path> (canonical) | missing (warning)
Gate: python3 .claude/scripts/check-design-system.py --root . → EXIT <n>
Scanned: <N> files (flutter a, angular b, react c)
Findings: <file:line> <RULE> <message> :: <snippet>   (one per line, as printed)
Status: PASS / FAIL / BROKEN / NOT APPLICABLE
```

## 4. Exception policy

`ignore-design: <reason>` (12+ characters of reason) on the hit line or the comment line directly above exempts that line only. A bare marker, a short reason or a marker elsewhere in the file does not. Tier markers cannot be exempted: move a non-component file out of the governed folder instead. Five or more markers in one file means the design system needs extending: raise it.

## Scope

- Flutter: `lib/` of each app and package (`pubspec.yaml` root). Angular / React: `src/` of each `package.json` root that depends on `@angular/core` / `react`.
- Run before `/review-code`; `/verify` runs the same gate for UI stacks.

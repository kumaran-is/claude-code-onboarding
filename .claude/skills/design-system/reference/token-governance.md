# Token, Icon and Motion Governance (Flutter, Angular, React)

One authority per token family, implemented once per stack, referenced everywhere else by name. Values belong to the project's DESIGN.md (`design-md-governance.md`); this file defines where they live and how they are enforced.

## 1. Where tokens live (one authority per stack)

| Family | Flutter | Angular (daisyUI / Spartan / hybrid) | React (shadcn) |
|---|---|---|---|
| Colour roles (light + dark, same names) | `ColorScheme` in `app_color_scheme.dart` + a `ThemeExtension` for roles Material lacks (success, warning, info, brand) | daisyUI: `@plugin "daisyui/theme"` blocks in `styles.css`. Spartan: the CSS variables in its theme stylesheet. Hybrid: daisyUI owns the variables and Spartan's variables are mapped onto them (one set of values) | `:root` and `.dark` CSS variables in `src/index.css`, exposed to Tailwind through `@theme inline` |
| Typography roles | `TextTheme` built in `app_text_theme.dart` (+ product numeric roles in an extension) | Tailwind 4 `--text-*` / `--font-*` theme variables; utilities `text-sm`… | same |
| Spacing | `AppSpacing` (+ `AppSize` minimums) | the Tailwind `--spacing` multiplier (`p-4`, `gap-2`) | same |
| Shape / radius | `AppRadius`, wired into component themes | `--radius-*` (daisyUI `--radius-box/field/selector`) | `--radius` + derived `rounded-*` |
| Elevation | `AppElevation` + `ColorScheme.shadow`/surface tint | daisyUI depth / `shadow-*` theme values | `shadow-*` theme values |
| Motion | `AppMotion` (durations, curves, `AppMotion.of` for reduced motion) | `--animate-*` / transition tokens + `prefers-reduced-motion` | same |
| Opacity | named alphas in the extension (`withValues(alpha:)`) | `color-mix(in oklch, var(--color-…) N%, transparent)` or `/NN` on semantic utilities | same |

Rules:
- **One scale per family, one authority.** Enforced by the gate: a second spacing/radius/motion class anywhere in the workspace (`DS-SCALE`), Dart colour literals in more than one token root (`DS-AUTHORITY`), a theme variable re-declared with a literal outside the global stylesheet (`DS-COLOR`), literal radii (`DS-SHAPE`). Not enforced (review item): a parallel token folder that holds no literals, or CSS variables duplicated under new names that point at existing tokens.
- **Light and dark are both first-class**: every role exists in both modes under the same name; never branch on brightness in feature code to pick a colour. Theme mode changes colour only (size, weight, spacing identical).
- **Derived tokens reference base tokens** (never copy the value). Component defaults (inputs, cards, buttons, dialogs, sheets, toasts) are configured once in the theme, not per call site.
- **Feature code never imports raw palettes** (`ColorTokens`, `--palette-*`): only roles.
- **Status is never colour alone**: text label (required) + icon or shape + semantic token. Error-state colour ≠ business-negative colour.
- **Contrast is tested from live tokens, both modes** (text ≥ 4.5:1, large text and UI ≥ 3:1, focus indicator ≥ 3:1 and ≥ 2 px), not from a hand-maintained list.
- **Tailwind 4 named palettes** (`text-red-500`, `bg-slate-100`) and arbitrary values (`p-[13px]`, `text-[15px]`, `bg-[#…]`) are literals: use semantic utilities (`bg-primary`, `text-muted-foreground`, `text-base-content`).

## 2. Icons

- **Exactly one icon family per app**, named in DESIGN.md. The toolkit does not mandate a family: Material Symbols/`Icons` is the Flutter default; Lucide is already the family of shadcn (`lucide-react`) and Spartan (`@ng-icons/lucide`), so a project on those kits uses Lucide everywhere rather than adding a second set.
- **Provider isolation:** only the icon wrapper/registry (a file named `*icon*` or inside the shared UI library) and the CLI-owned UI-kit folders import the icon package or call `Icons.*` / `CupertinoIcons.*`. Feature code uses semantic names (`AppIcons.delete`, `<app-icon name="delete">`, `<Icon name="delete" />`). Gate rules `DS-ICON-ISOLATION`, `DS-ICON-FAMILY`. Framework/system chrome that must call `Icons.*` (Material date-picker internals, a platform adaptive back inside the wrapper) uses `ignore-design: <12+ char reason>` on that line.
- One typed vocabulary: concept → one glyph. Two variants only (outline default; filled = selected/active). One closed size ramp (default 24), colour from a closed semantic union including `currentColor`.
- **Accessibility:** an icon-only control is an icon-button atom with a required accessible name describing the action (`tooltip`/`semanticLabel`, `aria-label`) and a ≥ 44 px / 48 dp target; decorative icons are hidden (`ExcludeSemantics`, `aria-hidden="true"`). Primary CTAs, status badges and nav items always carry text.
- **RTL:** directional glyphs (back, forward, chevrons, send) mirror via per-glyph registry metadata; check one RTL render.
- **Motion:** icon swaps cross-fade or rotate ≤ 90° using motion tokens; no pulsing attention loops; reduced motion makes the swap instant.

## 3. Motion and animation

| Need | Engine |
|---|---|
| Everyday state change (enter/leave, expand, press, route) | Flutter implicit/explicit animations with `AppMotion`; Angular `animate.enter`/`animate.leave` + CSS transitions/keyframes (the legacy `@angular/animations` DSL has a migration guide away from it); React CSS transitions/keyframes (`tw-animate-css` utilities) |
| Decorative timeline (celebration, empty-state illustration) | Lottie (`lottie` / `lottie-web`) through ONE shared wrapper |
| Interactive state machine driven by data or input | Rive through ONE shared wrapper |

- Never install an animation runtime as a side effect of a task: adding Lottie or Rive is a dependency decision recorded in DESIGN.md Motion (native/CSS is the default). Gate rule `DS-ANIM` flags a runtime imported outside the shared library wrapper (a feature file named `*_animation*` is not a wrapper). Gate rule `DS-ANIM-DECISION` flags a `lottie`/`rive` dependency whose name is absent from DESIGN.md Motion.
- Wrappers own lifecycle (pause off-screen/backgrounded), a static fallback, size budget and reduced motion.
- Durations and curves are tokens on a fixed scale (≤ ~600 ms for standard UI motion); motion explains a state change, never decorates by default.
- **Reduced motion is built in, not per screen:** Flutter `MediaQuery.disableAnimationsOf(context)` → `Duration.zero` (`AppMotion.of`); web `@media (prefers-reduced-motion: reduce)` disables transitions/keyframes and the skeleton shimmer. Test it once per wrapper. Library animations that are not CSS animations escape both the media query and `document.getAnimations()`: daisyUI 5 `loading` spinners animate through SMIL inside `mask-image` and keep spinning under reduced motion. The global stylesheet templates (`angular-spa/reference/daisyui-v5-components.md`, hybrid in `ui-mode-selection.md` §6) turn `.loading` into a static dot under reduced motion (verified: hybrid Playwright reduced-motion test red before, green after, control still animates); gate rule `DS-REDUCED-MOTION` fails an app that uses `loading-*` indicators without that override or a per-element `motion-reduce:hidden`. Browser tests also check computed `mask-image` for `<animate`, not only `document.getAnimations()`.

## 4. Enforcement map

| Layer | What | Where |
|---|---|---|
| Write-time advisory | literal colour/spacing/type, tier marker, presentational imports | `.claude/hookify.design-*.local.md` (delivered as `additionalContext`) |
| Blocking gate | everything above + inline styles, daisyUI 4 classes, icon family/isolation, `Icons.*` in feature UI, animation runtimes and DESIGN.md engine records, refresh-strategy markers, parallel scales, DESIGN.md discovery | `python3 .claude/scripts/check-design-system.py --root .` (selftest runs first; exit 2 = broken detector) |
| Callers | local, verification, CI | `/lint-design-system`, `/verify` (UI stacks), the project's CI step |
| Review | tiers, slots, tone mapping, states, refresh records, UX quality | `design-system-reviewer`, `ui-standards-expert`, `accessibility-auditor` |
| Runtime | contrast both modes, 200 % text, RTL, reduced motion, async transitions | the project's widget/component tests and Playwright (web) / Maestro (Flutter mobile) |

Escape hatch (all layers): `ignore-design: <reason>` on the hit line or the line directly above. The gate requires a reason of at least 12 characters; review every marker like debt.

# Design-system requirements-to-evidence matrix

Durable audit trace for `feat/flutter-mobile-engineering-best-practices`. Replaces the scratchpad matrix that lived only under `/tmp`. Source of the original 22 rows: [`design-system-governance-final-verification.md`](design-system-governance-final-verification.md). This file records enforcement after the 2026-11-26 P2 close-gaps round.

Gate: `python3 .claude/scripts/check-design-system.py` (selftest first; exit 2 = broken detector). Hooks are advisory.

| ID | Requirement | Source | Implementation | Enforcement | Positive test | Negative test | Status |
|---|---|---|---|---|---|---|---|
| DS-R1 | DESIGN.md discovery, precedence, missing-file | `design-md-governance.md`; prior audit DS-R1 | scaffolds write skeleton; gate prints canonical path | `check-design-system.py` discover + `--require-design-md` | 5 apps print canonical DESIGN.md | missing → warning; `--require-design-md` → `DS-DESIGN-MD` | PASS |
| DS-R2 | Three tiers, line-1 `// Tier:` | atomic-decision-tree | DART_LIB / NG_LIB / RX_LIB | `DS-TIER`; hookify `design-tier-comment-*` | governed files carry markers | `// Tier: atom` / missing line 1 | PASS |
| DS-R3 | Dumb button isBusy/tone/onPressed | color-system; DESIGN.md | fixtures in gate | `DS-PRESENTATIONAL` (clean) | `primary_button.dart` / `badge.tsx` | — | PASS |
| DS-R4 | Dumb HTTP → FAIL | DESIGN.md 1585 | presentational regex | `DS-PRESENTATIONAL` | `fetcher.component.ts`, `fetch(` | DOM `inject(ElementRef)` clean | PASS |
| DS-R5 | Angular domain inject → FAIL | DESIGN.md 1634 | `inject()` + constructor | `DS-PRESENTATIONAL` | `AuthSession`, `DashboardApi` | `ElementRef` / `Renderer2` | PASS (F1r residual P2) |
| DS-R6 | React global store → FAIL | DESIGN.md 1585 | zustand / features / `useContext(*StoreContext)` | `DS-PRESENTATIONAL` | `useCartStore`, `useContext(CartContext)` | `useContext(ThemeContext)` | PASS |
| DS-R7 | Flutter atom importing feature repo → FAIL | DESIGN.md 1587 | path regex | `DS-PRESENTATIONAL` | `order_repository.dart` import | — | PASS (n7 residual) |
| DS-R8 | Smart container passes semantic status | color-system | fixtures | — | `StatusTone.warning` clean | raw hex `DS-COLOR` | PASS |
| DS-R9 | Raw hex for business status | color-system; DESIGN.md | web quoted-hex + Dart `Color(0x)` | `DS-COLOR` | `{ id: 1, hex: '#E53935' }`, status maps, ternaries | `href="#add"`, `fragment="#bad"`, `id="feed"` | PASS |
| DS-R10 | No parallel token authorities | DESIGN.md; spacing std | `DS-SCALE`, `DS-AUTHORITY`, web `DS-SHAPE`/`DS-COLOR` | gate project-level | `brand_colors.dart`, `border-radius: 13px` | global `src/styles.css` / `index.css` | PASS (F3r/F21 P3) |
| DS-R11 | One icon family; wrapper isolation | icon-system; DESIGN.md | package imports + Flutter `Icons.*` | `DS-ICON-ISOLATION`, `DS-ICON-FAMILY` | `Icon(Icons.delete)` in feature; phosphor in feature | `app_icons_registry.dart`; `ignore-design` date-picker chrome; shared `primary_button` `Icons.check` | PASS |
| DS-R12 | Async states content-first | loading std; DESIGN.md | `interaction-contracts.md` §6b; scaffold skeletons | review + templates (not a state-machine gate) | daisyUI/React/Flutter transition tests (prior round); Spartan/hybrid templates now skeleton | mutation/submit still use spinner | PARTIAL (runtime re-scaffold NOT RUN) |
| DS-R13 | Refresh strategy record | refresh std §3/§6/§13 | `refresh-strategy:` marker | `DS-REFRESH` | `RefreshIndicator` / `react-simple-pull-to-refresh` without marker | marker present; background-only screen with no PTR | PASS |
| DS-R14 | Animation engine decision | animation-strategy | DESIGN.md Motion + shared wrapper | `DS-ANIM`, `DS-ANIM-DECISION` | `celebration_animation.dart` in features; `rive` dep without Motion mention | shared `app_lottie.dart`; `lottie` named in DESIGN.md Motion | PASS |
| DS-R15 | Reduced motion | animation-strategy §12 | `.loading` override; `DS-REDUCED-MOTION` | gate + Playwright (prior) | override removed → exit 1 | override present → exit 0 | PASS |
| DS-R16 | 55 mobile UX principles | prior audit F13; `mobile-ux-principles.md` | `mobile-ux-principles.md` | review (not gated) | 55 mapped; 13 missing stated here | no product names in the principles file | PASS |
| DS-R17 | daisyUI / Spartan / hybrid / React+shadcn preserved | DESIGN.md role map | `ui-mode-selection.md`; CLI-owned folders excluded | `UI_KIT` skip; `angular-ui-mode.sh` | prior unit/PW on four web apps | — | PASS |
| DS-R18 | Enforcement only where reliable | SOURCE scripts | selftest + hook tests | selftest exit 2 if detector removed | mutations below | anchors / ThemeContext / no-PTR screens | PASS |
| DS-R19 | Context budget | toolkit | `check-context-budget.sh --strict` | CI | ≤ 62000, canaries | — | PASS (re-run this round) |
| DS-R20 | Hookify design rules committed | `.gitignore` negation | `!.claude/hookify.design-*.local.md` | git | 11 design rules tracked | personal `*.local.md` ignored | PASS |
| DS-R21 | No product branding in toolkit files | all SOURCE | toolkit-only language | grep of `+` lines | 0 product/persona names in skills/hooks/gate/templates | — | PASS |
| DS-R22 | Flutter 3.50 scaffold | scaffold-flutter-app | `flutter: ">=3.50.1"` | SDK check | — | local 3.44.2 | BLOCKED |
| DS-R23 | Maestro device tests | testing-tool-selection | Maestro only for Flutter UI | device required | — | Maestro 2.11.0; 0 booted simulators | BLOCKED |

## Mutation controls (2026-11-26)

Each new/changed detector is removed in a copy of `check-design-system.py`; `--selftest` must exit 2:

- quoted-hex `id` skip (anchor-only filter) — `id-hex.ts` expected `DS-COLOR`
- Flutter `Icons.*` isolation — `delete_screen.dart` expected `DS-ICON-ISOLATION`
- React `useContext(CartContext)` — `cart-icon.tsx` expected `DS-PRESENTATIONAL`
- `DS-REFRESH` — `feed_screen.dart` expected `DS-REFRESH`
- `DS-ANIM` library-only wrapper — `celebration_animation.dart` expected `DS-ANIM`
- `DS-ANIM-DECISION` — `rive_app` expected project-level finding

## Deferrals

| ID | Why |
|---|---|
| DS-R12 runtime | Disposable `ng-spartan` / `ng-hybrid` apps from the prior session are gone. Templates and the scaffold command now emit skeletons. Full re-scaffold + Playwright is NOT RUN this round. |
| DS-R22 | Local Flutter 3.44.2; do not bypass `>=3.50.1`. |
| DS-R23 | No booted simulator; do not substitute a browser for Maestro. |
| F1r, F3r, F7, F11, F15, F17–F22 | P2/P3 residuals from the prior audit, not in this close-gaps list. |
| Angular `users` vs `dashboard` sample routes | Two documented examples, not one broken path. |
| Hybrid component-list vs Helm catalog | Ownership table in `ui-mode-selection.md` §4 is the contract; not a silent generator bug. |

## Toolkit vs merge

- **Toolkit:** READY for the P2 close-gaps that are enforceable in-repo (gate, hooks, templates, matrix).
- **Merge:** NEEDS_REVIEW until Flutter 3.50 scaffold runs and Maestro has a device. Spartan/hybrid runtime re-scaffold remains NOT RUN.

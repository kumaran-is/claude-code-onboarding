---
name: design-system
description: "Unified design system enforcement for Flutter and Angular. Routes all UI tasks through the correct stack-specific tokens, rules, and interaction contracts. Use when auditing UI compliance, reviewing design consistency, or building any user-facing surface."
allowed-tools: Read, Glob, Grep, Write, Edit
metadata:
  triggers: design system, UI audit, design tokens, design review, design lint, visual consistency, theme compliance, design drift
  related-skills: ui-standards-tokens, angular-spa, flutter-mobile, frontend-design, accessibility-auditor
  domain: frontend
  role: specialist
  scope: design
  output-format: document
last-reviewed: "2026-03-15"
---

**Iron Law:** Never hardcode colors, spacing, or typography — always use design tokens; run /lint-design-system before declaring any UI change complete.

# Design System — Unified Routing Hub

Single entry point for all design system enforcement across Flutter and Angular.

**When to use:** Any UI task — building screens, reviewing components, auditing design drift, or running design lint.

## Routing Table

Determine the stack from file context, then load the correct references:

```
What are you working on?
    |
    +-- Flutter (lib/**/*.dart, pubspec.yaml)
    |   |
    |   +-- Tokens (colors, spacing, typography, radius)
    |   |   → Read: .claude/skills/ui-standards-tokens/reference/ui-design-tokens.md
    |   |
    |   +-- Accessibility (semantics, focus, contrast)
    |   |   → Read: .claude/skills/ui-standards-tokens/reference/ui-accessibility-patterns.md
    |   |
    |   +-- Polish (animations, glassmorphism, theme extensions)
    |       → Read: .claude/skills/flutter-mobile/reference/flutter-design-polish.md
    |
    +-- Angular (src/app/**/*.ts|html|scss)
    |   |
    |   +-- Component styling (daisyUI classes, semantic tokens)
    |   |   → Read: .claude/skills/angular-spa/reference/daisyui-v5-components.md
    |   |
    |   +-- Tailwind config (spacing, breakpoints, CSS vars)
    |   |   → Read: .claude/skills/angular-spa/reference/tailwind-v4-config.md
    |   |
    |   +-- Conventions (design principles, form patterns)
    |   |   → Read: .claude/skills/angular-spa/reference/angular-conventions.md
    |   |
    |   +-- Animations (timing, keyframes, reduced motion)
    |       → Read: .claude/skills/angular-spa/reference/animations.md
    |
    +-- Cross-stack (interaction contracts, visual direction)
        |
        +-- Surface/interaction contracts (modals, forms, lists, errors)
        |   → Read: .claude/skills/design-system/reference/interaction-contracts.md
        |
        +-- Visual design direction (anti-patterns, typography philosophy)
            → Read: .claude/skills/frontend-design/reference/frontend-design-principles.md
```

## Before Writing UI — Pre-Flight

Answer before writing; a "no" means fix the plan first.

1. Does a shared component or screen already solve this? (Reuse before create.)
2. Are all values tokens, with no parallel one-off style?
3. Is every state designed? See the async-state contract in [interaction-contracts.md](reference/interaction-contracts.md) §6b (loading class, empty, error, offline, pending).
4. Does it show only truthful state (nothing reads as confirmed before the server confirms)?
5. Does it reflow at 200% text scale and with the keyboard open and system insets applied?
6. Does it look right in light and dark?
7. Any added chrome, duplicate CTA for a destination already in persistent navigation, or a card nested in a card?
8. Does motion earn its place? See the "Before you animate" gates in `.claude/skills/flutter-animations/SKILL.md`.
9. Would this only create churn? If the screen already meets the standard, say so; do not redesign for its own sake.

## Design Rules — Hard Policy (Both Stacks)

These are non-negotiable. Violations are caught by hookify rules at write-time.

### Colors
- **NEVER** hardcode hex values (`#3b82f6`, `Color(0xFF...)`)
- **NEVER** use `rgb()`, `rgba()`, `hsl()`, `hsla()` literals
- **Flutter:** Use `Theme.of(context).colorScheme.*`; `Color.withOpacity` is deprecated — use `withValues(alpha: ...)`
- **Angular:** Use daisyUI semantic tokens (`bg-primary`, `text-base-content`)

### Spacing
- **NEVER** use raw numeric spacing (`EdgeInsets.all(16)`, `mt-3`)
- **Flutter:** Use `AppSpacing.xs/sm/md/lg/xl/xxl`
- **Angular:** Use Tailwind semantic scale or daisyUI component spacing

### Typography
- **NEVER** use raw font sizes (`TextStyle(fontSize: 14)`, `text-[14px]`)
- **Flutter:** Use `Theme.of(context).textTheme.*`
- **Angular:** Use Tailwind typography scale (`text-sm`, `text-lg`, `text-xl`)

### Forms
- **NEVER** use bare `<input>`, `<select>`, `<textarea>` without framework bindings
- **Angular:** Use daisyUI form classes + reactive form `formControlName`
- **Flutter:** Use shared form field wrapper widgets

### Touch Targets
- **Minimum 48dp** (Flutter) / **44px** (Angular) for all interactive elements

### Inline Styles
- **NEVER** use `style="..."` in Angular templates — use Tailwind utilities or SCSS
- **NEVER** use inline `Style` widgets in Flutter — use theme extensions

## Machine Enforcement

### Hookify Rules (fire on every Write/Edit by Claude)

| Rule | Stack | What It Catches |
|------|-------|-----------------|
| `hookify.design-no-hardcoded-colors-dart` | Flutter | `Color(0xFF...)`, `Colors.blue` |
| `hookify.design-no-raw-spacing-dart` | Flutter | `EdgeInsets.all(16)`, `SizedBox(height: 8)` |
| `hookify.design-no-raw-textstyle-dart` | Flutter | `TextStyle(fontSize: N)` |
| `hookify.design-no-hex-angular` | Angular | `bg-[#...]`, `color: #...`, `rgb()`, `hsl()` |
| `hookify.design-no-raw-spacing-angular` | Angular | `mt-3`, `px-4`, `gap-2` |
| `hookify.design-no-raw-typography-angular` | Angular | `text-[14px]`, `font-[...]`, `font-size: N` |
| `hookify.design-no-raw-form-inputs` | Angular | bare `<input>`, `<select>` without `formControl` |

All rules respect `// ignore-design: [reason]` exception markers.

### Lint Commands

| Command | Scope |
|---------|-------|
| `/lint-design-system` | Orchestrator — runs all checks for detected stack(s) |
| `dart analyze` | Flutter static analysis |
| `ng lint` | Angular static analysis |

### Quality Gate

Before declaring any UI work done, these must pass (from `verification-and-reporting.md`):

- [ ] No hardcoded colors — all colors use theme tokens
- [ ] No raw spacing values — all spacing uses semantic tokens
- [ ] No inline TextStyles — all typography uses theme text styles
- [ ] Touch targets >= 48dp (Flutter) / 44px (Angular)
- [ ] `/lint-design-system` run with zero violations
- [ ] Exception markers (`// ignore-design: [reason]`) reviewed and justified

## Exception Policy

When a design rule must be violated intentionally:

1. Add inline marker: `// ignore-design: [short reason]` or `<!-- ignore-design: [reason] -->`
2. Reason must explain WHY (e.g., "platform-specific iOS styling", "third-party widget constraint")
3. Exceptions are reviewed like code debt
4. Periodically audit: search for `ignore-design` and remove stale exceptions
5. If 5+ exceptions accumulate in one file → the design system may need extending, flag it

## Scope & Rationale

### What We Enforce

| Surface | Status | Rationale |
|---------|--------|-----------|
| **Logged-in app screens** (Flutter + Angular) | ENFORCED | Primary user experience — consistency here drives retention and trust |
| **Shared/reusable components** | ENFORCED | Foundation — drift here cascades everywhere |
| **Theme definitions** | ENFORCED | Single source of truth for tokens |

### What We Defer

| Surface | Status | Rationale |
|---------|--------|-----------|
| **Admin panels / internal tools** | DEFERRED | Lower user impact — enforce when dedicated redesign pass happens |
| **Legacy/migration pages** | DEFERRED | Will be replaced — enforce on new version only |
| **Marketing / landing pages** | DEFERRED | Often need custom creative direction that conflicts with app tokens |
| **Test files** | EXCLUDED | Test code can use raw values for assertion clarity |
| **Generated code** (`*.g.dart`, `*.freezed.dart`) | EXCLUDED | Machine-generated — not human-authored |

### File Path Scope

| Stack | Included | Excluded |
|-------|----------|----------|
| Flutter | `lib/` | `test/`, `*.g.dart`, `*.freezed.dart`, build output |
| Angular | `src/app/` | `node_modules/`, `*.spec.ts`, config files |

## Visual Audit — 10-Dimension Scoring

Score the current UI across these 10 dimensions (0–10 each). For each dimension provide: score, specific file:line example, and a concrete fix.

1. **Color consistency** — Are colors using theme tokens (`bg-primary`, `colorScheme.primary`) or hardcoded hex values (`Color(0xFF3b82f6)`, `#3b82f6` in SCSS)?
2. **Typography hierarchy** — Clear h1 > h2 > h3 > body > caption scale using `Theme.of(context).textTheme.*` (Flutter) or Tailwind typography scale (`text-sm`, `text-lg`, `text-xl`) (Angular)? Or raw `TextStyle(fontSize: N)` / `text-[14px]` scattered throughout?
3. **Spacing rhythm** — Consistent 4px/8px/16px scale via `AppSpacing.*` (Flutter) or Tailwind semantic scale (Angular)? Or arbitrary `EdgeInsets.all(16)` / `mt-3` / `px-4` that break the grid?
4. **Component consistency** — Do similar elements (buttons, cards, list items, form fields) use the same widget/component patterns, or are there one-off inline implementations?
5. **Responsive behavior** — Fluid across breakpoints? Angular: Tailwind `sm:`/`md:`/`lg:` breakpoints applied? Flutter: `LayoutBuilder` / `MediaQuery` used for adaptive layouts?
6. **Dark mode** — Complete theme coverage using `colorScheme` (Flutter) / daisyUI semantic tokens (Angular)? Or half-done with hardcoded light values that break in dark mode?
7. **Animation** — Purposeful (entrance transitions, state changes, feedback)? Or gratuitous scroll-triggered animations on every section that distract rather than guide?
8. **Accessibility** — Color contrast ≥ 4.5:1 for normal text / ≥ 3:1 for large text, focus states present, touch targets ≥ 48dp (Flutter) / 44px (Angular), semantic labels on interactive elements?
9. **Information density** — Cluttered (too many competing elements) or too sparse (wasted space)? Empty states handled with meaningful UI rather than blank screens or raw `null` renders?
10. **Polish** — Hover states (Angular), loading states (`CircularProgressIndicator` / skeleton screens), error states (user-visible feedback), and micro-transitions present and consistent?

**Total score / 100.**
- **≥ 80** — Ship-ready. Minor issues only.
- **60–79** — Polish pass needed before release.
- **< 60** — Redesign required. Do not ship.

For each dimension scored below 7: file the specific file:line violation and state the concrete fix using the correct token or pattern for the stack.

## AI Slop Detection

Flag these patterns immediately — they signal generic AI-generated UI with no design intention. Each flag requires the exact file:line and the replacement pattern.

| Pattern | Signal | Replacement |
|---------|--------|-------------|
| Purple-to-blue gradient as primary background (`from-purple-500 to-blue-500`, `LinearGradient([Color(0xFF...purple), Color(0xFF...blue)])`) | Generic AI hero aesthetic | Use brand color tokens from `colorScheme` (Flutter) or daisyUI semantic `bg-primary` (Angular); gradients only for deliberate decorative surfaces |
| Glass morphism cards with no semantic purpose (`backdrop-blur`, `bg-white/10`, `BackdropFilter` on every card) | Trendy filler masking weak content hierarchy | Use solid surface tokens (`colorScheme.surface`, `bg-base-100`); reserve blur effects for modal overlays where focus isolation is the intent |
| Excessive border-radius on everything including data tables and code blocks (`rounded-2xl` on `<table>`, `BorderRadius.circular(24)` on list tiles) | Indiscriminate softening | Apply radius intentionally: cards and buttons use `AppRadius.*` tokens; data-dense surfaces (tables, code) use `rounded-none` or `rounded-sm` |
| Scroll-triggered animations on every section (`IntersectionObserver` on 10+ elements, `AnimationController` firing on every scroll event) | Cargo-culted engagement pattern | Use entrance animations only for primary hero or key CTAs; all other content renders immediately; see `flutter-design-polish.md` and `animations.md` for approved patterns |
| Generic centered hero: `[Big Title] [Subtitle] [Primary Button] [Secondary Button]` over gradient background | Uncustomized template output | Differentiate with brand-specific layout, real imagery or illustration, and a single focused CTA |
| Inter / Roboto / Space Grotesk as the only fonts with no display personality (same weight, same size hierarchy everywhere) | Default font stack, zero typographic intention | Add a display typeface for headings that matches brand tone; establish a deliberate type scale with size AND weight contrast between levels |
| Symmetrical 3-column feature card grid: icon + title + body, all equal height, all centered (`grid-cols-3`, `Column(children: [Icon, Text, Text])` × N) | The AI feature section template | Vary layout rhythm — mix wide + narrow cards, use real screenshots or illustrations instead of icons, break the grid for emphasis |
| Shadow stacking — `shadow-lg` on a container that already has `shadow-md`, nested inside `shadow-sm` (`BoxShadow` arrays with 3+ layers on the same widget) | Depth miscalculation, not intentional elevation | Use a single elevation token per surface level; Flutter: one `BoxShadow` per widget matching `colorScheme.shadow`; Angular: one daisyUI shadow utility per element |

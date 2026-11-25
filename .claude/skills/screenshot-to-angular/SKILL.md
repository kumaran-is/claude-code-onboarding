---
name: screenshot-to-angular
description: "Pixel-perfect Angular component replication from a screenshot. Use when the user provides a UI screenshot and asks to replicate, clone, implement, or build it in Angular. Enforces Angular standards (daisyUI semantic classes, Tailwind scale, standalone components, signals). Triggers: screenshot to angular, replicate this screen angular, clone this UI angular, build this screen in angular, implement this design angular."
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
metadata:
  triggers: screenshot to angular, replicate screen angular, clone UI angular, pixel perfect angular, implement design angular, build this screen angular, recreate UI angular
  related-skills: angular-spa, angular-ui-patterns, ui-standards-tokens, tailwind-patterns
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-04-04"
---

## Iron Law

**NEVER output hardcoded hex colors, raw px spacing, or `NgModule`. ALL colors → the workspace UI mode's semantic tokens (daisyUI: `bg-primary`, `text-base-content`; Spartan: `bg-background`, `text-foreground`), ALL spacing → Tailwind scale (`p-4`, `mt-2`), ALL components → standalone with `@if`/`@for` control flow, ALL state → `signal()`.**

# Screenshot-to-Angular Skill

## Purpose

Replicate a UI screenshot as a production-ready Angular 22.x standalone component with pixel-perfect visual accuracy, compliant with Angular standards (Tailwind 4.x + the workspace UI mode).

First run `bash .claude/scripts/angular-ui-mode.sh detect <workspace>` and build with that mode's components (`angular-spa/reference/ui-mode-selection.md` §4): the
daisyUI mapping below applies to `daisyui` and to the daisyUI-owned parts of `hybrid`; dialogs, menus, selects and
popovers in `spartan`/`hybrid` use Spartan Helm.

> **Scope reminder:** Confirm whether this screenshot is for a marketing/web app or a mobile app feature. If it shows app-level CRUD features (dashboards, forms, ticket management) intended for mobile, consider implementing in Flutter instead of Angular.

---

### Step 0 — Project DESIGN.md (before analysing the screenshot)

The screenshot owns WHAT the screen shows; the project's `DESIGN.md` owns HOW. Find it and read only the token, component and state sections this screen needs (`.claude/skills/design-system/reference/design-md-governance.md`). Map every colour, size and spacing to the project's tokens, never to the mock's raw values; reuse its shared components (and their tiers) before creating new ones. No DESIGN.md: say so, use the existing theme, invent no brand values. A value with no matching token is a gap: use the closest token and list it under "Design gaps" in the output for the human. New shared components follow `atomic-decision-tree.md` (line-1 `// Tier:`, presentational). Finish with `python3 .claude/scripts/check-design-system.py --root .`.

## Phase 1 — Screenshot Analysis (mandatory before writing code)

### Layout Analysis
```
□ Layout type: flex-col / flex-row / grid / relative+absolute
□ Scrollable? Yes / No
□ Has navbar? → note links, logo position, sticky/fixed
□ Has hero section? → note CTA, background treatment
□ Has footer? → note columns, links
□ Has modal / drawer / bottom sheet? → note trigger
□ Responsive breakpoints visible? → note mobile vs desktop differences
```

### Color Extraction (map to daisyUI tokens — do NOT use raw hex)
```
□ Page background     → bg-base-100 / bg-base-200 / bg-base-300
□ Card background     → bg-base-100 / bg-base-200
□ Primary accent      → bg-primary / text-primary / border-primary
□ Secondary accent    → bg-secondary / text-secondary
□ Heading text        → text-base-content
□ Body text           → text-base-content / text-base-content/70
□ Muted / caption     → text-base-content/50
□ Error / warning     → text-error / text-warning
□ Success             → text-success
□ Divider / border    → border-base-300 / divide-base-300
```

**Token mapping rule:** If the screenshot uses a color that doesn't map to a daisyUI token, use the closest semantic token and note the approximation in an HTML comment `<!-- Design note: -->`.

### Typography Analysis (map to Tailwind text scale)
```
□ Heading large    → text-4xl / text-5xl / font-bold
□ Heading medium   → text-2xl / text-3xl / font-semibold
□ Heading small    → text-xl / font-semibold
□ Body large       → text-base / text-lg
□ Body default     → text-sm / text-base
□ Caption / label  → text-xs / text-sm / font-medium
□ Font weight      → font-normal / font-medium / font-semibold / font-bold
□ Letter spacing   → tracking-tight / tracking-normal / tracking-wide
```

### Spacing Analysis (map to Tailwind scale)
```
□ Page padding     → px-4 / px-6 / px-8 / container mx-auto
□ Section gap      → py-12 / py-16 / py-24
□ Card padding     → p-4 / p-6 / p-8
□ Item gap         → gap-2 / gap-4 / gap-6
□ Button padding   → px-4 py-2 / px-6 py-3
```

### Component Inventory
```
□ Buttons: type (btn-primary/secondary/outline/ghost), size (btn-sm/md/lg)
□ Cards: border presence, shadow (shadow-sm/md/lg), rounded (rounded-lg/xl/2xl)
□ Input fields: border style, placeholder, label position
□ Navbar: links, CTA button, mobile menu presence
□ List items: spacing, icons, dividers
□ Images: aspect ratio, object-fit, placeholder needed
□ Badges/chips: variant (badge-primary/secondary/outline)
□ Alerts: variant (alert-info/success/warning/error)
```

---

## Phase 2 — Implementation Rules

### File Structure
```
src/app/
  pages/<page-name>/
    <page-name>.component.ts    ← standalone component
    <page-name>.component.html  ← template
  features/<feature-name>/
    <component-name>/
      <component-name>.component.ts
      <component-name>.component.html
  shared/components/
    <reusable-component>/       ← if used 2+ times
```

### Angular 22 Standards (zero tolerance)

| Pattern | Required Instead |
|---|---|
| `NgModule` | Standalone components only |
| `*ngIf`, `*ngFor` | `@if`, `@for` control flow |
| `BehaviorSubject` | `signal()` |
| `.subscribe()` without cleanup | `toSignal()` |
| `@Input()` decorator | `input()` signal-based |
| `@Output()` decorator | `output()` signal-based |
| Raw hex in class | daisyUI semantic class |
| Raw `px` in style | Tailwind scale class |
| `document.getElementById` | `viewChild()` |

### Component Template
```typescript
import { Component, signal, input, output } from '@angular/core';

@Component({
  selector: 'app-[name]',
  imports: [], // only the directives/pipes the template uses — never CommonModule
  templateUrl: './[name].component.html',
})
export class [Name]Component {
  // Use signal() for local state
  isOpen = signal(false);

  // Use input() for props
  title = input<string>('');

  // Use output() for events
  clicked = output<void>();
}
```

### daisyUI Component Mapping (`daisyui` mode; `hybrid` for daisyUI-owned components)

| Screenshot Element | daisyUI / Tailwind Implementation |
|---|---|
| Primary button | `<button class="btn btn-primary">` |
| Outlined button | `<button class="btn btn-outline btn-primary">` |
| Ghost button | `<button class="btn btn-ghost">` |
| Card | `<div class="card bg-base-100 shadow-md">` + `<div class="card-body">` |
| Input | `<input class="input w-full">` |
| Navbar | `<div class="navbar bg-base-100">` |
| Hero | `<div class="hero min-h-screen bg-base-200">` |
| Badge | `<span class="badge badge-primary">` |
| Alert | `<div class="alert alert-info">` |
| Modal | `<dialog class="modal">` |
| Dropdown | `<div class="dropdown">` |
| Avatar | `<div class="avatar"><div class="w-12 rounded-full">` |
| Divider | `<div class="divider">` OR `divide-y divide-base-300` |
| Loading | `<span class="loading loading-spinner">` |

### Interaction Rules
```html
<!-- Hover states — the daisyUI 5 color class styles hover itself; there are no *-focus color classes in v5 -->
<button class="btn btn-primary">

<!-- Focus states — always include for accessibility -->
<!-- keep a visible indicator: never focus:outline-none without a replacement (WCAG 2.4.7) -->
<input class="input focus:input-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">

<!-- Active/pressed state -->
<button class="btn btn-primary active:scale-95 transition-transform">

<!-- Scroll overflow -->
<div class="overflow-y-auto max-h-96 scrollbar-thin">
```

---

## Phase 3 — Output Format

```
## Screenshot Analysis
- Layout: [type]
- Components found: [list]
- Color mapping: [screenshot color → daisyUI token]
- Typography mapping: [size → Tailwind text class]
- Scope check: Marketing site? [Yes/No — if No, flag for Flutter]
- Approximations: [anything that couldn't map cleanly, with reason]

## Component Tree
[Indented HTML structure showing nesting]

## Implementation
[Complete .ts + .html files — production-ready, no TODOs]

## Design Notes
[Approximations made, placeholder images, responsive breakpoints assumed]
```

---

## Quality Gates (check before reporting done)

- [ ] `mcp__angular-cli__get_best_practices` queried with `workspacePath` (the folder holding `angular.json`) before coding; without it the tool returns generic v22 guidance
- [ ] Zero raw hex values in template or component
- [ ] Zero hardcoded `px`/`rem` spacing values — all Tailwind scale
- [ ] Standalone component — no `NgModule`
- [ ] `@if`/`@for` used — no `*ngIf`/`*ngFor`
- [ ] `signal()` for any reactive state — no `BehaviorSubject`
- [ ] Every interactive element has hover + focus state
- [ ] Target size ≥ 24×24 CSS px (WCAG 2.2 AA minimum); house standard 44px
- [ ] No daisyUI 4 classes (`input-bordered`, `*-focus` color variants); see `angular-spa/reference/daisyui-v5-components.md`
- [ ] `/lint-design-system` run with zero violations
- [ ] Reviewers dispatched: `ui-standards-expert` (token compliance) and `accessibility-auditor` (WCAG 2.2 AA)
- [ ] Images use `placeholder` or `aspect-ratio` to prevent layout shift
- [ ] Component placed in correct directory (`pages/` vs `features/` vs `shared/`)
- [ ] Scope confirmed: this is marketing-site content, not app functionality

---

## Related Skills
- Load `angular-spa` for full Angular 22 patterns and routing setup
- Load `tailwind-patterns` for Tailwind 4.x utility reference
- Load `ui-standards-tokens` for full daisyUI token reference
- Load `frontend-design` if creative direction is needed (not pure replication)

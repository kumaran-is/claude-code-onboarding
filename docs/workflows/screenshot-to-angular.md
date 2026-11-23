# Screenshot-to-Angular Workflow

> **When to use**: User provides a UI screenshot and asks to replicate, clone, or implement it in Angular
> **Prerequisites**: Angular project scaffolded; daisyUI + TailwindCSS 4.x configured

## Overview

Replicate a UI screenshot as a production-ready Angular 21.x standalone component with pixel-perfect visual accuracy, compliant with daisyUI semantic tokens and Tailwind scale. Uses `screenshot-to-angular` skill.

---

## Iron Law (from skill)

**NEVER output hardcoded hex colors, raw px spacing, or `NgModule`. ALL colors → daisyUI semantic classes (`bg-primary`, `text-base-content`), ALL spacing → Tailwind scale (`p-4`, `mt-2`), ALL components → standalone with `@if`/`@for` control flow, ALL state → `signal()`.**

---

## Phases

### Phase 1 — Load Skill and Analyze Screenshot

**Load skill first:**
```
/screenshot-to-angular
```

**Skills to also load if needed:**
- `angular-spa` — workspace conventions
- `angular-ui-patterns` — loading/error/empty state doctrine
- `tailwind-patterns` — Tailwind v4 and container queries
- `ui-standards-tokens` — design token audit

**MCP queries:**
```
mcp__angular-cli__get_best_practices    → pass workspacePath (angular.json folder); without it the tool returns v22 guidance
mcp__context7__resolve-library-id       → angular, @angular/core
```

**Screenshot analysis checklist (mandatory before coding):**
```
□ Layout type: flex-col / flex-row / grid / relative+absolute
□ Scrollable? Yes / No
□ Navbar present? → links, logo position, sticky/fixed
□ Hero section? → CTA, background treatment
□ Cards/lists? → count, spacing, border radius
□ Interactive elements? → buttons, inputs, dropdowns
□ Responsive breakpoints visible?
□ Color palette → map to daisyUI semantic classes
□ Typography → map to Tailwind text-* utilities
□ Spacing → map to Tailwind scale (p-*, m-*, gap-*)
```

---

### Phase 2 — Implement Component

**File placement:**
- Page-level screen: `src/app/features/<feature>/<feature>.component.ts`
- Reusable widget: `src/app/shared/components/<name>/<name>.component.ts`

**Component structure:**
```typescript
@Component({
  selector: 'app-<name>',
  standalone: true,
  imports: [CommonModule, RouterLink, /* daisyUI-compatible directives */],
  templateUrl: './<name>.component.html',
})
export class <Name>Component {
  // signals for state
}
```

**Token mapping rules:**
| Screenshot element | Angular / daisyUI class |
|---|---|
| Primary background | `bg-base-100` |
| Card background | `bg-base-200` |
| Primary text | `text-base-content` |
| Secondary text | `text-base-content/70` |
| Primary button | `btn btn-primary` |
| Outlined button | `btn btn-outline` |
| Input field | `input input-bordered` |
| Badge | `badge badge-primary` |
| Divider | `divider` |

---

### Phase 3 — Review Gate

Run after implementation:

```
□ Zero hardcoded hex values (grep -r "#[0-9a-fA-F]" src/)
□ Zero raw px spacing values
□ All components standalone (no NgModule)
□ All state uses signal()
□ @if/@for control flow (no *ngIf/*ngFor)
□ Target size ≥ 24×24 CSS px (WCAG 2.2 AA); house standard ≥ 44px
□ /lint-design-system passes with zero violations
```

**Dispatch reviewer:**
- `ui-standards-expert` agent — token compliance
- `accessibility-auditor` agent — WCAG 2.2 AA

---

## Common Pitfalls

| Mistake | Fix |
|---|---|
| Using `[ngClass]` with raw color strings | Use daisyUI semantic class directly |
| Hardcoding `style="color: #3b82f6"` | Map to `text-primary` or nearest daisyUI token |
| Using `px-[18px]` arbitrary values | Round to nearest Tailwind scale (`px-4` = 16px) |
| Using `NgModule` wrapper | Standalone only — `@Component({ standalone: true })` |
| Pixel-perfect via inline styles | Visual accuracy through tokens — never bypass the design system |

# Design System Compliance

> **When to use**: After building any UI component in Flutter or Angular — before PR review
> **Time estimate**: 30–60 min for a single screen; 2–3 hours for a full feature audit
> **Prerequisites**: Flutter or Angular UI components written; design token definitions in skill reference

## Overview

Design system compliance audit using the `design-system` skill, `/lint-design-system` command, `ui-standards-expert` agent, and `accessibility-auditor` agent. Enforces token usage, semantic colors, spacing scale and typography; accessibility (WCAG 2.2 AA) is reviewed by `accessibility-auditor`, the only agent that gives accessibility verdicts.

---

## Iron Law (from `skills/design-system/SKILL.md`)

> **NO HARDCODED VALUES — EVERY COLOR, SPACING, AND TYPOGRAPHY VALUE MUST USE A DESIGN TOKEN**
> Hardcoded values create visual inconsistency and make theme changes require manual search-and-replace.

---

## Compliance Dimensions

| Dimension | Flutter Token | Angular Token |
|-----------|--------------|--------------|
| Colors | `Theme.of(context).colorScheme.*` | daisyUI semantic: `bg-primary`, `text-base-content` |
| Spacing | `AppSpacing.md` (or `context.spacing.*`) | Tailwind scale: `p-4`, `m-2`, `gap-6` |
| Typography | `Theme.of(context).textTheme.*` | daisyUI typography: `text-sm`, `font-bold` |
| Elevation | `Theme.of(context).shadowColor` | daisyUI: `shadow-sm`, `shadow-md` |
| Radius | `Theme.of(context).shape.*` | daisyUI: `rounded-lg`, `rounded-btn` |

---

## Phases

### Phase 1 — Load Skill and Run `/lint-design-system`

**Skill**: Load `design-system` (`.claude/skills/design-system/SKILL.md`)

**Command**: `/lint-design-system`

The skill routes to the correct stack-specific checks:
- Flutter → `ui-standards-tokens` skill + Flutter-specific rules
- Angular → daisyUI + Tailwind 4.x rules

**What the linter checks**:

#### Flutter Violations
```dart
// ❌ VIOLATION — hardcoded color
Container(color: Color(0xFF1A73E8))

// ✅ COMPLIANT — design token
Container(color: Theme.of(context).colorScheme.primary)

// ❌ VIOLATION — raw spacing
Padding(padding: EdgeInsets.all(16))

// ✅ COMPLIANT — spacing token
Padding(padding: EdgeInsets.all(AppSpacing.md))

// ❌ VIOLATION — inline TextStyle
Text('Title', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold))

// ✅ COMPLIANT — theme text style
Text('Title', style: Theme.of(context).textTheme.titleLarge)
```

#### Angular Violations
```html
<!-- ❌ VIOLATION — hardcoded color -->
<div style="background-color: #1A73E8">

<!-- ✅ COMPLIANT — daisyUI token -->
<div class="bg-primary">

<!-- ❌ VIOLATION — arbitrary Tailwind value -->
<div class="p-[18px]">

<!-- ✅ COMPLIANT — Tailwind scale -->
<div class="p-4">

<!-- ❌ VIOLATION — hardcoded dark mode -->
<div class="text-white dark:text-black">

<!-- ✅ COMPLIANT — daisyUI semantic -->
<div class="text-base-content">
```

---

### Phase 2 — `ui-standards-expert` Agent

**Agent**: `ui-standards-expert`

**Dispatches for**:
- Design token usage audit (colors, spacing, typography)
- Material 3 theming (Flutter) or daisyUI theming (Angular)
- Responsive layout patterns
- Interaction contract and async-state coverage (`design-system/reference/interaction-contracts.md` §6b)
- No accessibility verdicts: accessibility signals are handed to `accessibility-auditor`

**Flutter interaction contracts** (from `ui-standards-tokens` skill):
- Touch targets ≥ 48dp (Android platform guideline; WCAG 2.5.8 AA floor is 24×24)
- `InkWell` or `GestureDetector` with proper `hitTestBehavior`
- No nested `GestureDetector` without `HitTestBehavior.opaque`

**Angular interaction contracts** (from `angular-spa` skill):
- Touch targets ≥ 24×24 CSS px (WCAG 2.5.8 AA); house standard ≥ 44px
- `:hover` and `:focus-visible` states on all interactive elements
- No `outline: none` without a custom focus indicator

---

### Phase 3 — `accessibility-auditor` Agent

**Agent**: `accessibility-auditor` (read-only WCAG 2.2 AA review, web and Flutter; checklist: `.claude/skills/accessibility-audit/reference/wcag22-checklist.md`)

**Flutter checks**:
```dart
// ❌ VIOLATION — icon without semantic label
Icon(Icons.delete)

// ✅ COMPLIANT — semantic label for screen reader
Semantics(
  label: 'Delete order',
  button: true,
  child: Icon(Icons.delete),
)

// ❌ VIOLATION — custom widget, no semantics
Container(child: GestureDetector(...))

// ✅ COMPLIANT
Semantics(
  label: 'Order card for item-1',
  child: Container(child: GestureDetector(...)),
)
```

**Angular checks**:
```html
<!-- ❌ VIOLATION — icon-only button without label -->
<button><mat-icon>delete</mat-icon></button>

<!-- ✅ COMPLIANT — aria-label -->
<button aria-label="Delete order"><mat-icon>delete</mat-icon></button>

<!-- ❌ VIOLATION — no role on custom interactive element -->
<div (click)="submit()">Submit</div>

<!-- ✅ COMPLIANT — semantic button -->
<button type="submit">Submit</button>
```

**Color contrast**: ≥ 4.5:1 for normal text, ≥ 3:1 for large text (18px+ regular or 14px+ bold)

**Keyboard navigation**: All interactive elements reachable via Tab, activated via Enter/Space

---

### Phase 4 — Exception Markers

When a design system deviation is intentionally needed:

**Flutter**:
```dart
// ignore-design: product requirement — branded gradient background
Container(
  decoration: BoxDecoration(
    gradient: LinearGradient(colors: [Color(0xFF1A73E8), Color(0xFF4285F4)]),
  ),
)
```

**Angular**:
```html
<!-- ignore-design: product requirement — brand animation uses raw value -->
<div class="animate-[pulse_1.5s_ease-in-out_infinite]">
```

**Rule**: Exception markers must include:
1. `ignore-design:` prefix
2. Reason (product requirement, third-party constraint, etc.)
3. Reviewed and approved during PR

---

### Phase 5 — Gate and Report

**Required before PR creation**:
```
/lint-design-system output:
Violations: [N]
- ❌ [file:line] — [violation description]
- ❌ [file:line] — [violation description]

After fixing all violations:
Violations: 0 ✅
Exception markers: [N] (reviewed in PR)
```

**All three must pass**:
- [ ] `/lint-design-system` returns zero violations (or all are exception-marked)
- [ ] `ui-standards-expert` agent `VERDICT: NO VIOLATIONS`
- [ ] `accessibility-auditor` agent `VERDICT` is not BLOCK, and its open manual checks are listed (automated results never establish conformance)

---

## Quick Reference

| Check | Tool | Gate |
|-------|------|------|
| Token usage | `/lint-design-system` | Zero violations (or exception-marked) |
| UI standards | `ui-standards-expert` agent | NO VIOLATIONS |
| WCAG 2.2 AA | `accessibility-auditor` agent | No CRITICAL/HIGH; manual checks listed |
| Target size | Part of accessibility-auditor | ≥ 24×24 CSS px (AA); house ≥ 48dp Flutter / ≥ 44px web |
| Color contrast | Part of accessibility-auditor | ≥ 4.5:1 normal, ≥ 3:1 large, light and dark |

---

## Common Pitfalls

- **Hardcoded colors in style files** — `.scss` and `style.ts` are also checked; violations there too
- **`Colors.white` instead of `colorScheme.surface`** — Flutter color constants are not design tokens
- **`bg-blue-500` instead of `bg-primary`** — Tailwind utility colors are not daisyUI semantic tokens
- **No focus state** — removing `outline` without replacement fails WCAG 2.4.7
- **Icon-only buttons** — always need `aria-label` (Angular) or `Semantics` widget (Flutter)

## Related Workflows

- [`feature-flutter-mobile.md`](feature-flutter-mobile.md) — Flutter design system context
- [`feature-angular-spa.md`](feature-angular-spa.md) — Angular design system context
- [`code-review.md`](code-review.md) — design system compliance is part of code review gate

# Frontend Design Workflow

> **When to use**: Starting any new UI — Angular component, Flutter screen, landing page, or standalone HTML/CSS
> **Prerequisites**: Know the product audience and purpose before starting

## Overview

Frontend design using the `frontend-design` skill. Enforces Design Thinking Phase → DFII scoring → implementation → three-layer review. Ensures every UI has intentional aesthetics, not generic AI-generated defaults.

---

## Iron Law (from `skills/frontend-design/SKILL.md`)

> **COMPLETE THE DESIGN THINKING PHASE BEFORE WRITING CODE. DFII ≥ 8 REQUIRED TO PROCEED.**

---

## Phases

### Phase 1 — Load Skill and Design Thinking Phase

**Skill**: Load `frontend-design` (`.claude/skills/frontend-design/SKILL.md`)

Complete the mandatory Design Thinking Phase:
```
Purpose:               [persuasive / functional / exploratory / expressive]
Tone (ONE direction):  [Brutalist / Editorial / Luxury / Retro-futuristic / Industrial /
                        Organic / Playful / Maximalist / Minimalist]
Differentiation Anchor: "If screenshotted without the logo, someone would recognize this
                         because: ___"
```

---

### Phase 2 — Score DFII

Calculate before writing any code:

```
Aesthetic Impact:           ___ / 5
Context Fit:                ___ / 5
Implementation Feasibility: ___ / 5
Performance Safety:         ___ / 5
Consistency Risk:           ___ / 5  (subtract)

DFII = (Impact + Fit + Feasibility + Performance) − Risk = ___
```

**Gate: DFII < 8 → rethink direction. Do not proceed.**

---

### Phase 3 — Load Design Principles

Read `reference/frontend-design-principles.md` for:
- Typography rules (no Inter/Roboto/Arial — choose distinctive fonts)
- Color system (CSS variables, one dominant + one accent)
- Spatial composition (break grid intentionally)
- Motion (sparse, purposeful, high-impact)
- Anti-patterns checklist

---

### Phase 4 — Implement

**For Angular (daisyUI + Tailwind CSS 4.3.5):**
```typescript
// Use daisyUI semantic tokens — never hardcoded hex
// bg-primary, text-base-content, border-base-300
// Load angular-spa skill for implementation patterns
```

**For Flutter (Theme + AppSpacing):**
```dart
// Use Theme.of(context).colorScheme.* — never Color(0xFF...)
// Use AppSpacing.md — never EdgeInsets.all(16)
// Load flutter-mobile skill for implementation patterns
```

**For HTML/CSS:**
```css
:root {
  --color-primary: ...;
  --color-accent: ...;
  --color-neutral: ...;
  --spacing-base: 8px;
}
```

---

### Phase 5 — Deliver with Required Output Structure

Every frontend design output MUST include:

1. **Design Direction Summary** — aesthetic name, DFII score, key inspiration
2. **Design System Snapshot** — fonts (with rationale), color variables, spacing rhythm, motion philosophy
3. **Implementation** — full working code
4. **Differentiation Callout** — "This avoids generic UI by doing **X** instead of **Y**."

---

### Phase 6 — Three-Layer Review

| Layer | Tool | What It Catches |
|---|---|---|
| **Layer 1 — Tokens** | `/lint-design-system` | Hardcoded colors, raw spacing, inline typography |
| **Layer 2 — WCAG** | `accessibility-auditor` agent | Contrast, ARIA, keyboard nav, semantic HTML |
| **Layer 3 — Patterns** | `web-design-guidelines` skill | Loading/error/empty states, focus management, interaction patterns |

**Gate**: All three layers pass before declaring done.

---

### Phase 7 — Operator Checklist

- [ ] Design Thinking Phase completed
- [ ] DFII score ≥ 8
- [ ] One memorable design anchor visible
- [ ] No generic fonts (Inter, Roboto, Arial)
- [ ] No generic colors (purple-on-white gradient)
- [ ] No default layouts (symmetrical card grid)
- [ ] Required Output Structure: all 4 sections delivered
- [ ] `/lint-design-system` — zero violations
- [ ] `accessibility-auditor` — no CRITICAL/HIGH findings
- [ ] `web-design-guidelines` — findings addressed

---

## Quick Reference

| Phase | Action | Gate |
|---|---|---|
| 1 — Design Thinking | Purpose + Tone + Differentiation Anchor | All three defined |
| 2 — DFII | Score formula | Score ≥ 8 |
| 3 — Principles | Load reference file | Typography, color, motion rules known |
| 4 — Implement | Code with design tokens | Builds without errors |
| 5 — Output | All 4 sections delivered | Differentiation Callout present |
| 6 — Review | Three-layer audit | All layers pass |

---

## Common Pitfalls

- **Skipping DFII** — building a weak aesthetic direction that looks like a template
- **Blending too many tones** — picking "minimalist + maximalist + brutalist" produces no coherent direction
- **Token violations** — using `#3b82f6` instead of `bg-primary` in Angular; `Color(0xFF3b82f6)` instead of `colorScheme.primary` in Flutter
- **Missing Differentiation Callout** — if you can't complete "This avoids generic UI by doing X instead of Y", the design isn't distinctive

## Related Workflows

- [`feature-angular-spa.md`](feature-angular-spa.md) — Angular feature development (load `frontend-design` in Phase 1)
- [`design-system-compliance.md`](design-system-compliance.md) — enforcing design tokens
- [`browser-e2e-testing.md`](browser-e2e-testing.md) — E2E testing after design review

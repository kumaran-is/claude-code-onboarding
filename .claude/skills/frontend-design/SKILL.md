---
name: frontend-design
description: "Distinctive, production-grade UI design with an explicit aesthetic direction, DFII go/no-go score and design-thinking phase before code. Use when creating a new page, landing page, dashboard or visual refresh. Not for token compliance (design-system) or reviews (ui-standards-expert)."
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch
metadata:
  triggers: frontend design, UI design, landing page, visual design, UI component, design system, creative UI, DFII, design direction, aesthetic, memorable UI, distinctive design, non-generic UI
  related-skills: angular-spa, ui-standards-tokens, browser-testing, web-design-guidelines, design-system
  domain: frontend
  role: specialist
  scope: design
  output-format: code
last-reviewed: "2026-03-15"
---

## Iron Law

**NO UI OUTPUT WITHOUT COMPLETING THE DESIGN THINKING PHASE FIRST — define Purpose, Tone (one direction), and Differentiation Anchor before writing a single line of code. DFII score must be ≥ 8 to proceed.**

# Frontend Design Skill

## Purpose

Provides creative frontend design methodology, visual principles, and quality checklists for building distinctive, production-grade interfaces that avoid generic AI aesthetics.

## Process

1. **Design Thinking Phase** (mandatory — do not skip)
   - Define Purpose: what action does this interface enable? Is it persuasive, functional, exploratory, or expressive?
   - Define Tone: choose ONE dominant direction (Brutalist / Editorial / Luxury / Retro-futuristic / Industrial / Organic / Playful / Maximalist / Minimalist). Do not blend more than two.
   - Define Differentiation Anchor: answer "If this were screenshotted with the logo removed, how would someone recognize it?" This must be visible in the final UI.
2. **Score DFII** — calculate Design Feasibility & Impact Index (see below). Score < 8 → rethink direction before proceeding.
3. **Load principles** -- Read `reference/frontend-design-principles.md` for typography, color, motion, and layout guidance
4. **Implement** -- Build working code (Angular, Flutter, or HTML/CSS/JS) aligned to the chosen aesthetic. Follow workspace design tokens (daisyUI for Angular, AppSpacing/colorScheme for Flutter).
5. **Deliver with required output structure** -- include Design Direction Summary, Design System Snapshot, Implementation, and Differentiation Callout

For the complete design principles, anti-patterns, and quality checklist:

Read [reference/frontend-design-principles.md](reference/frontend-design-principles.md)

## Error Handling

If the target framework is not specified, ask the user before proceeding.
If external font/asset resources are unavailable, document the fallback choice and continue.

## Design Feasibility & Impact Index (DFII)

Score the design direction before writing code. **Minimum score of 8 required to proceed.**

### Dimensions (each scored 1–5)

| Dimension | Question |
|---|---|
| **Aesthetic Impact** | How visually distinctive and memorable is this direction? |
| **Context Fit** | Does this aesthetic suit the product, audience, and purpose? |
| **Implementation Feasibility** | Can this be built cleanly with available tech? |
| **Performance Safety** | Will it remain fast and accessible? |
| **Consistency Risk** | Can this be maintained across screens/components? (subtract this) |

### Formula

```
DFII = (Impact + Fit + Feasibility + Performance) − Consistency Risk
Range: −5 → +15
```

### Interpretation

| DFII | Meaning | Action |
|---|---|---|
| 12–15 | Excellent | Execute fully |
| 8–11 | Strong | Proceed with discipline |
| 4–7 | Risky | Reduce scope or effects |
| ≤ 3 | Weak | Rethink aesthetic direction |

---

## Required Output Structure

Every frontend design output MUST include all four sections:

### 1. Design Direction Summary
- Aesthetic name (e.g. "Editorial Brutalism", "Luxury Minimal")
- DFII score
- Key inspiration (conceptual — not visual plagiarism)

### 2. Design System Snapshot
- Fonts (with rationale — why this font for this product?)
- Color variables (name them: `--color-primary`, `--color-accent`, `--color-neutral`)
- Spacing rhythm (base unit and scale)
- Motion philosophy (sparse/purposeful? or none?)

### 3. Implementation
- Full working code
- Comments only where intent is not obvious
- For Angular: use daisyUI semantic tokens (`bg-primary`, `text-base-content`) — no hardcoded hex
- For Flutter: use `Theme.of(context).colorScheme` and `AppSpacing.*` tokens — no `Color(0xFF...)`

### 4. Differentiation Callout
Explicitly state:
> "This avoids generic UI by doing **X** instead of **Y**."

If you cannot complete this sentence, the design is not distinctive enough.

---

## Operator Checklist (Pre-Delivery Gate)

- [ ] Design Thinking Phase completed (Purpose + Tone + Differentiation Anchor defined)
- [ ] DFII score ≥ 8
- [ ] One memorable design anchor visible in final UI
- [ ] No generic fonts (no Inter, Roboto, Arial, system-ui)
- [ ] No generic colors (no purple-on-white gradients, no flat gray)
- [ ] No default layouts (no symmetrical card grids, no template-like structure)
- [ ] Code matches design ambition (maximalist = complex code; minimalist = precise spacing)
- [ ] Accessible and performant (contrast ≥ 4.5:1, focus states, keyboard nav)
- [ ] Required Output Structure: all 4 sections present
- [ ] Three-layer review passed: tokens (`/lint-design-system`: hardcoded colors, raw spacing, inline typography), WCAG 2.2 AA (`accessibility-auditor`: contrast, ARIA, keyboard, semantics), patterns (`web-design-guidelines` skill, web targets: loading/error/empty states, focus management, interaction)
- [ ] No design should look like a previous one — vary light/dark, font choices, layout personality

---

## Creative Ambition Mandate

**Claude is capable of extraordinary creative work. Don't hold back — show what can truly be created when thinking outside the box and committing fully to a distinctive vision.**

Interpret requirements creatively. Make unexpected choices that feel genuinely designed for the context. No two designs should share the same aesthetic DNA.

**NEVER converge on common choices across generations.** The fact that Space Grotesk, purple gradients, or symmetrical hero layouts "worked before" is the exact reason not to use them again. Variety is mandatory, not optional.

---

## Questions to Ask Before Starting (If Needed)

1. Who is this for, emotionally?
2. Should this feel trustworthy, exciting, calm, or provocative?
3. Is memorability or clarity more important?
4. Will this scale to other pages/components?
5. What should users *feel* in the first 3 seconds?

---

## Workspace Integration

| Stack | Design Token Rule | Reference |
|---|---|---|
| **Angular** | daisyUI semantic tokens only — `bg-primary`, `text-base-content`, `border-base-300` | `angular-spa/reference/daisyui-v5-components.md` |
| **Flutter** | `Theme.of(context).colorScheme.*` + `AppSpacing.*` — never `Color(0xFF...)` or `EdgeInsets.all(16)` | `ui-standards-tokens/reference/ui-design-tokens.md` |
| **HTML/CSS** | CSS variables exclusively — `var(--color-primary)` | Define in `:root` block |
| **React Native** | Out of scope for this skill → use `mobile-developer` skill | `.claude/skills/mobile-developer/SKILL.md` |

**Related skills:**
- `web-design-guidelines` — run after implementing to audit against Vercel Web Interface Guidelines
- `design-system` — token compliance enforcement for Angular and Flutter
- `angular-spa` — Angular implementation patterns with daisyUI
- `ui-standards-tokens` — Flutter design token definitions

---
name: ui-ux-pro-max
description: "Design intelligence database for UI/UX work — 50+ styles, 97 color palettes, 57 font pairings, 99 UX guidelines. Flutter has a dedicated stack file. Angular uses html-tailwind stack. BM25 search engine via Python scripts. Use when selecting design direction, palettes, typography, chart types, or getting stack-specific UX guidelines before writing UI code."
risk: low
source: community (adapted for workspace)
date_added: "2026-02-27"
updated: "2026-03-15"
allowed-tools: Bash, Read
metadata:
  triggers: color palette, design style, font pairing, UI style, design system, typography, dashboard design, landing page design, UX guidelines, chart type, design inspiration, glassmorphism, brutalism, neumorphism, aurora UI
  related-skills: frontend-design, angular-spa, flutter-mobile, tailwind-patterns, design-system
  domain: frontend
  role: specialist
  scope: design
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law

**RUN `--design-system` FIRST before writing any UI code — it searches 5 domains in parallel and returns a complete design system. For Angular: use `html-tailwind` stack. For Flutter: use `flutter` stack. Scripts require Python 3.**

# UI/UX Pro Max — Design Intelligence Database

Searchable design knowledge database with BM25 search engine. Contains 50+ styles, 97 color palettes, 57 font pairings, 99 UX guidelines, and 25+ chart types. Stacks: Angular (html-tailwind), Flutter, SwiftUI.

## When to Use

- Choosing design style/aesthetic for a new Angular or Flutter UI
- Selecting a color palette for a specific product type (SaaS, health, fintech, etc.)
- Finding font pairings for a design direction
- Getting UX best practices (animation, z-index, accessibility, loading states)
- Recommending chart types for data visualization
- Getting stack-specific implementation guidelines

## When NOT to Use

- For implementing Angular or Flutter code — use `angular-spa` or `flutter-mobile` for that
- For design token enforcement — use `design-system` for that
- For WCAG compliance audit — use `accessibility-audit` for that

---

## Workspace Stack Mapping

| Workspace Stack | Script Stack Flag | Notes |
|---|---|---|
| **Angular 21.x + Tailwind v4** | `--stack html-tailwind` | No dedicated Angular CSV — html-tailwind covers Tailwind utilities, responsive, a11y |
| **React 19 (web)** | `--stack react` | Dedicated `stacks/react.csv` (React web patterns; load `react-spa` for implementation) |
| **Flutter 3.41.x** | `--stack flutter` | Dedicated `flutter.csv` with Riverpod, GoRouter, PopScope, ThemeData patterns |
| **iOS/SwiftUI** | `--stack swiftui` | SwiftUI-specific guidelines |

> **Angular gap documented:** `data/stacks/html-tailwind.csv` covers Tailwind patterns and responsive design but does not include Angular-specific patterns (Signals, daisyUI, `@defer`). For Angular-specific patterns, load `angular-spa` alongside this skill.

---

## Prerequisites

Python 3 required to run the search scripts:

```bash
python3 --version
# macOS: brew install python3
# Ubuntu: sudo apt install python3
```

---

## Step 1: Generate Design System (Always Start Here)

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<product_type> <keywords>" --design-system [-p "Project Name"]
```

This searches 5 domains in parallel (product, style, color, landing, typography) and returns:
- Recommended style + rationale
- Color palette with hex values
- Font pairing with rationale
- Effects and animation guidelines
- Anti-patterns to avoid

**Angular examples:**
```bash
# SaaS dashboard
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "saas dashboard analytics enterprise" --design-system -p "Dashboard"

# Dark admin panel
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "admin panel dark data management professional" --design-system -p "Admin"
```

**Flutter examples:**
```bash
# Health/wellness app
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "health wellness meditation calm" --design-system -p "Wellness App" --stack flutter

# Fintech mobile
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "fintech banking secure trust professional" --design-system -p "FinApp" --stack flutter
```

---

## Step 2: Domain-Specific Searches (As Needed)

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<keyword>" --domain <domain> [-n <max_results>]
```

| Domain | Use For | Example |
|--------|---------|---------|
| `style` | 50+ named styles (Glassmorphism, Brutalism, Aurora UI, etc.) | `--domain style "glassmorphism dark modern"` |
| `color` | 97 palettes by product type | `--domain color "saas enterprise blue"` |
| `typography` | 57 font pairings | `--domain typography "elegant serif luxury"` |
| `chart` | 25+ chart types | `--domain chart "real-time dashboard trend"` |
| `ux` | 99 UX guidelines | `--domain ux "animation accessibility loading"` |
| `landing` | Landing page structure | `--domain landing "hero social-proof conversion"` |
| `product` | Product-type patterns | `--domain product "healthcare SaaS dashboard"` |

---

## Step 3: Stack-Specific Guidelines

```bash
# Angular (html-tailwind)
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "responsive form focus" --stack html-tailwind

# Flutter
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "theming riverpod state" --stack flutter
```

---

## Workflow: Angular SPA Design

```
1. Run --design-system to get style + palette + typography
2. Load frontend-design skill → apply DFII scoring to recommended style
3. Load angular-spa skill → implement with daisyUI semantic tokens
4. Cross-check: are the palette hex values mappable to daisyUI semantic names?
   (e.g., primary color → bg-primary, surface → bg-base-100)
5. Run /lint-design-system to verify no hardcoded hex values slipped in
```

## Workflow: Flutter App Design

```
1. Run --design-system with --stack flutter
2. Load mobile-design skill → apply MFRI scoring
3. Load flutter-mobile skill → implement with ThemeData + AppSpacing tokens
4. Cross-check: are palette colors mapped to colorScheme roles?
   (primary, secondary, surface, onPrimary, etc.)
5. Run /lint-design-system to verify no Color(0xFF...) literals
```

---

## Output Formats

```bash
# ASCII box (default) — best for terminal
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "fintech" --design-system

# Markdown — best for documentation
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "fintech" --design-system -f markdown
```

Domain and stack searches exit like `grep`: `0` results found, `1` no results (widen the query or try
another domain; an empty search is not evidence the guideline does not exist), `2` error.

---

## Pre-Delivery Visual Checklist

Before delivering UI code, verify:

### Visual Quality
- [ ] No emojis used as icons (use SVG: Heroicons, Lucide)
- [ ] All icons from consistent icon set
- [ ] Hover states don't cause layout shift
- [ ] For Angular: using daisyUI semantic tokens, not raw hex

### Interaction
- [ ] All clickable elements have `cursor-pointer`
- [ ] Hover states provide clear visual feedback
- [ ] Transitions 150–300ms
- [ ] Focus states visible for keyboard navigation

### Contrast & Accessibility
- [ ] Light mode text >= 4.5:1 contrast ratio
- [ ] Glass/transparent elements visible in light mode
- [ ] `prefers-reduced-motion` respected
- [ ] Touch targets ≥ 24×24 CSS px (WCAG 2.5.8 AA); house standard 44px (web) / 48dp (Flutter)

### Layout
- [ ] Responsive at 320px (WCAG 1.4.10 reflow floor), 375px, 768px, 1024px, 1440px
- [ ] No horizontal scroll on mobile
- [ ] No content hidden behind fixed navbars

---

## Rule Priority

| Priority | Category | Impact |
|---|---|---|
| 1 | Accessibility (contrast, focus, ARIA) | CRITICAL |
| 2 | Touch & Interaction (≥ 24px targets AA, 44px house standard; feedback) | CRITICAL |
| 3 | Performance (image optimization, reduced-motion) | HIGH |
| 4 | Layout & Responsive (viewport, readable font) | HIGH |
| 5 | Typography & Color (line-height, font pairing) | MEDIUM |
| 6 | Animation (150–300ms timing, transform-based) | MEDIUM |
| 7 | Style Selection (match product type) | MEDIUM |
| 8 | Charts & Data (chart type match, alt table) | LOW |

---

## Related Skills

- `frontend-design` — design direction methodology (DFII scoring, Design Thinking Phase). **Load after this skill** to apply DFII scoring to the recommended style.
- `angular-spa` — Angular 21.x implementation with daisyUI v5.5.5 tokens
- `flutter-mobile` — Flutter 3.41.x implementation with ThemeData tokens
- `tailwind-patterns` — Tailwind v4 CSS-first config patterns
- `design-system` — token enforcement for Angular + Flutter
- `accessibility-audit` — canonical WCAG 2.2 AA checklist and audit (deeper than this skill's checklist)

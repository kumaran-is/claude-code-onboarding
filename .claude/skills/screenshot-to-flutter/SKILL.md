---
name: screenshot-to-flutter
description: "Pixel-perfect Flutter widget replication from a screenshot. Use when the user provides a UI screenshot and asks to replicate, clone, implement, or build it in Flutter. Enforces design system tokens (ColorScheme tokens, AppSpacing, TextTheme) — never raw hex or hardcoded values. Triggers: screenshot to flutter, replicate this screen, clone this UI, build this screen in flutter, implement this design in flutter."
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
metadata:
  triggers: screenshot to flutter, replicate screen, clone UI, pixel perfect flutter, implement design flutter, build this screen flutter, recreate UI flutter
  related-skills: flutter-mobile, mobile-design, ui-standards-tokens, riverpod-patterns
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-04-04"
---

## Iron Law

**NEVER output raw hex codes, hardcoded font sizes, or raw spacing values. ALL colors → `Theme.of(context).colorScheme.*`, ALL spacing → `AppSpacing.*`, ALL typography → `Theme.of(context).textTheme.*`. Pixel-perfect means visually identical, not token-violating.**

# Screenshot-to-Flutter Skill

## Purpose

Replicate a UI screenshot as a production-ready Flutter widget with pixel-perfect visual accuracy, while staying compliant with your project's design system.

---

## Phase 1 — Screenshot Analysis (mandatory before writing code)

Extract these properties visually from the screenshot. Document them before coding.

### Layout Analysis
```
□ Layout type: Column / Row / Stack / CustomScrollView / GridView
□ Scrollable? Yes / No — if yes, which axis
□ Has AppBar / navigation bar? → describe exactly
□ Has bottom navigation? → describe tabs/icons
□ Has FAB? → position and style
□ Has bottom sheet or modal? → note handle style
```

### Color Extraction (map to tokens — do NOT use raw hex)
```
□ Background color   → map to: surface / surfaceContainerLowest…Highest (background, surfaceVariant are deprecated)
□ Primary accent     → map to: primary / secondary / tertiary
□ Card background    → map to: surfaceContainer / surfaceContainerHigh
□ Text (heading)     → map to: onSurface (onBackground is deprecated)
□ Text (body)        → map to: onSurface / onSurfaceVariant
□ Icon color         → map to: onSurfaceVariant / primary
□ Divider color      → map to: outlineVariant
□ Error state        → map to: error / onError
```

**Token mapping rule:** If the screenshot uses a color that doesn't map cleanly to a token, use the closest semantic token and note the approximation in a `// Design note:` comment.

### Typography Analysis (map to TextTheme)
```
□ Heading size       → headlineLarge / headlineMedium / headlineSmall
□ Title size         → titleLarge / titleMedium / titleSmall
□ Body size          → bodyLarge / bodyMedium / bodySmall
□ Caption size       → labelLarge / labelMedium / labelSmall
□ Font weight        → FontWeight.w400 / w500 / w600 / w700
□ Letter spacing     → note if visually different from default
```

### Spacing Analysis (map to AppSpacing)
```
□ Outer padding      → AppSpacing.md (16) / AppSpacing.lg (24) / AppSpacing.xl (32)
□ Inner card padding → AppSpacing.sm (8) / AppSpacing.md (16)
□ Gap between items  → AppSpacing.xs (4) / AppSpacing.sm (8) / AppSpacing.md (16)
□ Section spacing    → AppSpacing.lg (24) / AppSpacing.xl (32)
```

### Component Inventory
```
□ Buttons: count, type (filled/outlined/text/icon), border radius
□ Cards: count, elevation, border radius, border presence
□ Input fields: count, decoration style, placeholder presence
□ List items: spacing, leading/trailing widgets, divider style
□ Images/avatars: size, shape (circle/rounded/square), placeholder needed
□ Icons: which icon set (Material / Cupertino), sizes
□ Chips/badges: style, colors
```

---

## Phase 2 — Implementation Rules

### Structure
- **One widget per file** — name matches the screen (e.g. `property_detail_screen.dart`)
- Place in `lib/features/<feature>/presentation/screens/` or `lib/features/<feature>/presentation/widgets/`
- Use `ConsumerWidget` if the screen needs Riverpod state, `StatelessWidget` if pure display
- Extract repeated sub-components (e.g. a repeated card) into separate widget files

### Flutter-Specific Replication Rules

Flutter 3.50.x: import Material widgets from `package:material_ui/material_ui.dart` (pin `material_ui: 1.11.1`); `package:flutter/material.dart` is deprecated since 3.47 and fails a zero-issue `flutter analyze`.

| Screenshot Element | Flutter Implementation |
|---|---|
| Column layout | `Column` with `crossAxisAlignment` matching visual alignment |
| Scrollable content | `SingleChildScrollView` + `Column` OR `ListView.builder` |
| Card | `Card` with `elevation`, `shape: RoundedRectangleBorder(borderRadius: ...)` |
| List items | `ListTile` or custom widget — match leading/trailing/spacing exactly |
| Navigation bar | `NavigationBar` (Material 3) — match selected/unselected states |
| AppBar | `AppBar` with `backgroundColor`, `elevation`, `titleTextStyle` from theme |
| Bottom sheet | `BottomSheet` with `DraggableScrollableSheet` if scrollable |
| Input field | `TextFormField` with `InputDecoration` matching border style |
| Filled button | `FilledButton` — do not use `ElevatedButton` for Material 3 screens |
| Outlined button | `OutlinedButton` |
| Text button | `TextButton` |
| Avatar | `CircleAvatar` with `backgroundImage: NetworkImage(placeholder)` |
| Chip | `Chip` or `FilterChip` depending on interactivity |
| Divider | `Divider(color: theme.colorScheme.outlineVariant)` |
| Shadow | `BoxDecoration(boxShadow: [...])` — match blur radius visually |

### Interaction Rules
```dart
// Pressed state — use InkWell or GestureDetector, not onTap only
InkWell(
  onTap: () {},
  borderRadius: BorderRadius.circular(N),
  child: ...,
)

// Scroll behavior — always clip properly
ClipRRect(
  borderRadius: ...,
  child: SingleChildScrollView(...)
)
```

### Design System Token Reference
```dart
// Colors — from theme, never hardcoded
final cs = Theme.of(context).colorScheme;
cs.primary          // primary accent
cs.surface          // card/screen background
cs.onSurface        // body text
cs.onSurfaceVariant // secondary text, icons
cs.outlineVariant   // dividers, borders
cs.error            // error states

// Typography — from theme, never hardcoded
final tt = Theme.of(context).textTheme;
tt.headlineMedium   // screen title
tt.titleLarge       // section header
tt.bodyMedium       // body text
tt.labelSmall       // caption, badge text

// Spacing — from AppSpacing, never hardcoded px
AppSpacing.xs  // 4
AppSpacing.sm  // 8
AppSpacing.md  // 16
AppSpacing.lg  // 24
AppSpacing.xl  // 32
AppSpacing.xxl // 48
```

---

## Phase 3 — Output Format

```
## Screenshot Analysis
- Layout: [type]
- Components found: [list]
- Color mapping: [screenshot color → token]
- Typography mapping: [size → TextTheme style]
- Approximations: [anything that couldn't map cleanly, with reason]

## Widget Tree
[Mermaid or indented tree showing widget hierarchy]

## Implementation
[Complete .dart file — production-ready, no TODOs, no stubs]

## Design Notes
[Any visual approximations made, placeholder images used, tokens chosen]
```

---

## Quality Gates (check before reporting done)

- [ ] Zero raw hex color values in output (`grep -rn "0x[0-9a-fA-F]\|Color(0" lib/` returns no hits in new code)
- [ ] Zero hardcoded `fontSize`, `padding`, or spacing numbers (`grep -rn "fontSize:" lib/` returns no hits in new code; spacing only via `AppSpacing.*`)
- [ ] Touch targets ≥ 48dp for every interactive element (house standard; WCAG 2.2 AA minimum is 24×24)
- [ ] `/lint-design-system` run with zero violations
- [ ] Every interactive element has a pressed state (`InkWell` / `GestureDetector`)
- [ ] Images use `placeholder` pattern (not missing or broken)
- [ ] `flutter analyze` would pass (no obvious type errors, no unused imports)
- [ ] Navigation bar / AppBar replicated if present in screenshot
- [ ] Widget file placed in correct feature directory
- [ ] `ConsumerWidget` used only if Riverpod state is actually needed
- [ ] Reviewers dispatched: `riverpod-reviewer` (if providers were added), `accessibility-auditor` (Semantics, contrast, touch targets), `ui-standards-expert` (token compliance)

---

## Related Skills
- Load `mobile-design` first if the screen requires MFRI assessment (new feature, not pure replication)
- Load `riverpod-patterns` if the screen needs state management wired up
- Load `ui-standards-tokens` for full AppSpacing / TextTheme token reference

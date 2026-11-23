# Screenshot-to-Flutter Workflow

> **When to use**: User provides a UI screenshot and asks to replicate, clone, or implement it in Flutter
> **Prerequisites**: Flutter project scaffolded with project design system (ColorScheme, AppSpacing, TextTheme)

## Overview

Replicate a UI screenshot as a production-ready Flutter widget with pixel-perfect visual accuracy, compliant with the project design system. Uses `screenshot-to-flutter` skill.

---

## Iron Law (from skill)

**NEVER output raw hex codes, hardcoded font sizes, or raw spacing values. ALL colors → `Theme.of(context).colorScheme.*`, ALL spacing → `AppSpacing.*`, ALL typography → `Theme.of(context).textTheme.*`.**

---

## Phases

### Phase 1 — Load Skill and Analyze Screenshot

**Load skill first:**
```
/screenshot-to-flutter
```

**Skills to also load if needed:**
- `flutter-mobile` — Riverpod, Freezed, widget architecture
- `mobile-design` — touch psychology, MFRI risk scoring, platform conventions
- `ui-standards-tokens` — design token audit
- `riverpod-patterns` — state management if the screen has async data

**MCP queries:**
```
mcp__dart-mcp-server__analyze_files     → check existing token definitions
mcp__context7__resolve-library-id       → flutter, riverpod
```

**Screenshot analysis checklist (mandatory before coding):**
```
□ Layout type: Column / Row / Stack / CustomScrollView / GridView
□ Scrollable? Yes / No — which axis
□ AppBar / navigation bar present? → describe exactly
□ Bottom navigation? → describe tabs/icons
□ FAB? → position and style
□ Bottom sheet or modal? → handle style
□ Color palette → map to colorScheme tokens
□ Typography → map to textTheme variants
□ Spacing → map to AppSpacing constants
□ Component inventory: buttons, cards, inputs, chips, dividers
```

**Token mapping:**
```
Background color   → colorScheme.surface / .surfaceContainerLow…Highest (.background/.surfaceVariant are deprecated)
Primary accent     → colorScheme.primary / .secondary / .tertiary
Card background    → colorScheme.surfaceContainer / .surfaceContainerHigh
Heading text       → textTheme.headlineLarge/Medium/Small
Body text          → textTheme.bodyLarge/Medium/Small
Outer padding      → AppSpacing.md (16) / AppSpacing.lg (24)
Inner padding      → AppSpacing.sm (8) / AppSpacing.md (16)
Gap between items  → AppSpacing.xs (4) / AppSpacing.sm (8)
```

---

### Phase 2 — Implement Widget

**File placement:**
- Screen: `lib/features/<feature>/presentation/screens/<name>_screen.dart`
- Reusable widget: `lib/features/<feature>/presentation/widgets/<name>_widget.dart`

**Widget type selection:**
- Use `ConsumerWidget` if the screen needs Riverpod state
- Use `StatelessWidget` if pure display (no async data)

**Screenshot element → Flutter widget mapping** (Flutter 3.50.x: Material widgets come from `package:material_ui/material_ui.dart`):

| Screenshot element | Flutter implementation |
|---|---|
| Column layout | `Column` with `crossAxisAlignment` matching visual alignment |
| Scrollable list | `ListView.builder` or `SingleChildScrollView` + `Column` |
| Card | `Card` with `elevation`, `shape: RoundedRectangleBorder(...)` |
| Navigation bar | `NavigationBar` (Material 3) |
| AppBar | `AppBar` with theme-derived `backgroundColor` and `titleTextStyle` |
| Filled button | `FilledButton` (not `ElevatedButton` for Material 3) |
| Outlined button | `OutlinedButton` |
| Input field | `TextFormField` with `InputDecoration` |
| Avatar | `CircleAvatar` with `backgroundImage: NetworkImage(placeholder)` |
| Chip | `Chip` or `FilterChip` |
| Divider | `Divider(color: theme.colorScheme.outlineVariant)` |
| Bottom sheet | `DraggableScrollableSheet` |

---

### Phase 3 — Review Gate

Run after implementation:

```
□ Zero raw hex values (grep -r "0x[0-9a-fA-F]\|Color(0" lib/)
□ Zero hardcoded font sizes (grep -r "fontSize:" lib/)
□ Zero raw spacing values — only AppSpacing.* constants
□ flutter analyze exits with 0 errors and 0 new warnings
□ Touch targets ≥ 48dp for all interactive elements
□ /lint-design-system passes with zero violations
```

**Dispatch reviewer:**
- `riverpod-reviewer` agent — if Riverpod providers were added
- `accessibility-auditor` agent — Semantics widgets, contrast, touch targets
- `ui-standards-expert` agent — token compliance

---

## Common Pitfalls

| Mistake | Fix |
|---|---|
| `Color(0xFF3B82F6)` hardcoded | Map to `colorScheme.primary` or nearest token |
| `fontSize: 16` hardcoded | Use `textTheme.bodyLarge` |
| `SizedBox(height: 16)` raw value | Use `SizedBox(height: AppSpacing.md)` |
| `Padding(padding: EdgeInsets.all(12))` | Use `EdgeInsets.all(AppSpacing.sm)` (8) or `.md` (16) |
| Using `ElevatedButton` for Material 3 | Use `FilledButton` for primary actions |
| Pixel-perfect via hardcoded values | Visual accuracy through tokens — never bypass the design system |

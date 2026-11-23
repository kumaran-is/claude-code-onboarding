# Android Platform Guidelines

Material Design 3 essentials, Android design conventions, Roboto typography, and native patterns. Read this file when building Flutter screens that target Android devices.

**Flutter note:** These Material Design 3 principles apply directly when building Flutter screens for Android. Flutter's Material widgets implement the M3 spec natively. Use `Theme.of(context)` for all color and typography. For Android-specific behaviors (predictive back, edge-to-edge, dynamic color), use the appropriate Flutter APIs described below.

---

## 1. Material Design 3 Philosophy

### Core Material Principles

```
MATERIAL AS METAPHOR:
+-- Surfaces exist in 3D space
+-- Light and shadow define hierarchy
+-- Motion provides continuity
+-- Bold, graphic, intentional design

ADAPTIVE DESIGN:
+-- Responds to device capabilities
+-- One UI for all form factors
+-- Dynamic color from wallpaper (Android 12+)
+-- Personalized per user

ACCESSIBLE BY DEFAULT:
+-- Large touch targets (48dp minimum)
+-- Clear visual hierarchy
+-- Semantic colors
+-- Motion respects preferences
```

### Material Design Values

| Value | Implementation |
|-------|----------------|
| **Dynamic Color** | Colors adapt to wallpaper/user preference |
| **Personalization** | User-specific themes |
| **Accessibility** | Built into every component |
| **Responsiveness** | Works on all screen sizes |
| **Consistency** | Unified design language |

---

## 2. Android Typography

### Roboto Font Family

```
Android System Fonts:
+-- Roboto: Default sans-serif
+-- Roboto Flex: Variable font (API 33+)
+-- Roboto Serif: Serif alternative
+-- Roboto Mono: Monospace
```

### Material Type Scale

| Role | Size | Weight | Usage |
|------|------|--------|-------|
| **Display Large** | 57sp | Regular | Hero text, splash |
| **Headline Large** | 32sp | Regular | Page titles |
| **Headline Medium** | 28sp | Regular | Section headers |
| **Title Large** | 22sp | Regular | Dialogs, cards |
| **Title Medium** | 16sp | Medium | Lists, navigation |
| **Body Large** | 16sp | Regular | Primary content |
| **Body Medium** | 14sp | Regular | Secondary content |
| **Label Large** | 14sp | Medium | Buttons, FAB |
| **Label Medium** | 12sp | Medium | Navigation |

In Flutter, all these roles map directly to `Theme.of(context).textTheme`:

```dart
// Maps:
// Display Large -> textTheme.displayLarge
// Headline Large -> textTheme.headlineLarge
// Title Large -> textTheme.titleLarge
// Body Large -> textTheme.bodyLarge
// Label Large -> textTheme.labelLarge
Text('Hello', style: Theme.of(context).textTheme.bodyLarge)
```

### Scalable Pixels

```
sp = Scale-independent pixels
sp automatically scales with user font size preference.

RULE: Flutter's Theme.of(context).textTheme handles sp scaling
automatically — never hardcode fontSize values.
```

---

## 3. Material Color System

### Dynamic Color (Material You, Android 12+)

Android 12+ can extract a color palette from the user's wallpaper and apply it to your app theme. In Flutter, use the `dynamic_color` package:

```dart
// pubspec.yaml: dynamic_color: 2.1.0  (already built on material_ui; verified on Flutter 3.50.1)
import 'package:dynamic_color/dynamic_color.dart';
import 'package:material_ui/material_ui.dart';

DynamicColorBuilder(
  builder: (lightDynamic, darkDynamic) {
    return MaterialApp(
      theme: ThemeData(
        colorScheme: lightDynamic ?? defaultLightColorScheme,
      ),
      darkTheme: ThemeData(
        colorScheme: darkDynamic ?? defaultDarkColorScheme,
      ),
    );
  },
)
```

### Semantic Color Roles

In Flutter, all Material 3 color roles are available through `Theme.of(context).colorScheme`:

```dart
colorScheme.surface          // Main background
colorScheme.surfaceContainerHighest // Cards, containers (surfaceVariant is deprecated)
colorScheme.onSurface        // Primary text
colorScheme.onSurfaceVariant // Secondary text
colorScheme.outline          // Borders, dividers
colorScheme.primary          // Key actions, FAB
colorScheme.onPrimary        // Text on primary
colorScheme.primaryContainer // Less emphasis containers
colorScheme.error            // Errors, destructive
```

### Dark Theme

```
Material Dark Theme:
+-- Background: #121212 (not pure black by default)
+-- Surface: elevated using overlay, not shadow
+-- Elevation: Higher elevation = lighter overlay
+-- Reduce color saturation on dark backgrounds
+-- Always check contrast ratios (WCAG AA)

RULE: Use ThemeData.dark() + ColorScheme.fromSeed() in Flutter
for automatic dark mode — never manually invert colors.
```

---

## 4. Android Layout and Spacing

### Layout Grid

```
Android uses 8dp baseline grid:

All spacing in multiples of 8dp:
+-- 4dp: Component internal (half-step)
+-- 8dp: Minimum spacing
+-- 16dp: Standard spacing
+-- 24dp: Section spacing
+-- 32dp: Large spacing

Margins:
+-- Compact (phone): 16dp
+-- Medium (small tablet): 24dp
+-- Expanded (large): 24dp+ or columns
```

In Flutter, use `AppSpacing.*` tokens from the `ui-standards-tokens` skill for all spacing values.

### Responsive Layout

```
Window Size Classes:

COMPACT (< 600dp width):
+-- Phones in portrait
+-- Single column layout
+-- Bottom navigation

MEDIUM (600-840dp width):
+-- Tablets, foldables
+-- Consider 2 columns
+-- Navigation rail

EXPANDED (> 840dp width):
+-- Large tablets
+-- Multi-column layouts
+-- Navigation drawer
```

In Flutter, use `MediaQuery.of(context).size.width` or the `adaptive_layout` package to respond to window size classes.

---

## 5. Android Navigation Patterns

### Navigation Components

| Component | Use Case | Flutter Implementation |
|-----------|----------|------------------------|
| **Bottom Navigation** | 3-5 top-level destinations | `NavigationBar` (M3) |
| **Navigation Rail** | Tablets | `NavigationRail` |
| **Navigation Drawer** | Many destinations | `Drawer` with `NavigationDrawer` |
| **Top App Bar** | Current context, actions | `AppBar` with M3 style |

### Bottom Navigation (Material 3)

```
Rules:
+-- 3-5 destinations
+-- Icons: Material Symbols (24dp visual, 48dp touch target)
+-- Labels: Always visible (accessibility)
+-- Active: Filled icon + indicator pill (M3 style)
+-- Badge: For notifications (Badge widget in Flutter)
```

```dart
NavigationBar(
  destinations: const [
    NavigationDestination(
      icon: Icon(Icons.home_outlined),
      selectedIcon: Icon(Icons.home),
      label: 'Home',
    ),
    NavigationDestination(
      icon: Icon(Icons.search_outlined),
      selectedIcon: Icon(Icons.search),
      label: 'Search',
    ),
  ],
  selectedIndex: _selectedIndex,
  onDestinationSelected: (index) => setState(() => _selectedIndex = index),
)
```

### Back Navigation

```
Android provides system back:
+-- Back button (3-button navigation)
+-- Back gesture (swipe from edge)
+-- Predictive back (Android 14+)

Your app must:
+-- Handle back correctly (pop stack — GoRouter does this)
+-- Support predictive back animation
+-- Never hijack/override back unexpectedly
+-- Confirm before discarding unsaved work
```

GoRouter handles back navigation automatically. For custom back behavior, use `PopScope`:

```dart
PopScope(
  canPop: !_hasUnsavedChanges,
  onPopInvokedWithResult: (didPop, result) { // onPopInvoked is deprecated
    if (!didPop) {
      _showUnsavedChangesDialog();
    }
  },
  child: ...,
)
```

---

## 6. Material Components in Flutter

### Buttons (Material 3)

```dart
// Primary action
FilledButton(onPressed: onPressed, child: const Text('Confirm'))

// Secondary action
FilledButton.tonal(onPressed: onPressed, child: const Text('Save'))

// Tertiary action
OutlinedButton(onPressed: onPressed, child: const Text('Cancel'))

// Lowest emphasis
TextButton(onPressed: onPressed, child: const Text('Skip'))
```

### Floating Action Button

```dart
// Standard FAB
FloatingActionButton(
  onPressed: onPressed,
  child: const Icon(Icons.add),
)

// Extended FAB (icon + label)
FloatingActionButton.extended(
  onPressed: onPressed,
  icon: const Icon(Icons.add),
  label: const Text('New Item'),
)

// Position: Bottom right, 16dp from edges (Scaffold handles this)
```

### Cards (Material 3)

```dart
// Elevated card
Card(
  child: Padding(
    padding: const EdgeInsets.all(16),
    child: content,
  ),
)

// Filled card
Card.filled(child: content)

// Outlined card
Card.outlined(child: content)
// Corner radius: 12dp (M3 default in Flutter)
```

### Text Fields (Material 3)

```dart
// Filled text field (default M3)
TextField(
  decoration: const InputDecoration(
    labelText: 'Email',
    hintText: 'Enter your email',
    filled: true,
  ),
)

// Outlined text field
TextField(
  decoration: const InputDecoration(
    labelText: 'Email',
    border: OutlineInputBorder(),
  ),
)
```

---

## 7. Android-Specific Patterns

### Snackbars

```dart
// M3 Snackbar with action
ScaffoldMessenger.of(context).showSnackBar(
  SnackBar(
    content: const Text('Archived 1 item'),
    action: SnackBarAction(
      label: 'UNDO',
      onPressed: () { /* undo */ },
    ),
    duration: const Duration(seconds: 4),
  ),
)

// Rules:
// +-- Brief message, single line if possible
// +-- One action (text, not icon)
// +-- Can be dismissed by swipe
// +-- Don't stack — queue them
```

### Bottom Sheets (Material 3)

```dart
showModalBottomSheet(
  context: context,
  useSafeArea: true,
  showDragHandle: true,        // Shows drag handle per M3
  isScrollControlled: true,
  builder: (context) => content,
)
// Corner radius: 28dp (top corners, M3 default)
```

### Ripple Effect

Every touchable element gets ripple in Flutter automatically via `InkWell` and `InkResponse`. Never use `GestureDetector` alone for primary actions — always use `InkWell` or `FilledButton`/`TextButton` which include ripple:

```dart
// Ripple included automatically:
InkWell(
  onTap: onTap,
  borderRadius: BorderRadius.circular(8),
  child: content,
)
```

---

## 8. Material Symbols in Flutter

```dart
// Add to pubspec.yaml:
// material_symbols_icons: 4.2960.0

import 'package:material_symbols_icons/symbols.dart';

// Use with fill control:
Icon(Symbols.home, fill: 1) // Filled (active)
Icon(Symbols.home, fill: 0) // Outlined (inactive)
Icon(Symbols.home, size: 24) // Standard size
```

---

## 9. Android Accessibility

### TalkBack Requirements

```dart
// Every interactive element needs Semantics
Semantics(
  label: 'Play button',
  button: true,
  child: InkWell(
    onTap: onTap,
    child: const Icon(Icons.play_arrow),
  ),
)
```

### Touch Target Size

```
MANDATORY: 48dp x 48dp minimum in Flutter

Even if visual element is smaller:
+-- Icon: 24dp visual, 48dp touch area
+-- Add padding or use SizedBox to reach 48dp

Spacing between targets: 8dp minimum
```

### Font Scaling

Android supports font scaling up to 200%. In Flutter, `Theme.of(context).textTheme.*` scales automatically. Never lock scaling (`TextScaler.noScaling`, or the deprecated `textScaleFactor`): that breaks accessibility. Android 14+ scales non-linearly, so read sizes through `MediaQuery.textScalerOf(context)`.

### Reduce Motion

```dart
// Check preference in Flutter
final reduceMotion = MediaQuery.disableAnimationsOf(context); // rebuilds only on this field

if (reduceMotion) {
  // Use instant transitions (duration: Duration.zero)
} else {
  // Use animations
}
```

---

## 10. Android Checklist

### Before Every Android Screen

- [ ] Using Material 3 components (FilledButton, NavigationBar, etc.)
- [ ] Touch targets >= 48dp
- [ ] InkWell ripple on all tappable elements
- [ ] Using Theme.of(context).textTheme (Roboto, sp scaling)
- [ ] Semantic colors via colorScheme (dynamic color support)
- [ ] Back navigation works correctly (GoRouter + PopScope)

### Before Android Release

- [ ] Dark theme tested
- [ ] Dynamic color tested (if supported — use dynamic_color package)
- [ ] All font sizes tested (200% scale in accessibility settings)
- [ ] TalkBack tested (enable in Settings)
- [ ] Predictive back implemented (PopScope) for Android 14+
- [ ] Edge-to-edge display (Android 15+ — use `enableEdgeToEdge()`)
- [ ] Different screen sizes tested (phones, tablets)
- [ ] Navigation patterns match platform (system back, gestures)

---

> **Remember:** Android users expect Material Design. Custom designs that ignore Material patterns feel foreign. Use Material components as your foundation and customize thoughtfully.

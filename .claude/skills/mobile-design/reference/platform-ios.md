# iOS Platform Guidelines

Human Interface Guidelines (HIG) essentials, iOS design conventions, SF Pro typography, and native patterns. Read this file when building Flutter screens that target iPhone or iPad.

**Flutter note:** These iOS HIG principles apply when building adaptive Flutter screens for iOS. In Flutter, use `CupertinoWidget` variants (CupertinoNavigationBar, CupertinoTabBar, CupertinoAlertDialog) for iOS-specific components, or check `Platform.isIOS` for conditional behavior. See the `flutter-mobile` skill for platform channel patterns and adaptive widget selection.

---

## 1. Human Interface Guidelines Philosophy

### Core Apple Design Principles

```
CLARITY:
+-- Text is legible at every size
+-- Icons are precise and lucid
+-- Adornments are subtle and appropriate
+-- Focus on functionality drives design

DEFERENCE:
+-- UI helps people understand and interact
+-- Content fills the screen
+-- UI never competes with content
+-- Translucency hints at more content

DEPTH:
+-- Distinct visual layers convey hierarchy
+-- Transitions provide sense of depth
+-- Touch reveals functionality
+-- Content is elevated over UI
```

### iOS Design Values

| Value | Implementation |
|-------|----------------|
| **Aesthetic Integrity** | Design matches function (game != productivity) |
| **Consistency** | Use system controls, familiar patterns |
| **Direct Manipulation** | Touch directly affects content |
| **Feedback** | Actions are acknowledged |
| **Metaphors** | Real-world comparisons aid understanding |
| **User Control** | User initiates actions, can cancel |

---

## 2. iOS Typography

### SF Pro Font Family

```
iOS System Fonts:
+-- SF Pro Text: Body text (< 20pt)
+-- SF Pro Display: Large titles (>= 20pt)
+-- SF Pro Rounded: Friendly contexts
+-- SF Mono: Code, tabular data
```

### iOS Type Scale (Dynamic Type)

| Style | Default Size | Weight | Usage |
|-------|--------------|--------|-------|
| **Large Title** | 34pt | Bold | Navigation bar (scroll collapse) |
| **Title 1** | 28pt | Bold | Page titles |
| **Title 2** | 22pt | Bold | Section headers |
| **Title 3** | 20pt | Semibold | Subsection headers |
| **Headline** | 17pt | Semibold | Emphasized body |
| **Body** | 17pt | Regular | Primary content |
| **Callout** | 16pt | Regular | Secondary content |
| **Subhead** | 15pt | Regular | Tertiary content |
| **Footnote** | 13pt | Regular | Caption, timestamps |
| **Caption 1** | 12pt | Regular | Annotations |
| **Caption 2** | 11pt | Regular | Fine print |

### Dynamic Type Support (MANDATORY)

In Flutter, use `Theme.of(context).textTheme.*` which automatically scales with the system text size setting. Never hardcode `fontSize` values in a `TextStyle` without using `Theme.of(context)`.

```dart
// WRONG: Fixed font size
Text('Hello', style: TextStyle(fontSize: 17))

// CORRECT: Theme text style (scales with user settings)
Text('Hello', style: Theme.of(context).textTheme.bodyLarge)

// Also correct for explicit scaling:
Text('Hello', style: CupertinoTheme.of(context).textTheme.textStyle)
```

---

## 3. iOS Color System

### Semantic Colors (Automatic Dark Mode)

Use semantic colors so your app adapts to dark mode automatically. In Flutter, use `Theme.of(context).colorScheme.*` rather than hardcoded values:

```dart
// Maps to iOS semantic color roles
colorScheme.surface          // systemBackground
colorScheme.onSurface        // label (primary text)
colorScheme.surfaceContainerHighest // secondarySystemBackground (surfaceVariant is deprecated)
colorScheme.primary          // tintColor / accent
colorScheme.error            // systemRed
```

### iOS System Accent Colors (for reference)

| Color | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| Blue | #007AFF | #0A84FF | Links, highlights, default tint |
| Green | #34C759 | #30D158 | Success, positive |
| Red | #FF3B30 | #FF453A | Errors, destructive |
| Orange | #FF9500 | #FF9F0A | Warnings |
| Yellow | #FFCC00 | #FFD60A | Attention |

### Dark Mode Considerations

```
iOS Dark Mode is NOT inverted light mode:

LIGHT MODE:              DARK MODE:
+-- White backgrounds    +-- True black or near-black
+-- High saturation      +-- Desaturated colors
+-- Black text           +-- White/light gray text
+-- Drop shadows         +-- Glows or no shadows

RULE: Always use Theme.of(context).colorScheme — never hardcode colors.
```

---

## 4. iOS Layout and Spacing

### Safe Areas

```
+-------------------------------------+
|XXXXXXXXXXXXX Status Bar XXXXXXXXXXXXX| <- Top safe area inset
+-------------------------------------+
|                                     |
|                                     |
|         Safe Content Area           |
|                                     |
|                                     |
+-------------------------------------+
|XXXXXXXXXXXXXXX Home Indicator XXXXXXX| <- Bottom safe area inset
+-------------------------------------+

RULE: Never place interactive content in unsafe areas.
Flutter handles this via SafeArea widget and MediaQuery.paddingOf(context)
```

In Flutter, wrap content in `SafeArea` or use `MediaQuery.viewPaddingOf(context)` to respect the Dynamic Island, notch, and home indicator.

### Standard Margins and Padding

| Element | Margin | Notes |
|---------|--------|-------|
| Screen edge to content | 16pt | Standard horizontal margin |
| Card internal padding | 16pt | Content within cards |
| Button internal padding | 12pt vertical, 16pt horizontal | Minimum |
| List item padding | 16pt horizontal | Standard cell padding |

### iOS Grid System

```
iPhone Grid (Standard):
+-- 16pt margins (left/right)
+-- 8pt minimum spacing
+-- Content in 8pt multiples

iPad Grid:
+-- 20pt margins (or more)
+-- Consider multi-column layouts
```

---

## 5. iOS Navigation Patterns

### Navigation Types

| Pattern | Use Case | Flutter Implementation |
|---------|----------|------------------------|
| **Tab Bar** | 3-5 top-level sections | `CupertinoTabBar` or `BottomNavigationBar` |
| **Navigation Controller** | Hierarchical drill-down | `Navigator` via `GoRouter` |
| **Modal** | Focused task | `showModalBottomSheet` or `showCupertinoModalPopup` |
| **Alert** | Critical interruption | `showCupertinoDialog` |

### Tab Bar Guidelines

```
Rules:
+-- 3-5 items maximum
+-- Icons: SF Symbols or custom (25x25pt visual, 49pt height touch area)
+-- Labels: Always include (accessibility)
+-- Active state: Filled icon + tint color
+-- Tab bar always visible (do not hide on scroll)
```

### Navigation Bar Guidelines

```
Rules:
+-- Back button: System chevron + previous title (or "Back")
+-- Title: Centered, dynamic font
+-- Right actions: Max 2 items
+-- Large title: Collapses on scroll (optional)
+-- Prefer text buttons over icons (clarity)
```

### Modal Presentations

| Style | Use Case | Flutter |
|-------|----------|---------|
| **Sheet (default)** | Secondary tasks | `showModalBottomSheet` |
| **Full Screen** | Immersive tasks | `Navigator.push` full-screen route |
| **Alert** | Critical interruption | `showCupertinoDialog` |
| **Action Sheet** | Choices from context | `showCupertinoModalPopup` |

### Gestures

| Gesture | iOS Convention | Flutter |
|---------|----------------|---------|
| **Edge swipe (left)** | Navigate back | Enabled by default in `Navigator` |
| **Pull down (sheet)** | Dismiss modal | `DraggableScrollableSheet` |
| **Long press** | Context menu | `GestureDetector.onLongPress` |

---

## 6. iOS-Specific Patterns

### Pull to Refresh

```dart
// Flutter implementation
RefreshIndicator(
  onRefresh: () async {
    await ref.read(myProvider.notifier).refresh();
  },
  child: ListView.builder(
    itemCount: items.length,
    itemBuilder: (context, index) => ItemTile(items[index]),
  ),
)
```

### Bottom Sheets (iOS Sheet Style)

iOS 15+ detents (half-sheet / full-sheet):

```dart
showModalBottomSheet(
  context: context,
  isScrollControlled: true,    // Allows full-height sheets
  backgroundColor: Colors.transparent,
  builder: (context) => DraggableScrollableSheet(
    initialChildSize: 0.5,     // Half screen
    maxChildSize: 0.95,        // Near full screen
    minChildSize: 0.25,
    builder: (context, scrollController) => SheetContent(),
  ),
)
```

### Context Menus (Long Press)

```dart
GestureDetector(
  onLongPress: () {
    showCupertinoModalPopup(
      context: context,
      builder: (context) => CupertinoActionSheet(
        title: const Text('Options'),
        actions: [
          CupertinoActionSheetAction(
            onPressed: () { ... },
            child: const Text('Copy'),
          ),
          CupertinoActionSheetAction(
            isDestructiveAction: true,
            onPressed: () { ... },
            child: const Text('Delete'),
          ),
        ],
        cancelButton: CupertinoActionSheetAction(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
      ),
    );
  },
  child: child,
)
```

---

## 7. SF Symbols in Flutter

SF Symbols are not available as a Flutter package. Options:
- Use `cupertino_icons` package for the most common SF Symbol equivalents
- Use `flutter_svg` with exported SVGs of custom symbols
- Use Material Icons as cross-platform alternative and adapt to platform

---

## 8. iOS Accessibility

### VoiceOver Requirements

Every interactive widget must have Semantics:

```dart
Semantics(
  label: 'Play button',
  hint: 'Plays the selected track',
  button: true,
  child: InkWell(
    onTap: onTap,
    child: const Icon(Icons.play_arrow),
  ),
)
```

### Dynamic Type Scaling

Support all Dynamic Type sizes. In Flutter, using `Theme.of(context).textTheme.*` handles this automatically. Never lock font scaling (`TextScaler.noScaling`, or the deprecated `textScaleFactor: 1.0`): that breaks accessibility.

### Reduce Motion

```dart
// Respect reduce motion preference
final reduceMotion = MediaQuery.disableAnimationsOf(context);

if (reduceMotion) {
  // Use instant transitions
} else {
  // Use animations
}
```

---

## 9. iOS Checklist

### Before Every iOS Screen

- [ ] Using Theme.of(context).textTheme (Dynamic Type)
- [ ] Safe areas respected with SafeArea widget
- [ ] Navigation follows HIG (back gesture works)
- [ ] Tab bar items <= 5
- [ ] Touch targets >= 44pt
- [ ] Semantics on all interactive elements

### Before iOS Release

- [ ] Dark mode tested
- [ ] All text sizes tested (Accessibility Inspector)
- [ ] VoiceOver tested (enable in Settings)
- [ ] Edge swipe back works everywhere
- [ ] Keyboard avoidance implemented (resizeToAvoidBottomInset)
- [ ] Notch / Dynamic Island not obscuring content
- [ ] Home indicator area respected (SafeArea bottom)
- [ ] CupertinoWidget used for platform-specific controls

---

> **Remember:** iOS users have strong expectations from other iOS apps. Deviating from HIG patterns feels "broken" to them. When in doubt, use the native Flutter Cupertino variant.

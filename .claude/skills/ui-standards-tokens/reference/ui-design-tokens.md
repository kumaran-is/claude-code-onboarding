# UI Design Tokens

## Spacing Tokens
```dart
class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
  static const double xxl = 48;
}
```

## Radius Tokens
```dart
class AppRadius {
  static const double none = 0;
  static const double sm = 4;
  static const double md = 8;
  static const double lg = 16;
  static const double xl = 24;
  static const double full = 999;
}
```

## Size Tokens
```dart
class AppSize {
  static const double iconSm = 16;
  static const double icon = 24;
  static const double iconLg = 32;
  static const double touchTarget = 48;
  static const double avatar = 40;
  static const double avatarLg = 64;
}
```

## Theme Usage

### Colors
```dart
// Never
Color(0xFF2196F3)
Colors.blue

// Always
Theme.of(context).colorScheme.primary
Theme.of(context).colorScheme.onSurface
Theme.of(context).colorScheme.surfaceContainerHighest
```

### Typography
```dart
// Never
TextStyle(fontSize: 16, fontWeight: FontWeight.bold)

// Always
Theme.of(context).textTheme.titleMedium
Theme.of(context).textTheme.bodyLarge?.copyWith(
  fontWeight: FontWeight.bold,
)
```

## Responsive Breakpoints

| Breakpoint | Width | Layout |
|------------|-------|--------|
| Mobile | < 600px | Single column |
| Tablet | 600-1199px | Two columns |
| Desktop | >= 1200px | Multi-column |

```dart
class ResponsiveLayout extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 1200) {
          return DesktopLayout();
        } else if (constraints.maxWidth >= 600) {
          return TabletLayout();
        }
        return MobileLayout();
      },
    );
  }
}
```

---

## Design Token Taxonomy (7 Categories)

Each category is shown with Flutter (Dart) and Angular (CSS variables) equivalents.

### 1. Color Tokens (3-Tier Hierarchy)

```
Primitive → Semantic → Component
```

- **Flutter:** `ThemeData.colorScheme` exposes Material 3 color roles — `primary`, `onPrimary`, `secondary`, `surface`, `error`, `surfaceContainerHighest`, etc.
- **Angular/CSS:**
  ```css
  /* Primitive */
  --color-blue-500: #3B82F6;

  /* Semantic */
  --color-primary: var(--color-blue-500);

  /* Component */
  --button-bg-primary: var(--color-primary);
  ```
- **Rule:** NEVER use primitive colors directly in components — always go through the semantic layer.

### 2. Spacing Tokens

- **Flutter:** `AppSpacing.xs/sm/md/lg/xl/xxl` (see above). All values follow a 4px base scale.
- **Angular/CSS:**
  ```css
  /* Primitive */
  --space-1: 4px;
  --space-2: 8px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;

  /* Semantic */
  --spacing-sm: var(--space-2);
  --spacing-md: var(--space-4);
  --spacing-lg: var(--space-6);
  ```
  Tailwind mapping: `p-2` = 8px, `p-4` = 16px, `p-6` = 24px.

### 3. Typography Tokens

- **Flutter:** `Theme.of(context).textTheme.*` — 15 roles from `displayLarge` down to `labelSmall`. Never use raw `TextStyle(fontSize: ...)`.
- **Angular/CSS:**
  ```css
  --font-sans: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;
  --font-size-xl: 1.25rem;
  --font-weight-normal: 400;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;
  ```
  Never use hardcoded `px` font sizes in Angular component CSS.

### 4. Border & Radius Tokens

- **Flutter:** `AppRadius.sm/md/lg/xl/full` (see above).
- **Angular/CSS:**
  ```css
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;
  ```
  daisyUI mapping: `rounded-sm`, `rounded-md`, `rounded-lg`, `rounded-full`.

### 5. Shadow Tokens

- **Flutter:** `Theme.of(context).cardTheme.elevation` for card elevation, or `BoxShadow` via `ThemeData` extensions. Never hardcode `BoxShadow` values inline.
- **Angular/CSS:**
  ```css
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px rgb(0 0 0 / 0.1);
  --shadow-focus-primary: 0 0 0 3px var(--color-primary);
  ```
  daisyUI utilities: `shadow-sm`, `shadow-md`, `shadow-xl`.

### 6. Motion Tokens

- **Flutter:**
  ```dart
  const Duration fast   = Duration(milliseconds: 150);
  const Duration normal = Duration(milliseconds: 200);
  const Duration slow   = Duration(milliseconds: 300);
  ```
  Always respect `MediaQuery.of(context).disableAnimations` — skip or shorten animations when true.
- **Angular/CSS:**
  ```css
  --duration-fast: 150ms;
  --duration-normal: 200ms;
  --duration-slow: 300ms;
  --ease-out: cubic-bezier(0, 0, 0.2, 1);

  @media (prefers-reduced-motion: reduce) {
    --duration-fast: 0ms;
    --duration-normal: 0ms;
    --duration-slow: 0ms;
  }
  ```

### 7. Z-Index Tokens (Angular Only)

Flutter uses `Stack` and `Overlay` for layering — there are no z-index tokens.

```css
--z-dropdown:       1000;
--z-modal-backdrop: 1040;
--z-modal:          1050;
--z-tooltip:        1070;
```

---

## Token Naming Convention

Component token format (both platforms):

```
{component}-{property}-{variant?}-{state?}
```

| CSS Variable | Flutter equivalent |
|---|---|
| `--button-bg-primary` | `colorScheme.primary` |
| `--button-bg-primary-hover` | `colorScheme.primary.withValues(alpha: 0.9)` |
| `--input-border-color-focus` | `colorScheme.primary` |
| `--card-surface` | `colorScheme.surfaceContainerHighest` |

---

## Theme Switching

### Angular (CSS custom properties)

```css
:root {
  --color-primary: #3B82F6;
  --color-background: #FFFFFF;
}

:root[data-theme="dark"] {
  --color-primary: #60A5FA;
  --color-background: #111827;
}
```

### Flutter (ThemeData / brightness)

```dart
MaterialApp(
  themeMode: ThemeMode.system, // or .light / .dark
  theme: ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: Colors.blue,
      brightness: Brightness.light,
    ),
  ),
  darkTheme: ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: Colors.blue,
      brightness: Brightness.dark,
    ),
  ),
)
```

---

## Theme Wiring Checklist — A Token That Reaches No Surface Is Not a Token

- Every token family must be consumed by the matching `ThemeData` sub-theme (`dialogTheme`, `inputDecorationTheme`, `snackBarTheme`, `bottomSheetTheme`, `cardTheme`, `appBarTheme`, button themes). An omitted sub-theme silently hands the surface back to Material defaults (e.g. the default dialog radius).
- In a theme, use the semantic alias (`radius.input`, `radius.dialog`), not a foundation step (`radius.medium`).
- Several theme text-style slots (e.g. `snackBarTheme.contentTextStyle`) replace Material's default rather than merge. A colour-only `TextStyle(color: ...)` there drops the type scale; build from `textTheme.<role>!.copyWith(...)`. Verify per slot against the SDK docs.
- Pin the wiring with a theme test that asserts the rendered property equals the token (never a literal) in light and dark, at a compact and a wide width.
- One canonical scale per token family. Never add a duplicate under another name or keep a "legacy" scale beside the canonical one; add the new token, migrate every caller and delete the old one in the same change.

## Semantic Colour, Shadow and Font Rules

- Use the scheme's error role for system/validation errors. Business-negative outcomes (overdue, declined) use a separate semantic token if the theme defines one. A neutral state (inactive, vacant) is neutral, not red.
- Amounts default to the normal on-surface colour; use positive/negative only when the meaning changes.
- Do not branch on `Theme.of(context).brightness` for colour values; tokens already resolve per theme. The one sanctioned branch is a map basemap style, at the component boundary.
- Chrome drawn over a photo, map or scrim uses a theme-invariant "on-scrim" colour; a normal `on-surface` role flips dark and vanishes on black.
- Dark theme: small-blur shadows are invisible on dark/OLED backgrounds. Define a floor (for example card blur >= 24, elevated >= 32) and assert it in the theme test.
- Fonts bundled in a separate package: every `TextStyle`/`TextTheme.apply` that sets `fontFamily` must also pass `package: '<pkg>'`, or the platform font renders silently (build green, typography wrong). Do not redeclare fonts in app pubspecs.
- Icons: wrap them in one app-level icon widget and one icon-button that guarantees a 48x48 hit area and requires a semantics label. Use "filled" weight only for active/selected states, and check a new glyph's fill variant on a device (regular and fill fonts can disagree at a codepoint).

## Accessibility: WCAG Contrast Requirements

| Context | Minimum ratio |
|---|---|
| Normal text (< 18px or < 14px bold) | 4.5:1 |
| Large text (>= 18px, or >= 14px bold) | 3:1 |
| UI components (buttons, inputs, focus rings) | 3:1 |
| High-contrast theme target (WCAG AAA) | 7:1 |

Flutter: `ColorScheme.fromSeed` generates Material 3 tonal palettes designed to meet WCAG AA by default. Do not override role colors with arbitrary hex values — doing so breaks the contrast guarantees.

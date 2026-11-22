# Flutter Premium Design & Polish Templates

Visual polish patterns for modern Flutter (2025/2026) — glassmorphism, premium cards, theming, and gradient accents.

> Radii, alphas and sizes below are literal for readability. In a project with design tokens, replace them with token constants (see [ui-design-tokens.md](../../ui-standards-tokens/reference/ui-design-tokens.md)). `Color.withOpacity` is deprecated (precision loss); use `withValues(alpha: ...)`. Restraint beats effects: use glass/gradients sparingly (at most one gradient surface per screen) and never as the only carrier of information.

## Glassmorphism with BackdropFilter

```dart
class GlassCard extends StatelessWidget {
  final Widget child;
  final double blur;
  final double opacity;

  const GlassCard({
    super.key,
    required this.child,
    this.blur = 10,
    this.opacity = 0.1,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: Container(
          decoration: BoxDecoration(
            color: colorScheme.surface.withValues(alpha: opacity),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: colorScheme.outline.withValues(alpha: 0.2),
            ),
          ),
          child: child,
        ),
      ),
    );
  }
}
```

## Modern Card Styling

```dart
class PremiumCard extends StatelessWidget {
  final Widget child;
  final bool isPremium;

  const PremiumCard({
    super.key,
    required this.child,
    this.isPremium = false,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(
        color: colorScheme.surface,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withValues(alpha: 0.08),
            blurRadius: 24,
            offset: const Offset(0, 8),
          ),
        ],
        border: isPremium
            ? Border.all(
                color: colorScheme.primary.withValues(alpha: 0.3),
                width: 1.5,
              )
            : null,
      ),
      child: Stack(
        children: [
          Padding(
            padding: const EdgeInsets.all(20),
            child: child,
          ),
          if (isPremium)
            Positioned(
              top: 12,
              right: 12,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      colorScheme.primary,
                      colorScheme.tertiary,
                    ],
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  'PRO',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: colorScheme.onPrimary,
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
```

## Dark/Light Theme with ThemeExtension

```dart
// Custom theme extension for app-specific colors
@immutable
class AppColors extends ThemeExtension<AppColors> {
  final Color success;
  final Color warning;
  final Color cardGradientStart;
  final Color cardGradientEnd;

  const AppColors({
    required this.success,
    required this.warning,
    required this.cardGradientStart,
    required this.cardGradientEnd,
  });

  @override
  AppColors copyWith({
    Color? success,
    Color? warning,
    Color? cardGradientStart,
    Color? cardGradientEnd,
  }) {
    return AppColors(
      success: success ?? this.success,
      warning: warning ?? this.warning,
      cardGradientStart: cardGradientStart ?? this.cardGradientStart,
      cardGradientEnd: cardGradientEnd ?? this.cardGradientEnd,
    );
  }

  @override
  AppColors lerp(covariant AppColors? other, double t) {
    if (other == null) return this;
    return AppColors(
      success: Color.lerp(success, other.success, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      cardGradientStart: Color.lerp(cardGradientStart, other.cardGradientStart, t)!,
      cardGradientEnd: Color.lerp(cardGradientEnd, other.cardGradientEnd, t)!,
    );
  }

  static const light = AppColors(
    success: Color(0xFF2E7D32),
    warning: Color(0xFFF57F17),
    cardGradientStart: Color(0xFF6366F1),
    cardGradientEnd: Color(0xFF8B5CF6),
  );

  static const dark = AppColors(
    success: Color(0xFF66BB6A),
    warning: Color(0xFFFFD54F),
    cardGradientStart: Color(0xFF818CF8),
    cardGradientEnd: Color(0xFFA78BFA),
  );
}

// Register in theme
ThemeData lightTheme() => ThemeData(
  colorScheme: ColorScheme.fromSeed(
    seedColor: const Color(0xFF6366F1),
    brightness: Brightness.light,
  ),
  extensions: const [AppColors.light],
);

ThemeData darkTheme() => ThemeData(
  colorScheme: ColorScheme.fromSeed(
    seedColor: const Color(0xFF6366F1),
    brightness: Brightness.dark,
  ),
  extensions: const [AppColors.dark],
);

// Usage
final appColors = Theme.of(context).extension<AppColors>()!;
Container(color: appColors.success)
```

## Gradient Accent Decorations

```dart
// Gradient app bar or header
Container(
  decoration: BoxDecoration(
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [
        Theme.of(context).colorScheme.primary,
        Theme.of(context).colorScheme.tertiary,
      ],
    ),
    borderRadius: const BorderRadius.vertical(bottom: Radius.circular(24)),
  ),
  padding: const EdgeInsets.fromLTRB(24, 60, 24, 32),
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        'Good Morning',
        style: Theme.of(context).textTheme.headlineMedium?.copyWith(
              color: Theme.of(context).colorScheme.onPrimary,
              fontWeight: FontWeight.bold,
            ),
      ),
    ],
  ),
)
```

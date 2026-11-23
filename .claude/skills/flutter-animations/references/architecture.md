# Architecture — Enterprise Flutter Animation Service Layer

## Table of Contents
1. [Full Directory Structure](#1-full-directory-structure)
2. [DI Wiring (get_it / Riverpod)](#2-di-wiring)
3. [AnimationService — Unified Facade](#3-animationservice--unified-facade)
4. [AnimationPlaceholder Widget](#4-animationplaceholder-widget)
5. [Accessibility — Reduce Motion](#5-accessibility--reduce-motion)
6. [Typed Asset Constants](#6-typed-asset-constants)
7. [pubspec.yaml Setup](#7-pubspecyaml-setup)
8. [CI/CD Size Checks](#8-cicd-size-checks)
9. [Code Review Checklist](#9-code-review-checklist)

---

## 1. Full Directory Structure

```
lib/
+-- core/
|   +-- animations/
|       +-- animation_assets.dart          # Typed asset path constants
|       +-- animation_preloader.dart       # Startup preloader (Rive + Lottie)
|       +-- animation_service.dart         # Unified facade for DI
|       +-- rive_file_cache.dart           # Decode-once Rive File cache
|       +-- lottie_cache_manager.dart      # Composition cache singleton
+-- widgets/
|   +-- animations/
|       +-- rive_widget.dart               # Reusable Rive wrapper
|       +-- lottie_widget.dart             # Reusable Lottie wrappers (loop/once)
|       +-- animation_placeholder.dart     # Shimmer shown while loading
|       +-- safe_animation.dart            # Error-boundary animation widget

assets/
+-- rive/
|   +-- auth_flow.riv
|   +-- progress_ring.riv
|   +-- toggle.riv
+-- lottie/
    +-- splash_logo.lottie
    +-- empty_state.lottie
    +-- success_check.lottie
    +-- skeleton.lottie
```

---

## 2. DI Wiring

### get_it
```dart
// lib/core/di/service_locator.dart
import 'package:get_it/get_it.dart';

final sl = GetIt.instance;

Future<void> configureDependencies() async {
  sl.registerSingleton<LottieCacheManager>(LottieCacheManager.instance);
  sl.registerSingleton<RivePreloader>(RivePreloader.instance);
  sl.registerSingleton<AnimationService>(
    AnimationService(
      rivePreloader: sl<RivePreloader>(),
      lottieCacheManager: sl<LottieCacheManager>(),
    ),
  );
  await sl<AnimationService>().preloadAll();
}
```

### Riverpod
```dart
// lib/core/animations/animation_providers.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';

final animationServiceProvider = Provider<AnimationService>((ref) {
  return AnimationService(
    rivePreloader: RivePreloader.instance,
    lottieCacheManager: LottieCacheManager.instance,
  );
});

final animationPreloadProvider = FutureProvider<void>((ref) async {
  await ref.read(animationServiceProvider).preloadAll();
});
```

---

## 3. AnimationService — Unified Facade

```dart
// lib/core/animations/animation_service.dart

class AnimationService {
  final RivePreloader rivePreloader;
  final LottieCacheManager lottieCacheManager;

  const AnimationService({
    required this.rivePreloader,
    required this.lottieCacheManager,
  });

  /// Preload all production animation assets.
  /// Call from main() — handles RiveNative.init() internally.
  Future<void> preloadAll() async {
    await RiveNative.init();
    await Future.wait([
      rivePreloader.preloadAll(),
      lottieCacheManager.preloadAll([
        AnimationAssets.splashLogo,
        AnimationAssets.emptyState,
        AnimationAssets.successCheck,
        AnimationAssets.skeleton,
      ]),
    ]);
  }

  bool get isReady =>
      rivePreloader.isAllLoaded && lottieCacheManager.isAllLoaded;
}
```

---

## 4. AnimationPlaceholder Widget

Show while compositions load. Uses ThemeData colorScheme tokens — no hardcoded colors.

```dart
// lib/widgets/animations/animation_placeholder.dart
import 'package:material_ui/material_ui.dart';

class AnimationPlaceholder extends StatelessWidget {
  final double width;
  final double height;
  final BorderRadius borderRadius;

  const AnimationPlaceholder({
    super.key,
    this.width = 200,
    this.height = 200,
    this.borderRadius = const BorderRadius.all(Radius.circular(12)),
  });

  @override
  Widget build(BuildContext context) {
    return _ShimmerBox(
      width: width,
      height: height,
      borderRadius: borderRadius,
    );
  }
}

class _ShimmerBox extends StatefulWidget {
  final double width;
  final double height;
  final BorderRadius borderRadius;

  const _ShimmerBox({
    required this.width,
    required this.height,
    required this.borderRadius,
  });

  @override
  State<_ShimmerBox> createState() => _ShimmerBoxState();
}

class _ShimmerBoxState extends State<_ShimmerBox>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _shimmer;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _shimmer = CurvedAnimation(parent: _controller, curve: Curves.easeInOut);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Reduced motion: a static placeholder, no shimmer loop.
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller.stop();
    } else if (!_controller.isAnimating) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return AnimatedBuilder(
      animation: _shimmer,
      builder: (context, child) {
        return Container(
          width: widget.width,
          height: widget.height,
          decoration: BoxDecoration(
            borderRadius: widget.borderRadius,
            color: Color.lerp(
              colorScheme.surfaceContainerHighest,
              colorScheme.surfaceContainerHigh,
              _shimmer.value,
            ),
          ),
        );
      },
    );
  }
}
```

---

## 5. Accessibility — Reduce Motion

Every animation widget must check `MediaQuery.disableAnimationsOf(context)`.

### Reduce-motion behaviour by type:

| Animation Type | Reduce-motion Behaviour |
|---|---|
| Looping decorative (Lottie) | Pause at frame 0 (static image) |
| Play-once confirmation | Show final frame immediately |
| Rive interactive (button/toggle) | Show static fallback widget |
| Rive state machine (auth/progress) | Swap to plain `CircularProgressIndicator` |
| Skeleton loader | Replace with `Container` of same dimensions |

### Helper mixin:
```dart
mixin ReducedMotionMixin<T extends StatefulWidget> on State<T> {
  bool get reduceMotion => MediaQuery.disableAnimationsOf(context);

  Widget buildWithMotionCheck({
    required Widget animated,
    required Widget reduced,
  }) {
    return reduceMotion ? reduced : animated;
  }
}
```

---

## 6. Typed Asset Constants

```dart
// lib/core/animations/animation_assets.dart
abstract final class AnimationAssets {
  // Rive (.riv)
  static const String toggle       = 'assets/rive/toggle.riv';
  static const String authFlow     = 'assets/rive/auth_flow.riv';
  static const String progressRing = 'assets/rive/progress_ring.riv';
  static const String onboarding   = 'assets/rive/onboarding.riv';
  static const String bottomNav    = 'assets/rive/bottom_nav.riv';

  // Lottie (.lottie / .json)
  static const String splashLogo   = 'assets/lottie/splash_logo.lottie';
  static const String emptyState   = 'assets/lottie/empty_state.lottie';
  static const String successCheck = 'assets/lottie/success_check.lottie';
  static const String errorShake   = 'assets/lottie/error_shake.lottie';
  static const String skeleton     = 'assets/lottie/skeleton.lottie';
  static const String confetti     = 'assets/lottie/confetti.lottie';
}
```

---

## 7. pubspec.yaml Setup

```yaml
dependencies:
  flutter:
    sdk: flutter
  material_ui: 1.11.1
  rive: 0.14.11
  lottie: 3.8.2

flutter:
  uses-material-design: true
  assets:
    - assets/rive/
    - assets/lottie/
```

**Note:** Trailing slash on asset folder path includes all files in the directory automatically.

---

## 8. CI/CD Size Checks

Add to `.github/workflows/flutter.yml`:

```yaml
- name: Check Rive asset sizes
  run: |
    OVERSIZED=$(find assets/rive -name "*.riv" -size +500k)
    if [ -n "$OVERSIZED" ]; then
      echo "Rive files exceed 500 KB limit:"
      echo "$OVERSIZED"
      exit 1
    fi
    echo "All .riv files within size limit"

- name: Check Lottie asset sizes
  run: |
    OVERSIZED=$(find assets/lottie -name "*.json" -size +300k)
    if [ -n "$OVERSIZED" ]; then
      echo "Lottie JSON files exceed 300 KB limit. Convert to .lottie format:"
      echo "$OVERSIZED"
      exit 1
    fi
    echo "All Lottie files within size limit"
```

---

## 9. Code Review Checklist

Use as PR checklist for any animation PR:

### Correctness
- [ ] Engine choice follows the Rive/Lottie decision table
- [ ] Correct artboard and state machine names (verified against Rive file)
- [ ] `FileLoader` disposed by the widget that created it; the controller and view-model instance created by `RiveWidgetBuilder` are not disposed again
- [ ] `AnimationController` (Lottie) disposed
- [ ] Asset paths use `AnimationAssets` constants — no raw strings
- [ ] `RiveWidgetBuilder` + Data Binding used (no legacy `RiveAnimation.asset`, no deprecated `stateMachine.boolean/number/trigger` inputs)

### Performance
- [ ] `await RiveNative.init()` in `main()` before `runApp`
- [ ] Assets preloaded before first render
- [ ] Lottie loops use `RenderCache.drawingCommands` (`raster` only for very short, small animations)
- [ ] Rive renderer declared explicitly
- [ ] Lottie compositions cached via `LottieCacheManager` in list views
- [ ] 3+ Rive widgets wrapped in `RivePanel(useSharedTexture: true)`

### Accessibility
- [ ] `Semantics` label on all animation containers
- [ ] Reduce-motion branch implemented per decision table
- [ ] Static fallback widget provided for all Rive interactive animations
- [ ] Colours passed explicitly (view-model colour / `ValueDelegate.color`); neither engine reads the app theme

### Robustness
- [ ] `RiveWidgetBuilder` `RiveFailed` state shows fallback widget
- [ ] Network animations have placeholder + error states
- [ ] Lottie loads set `errorBuilder` (visible fallback, failure reported)

### Assets
- [ ] `.riv` size <= 500 KB (CI enforced)
- [ ] Lottie assets in `.lottie` format
- [ ] Lottie JSON size <= 300 KB (CI enforced)
- [ ] Assets declared in `pubspec.yaml`

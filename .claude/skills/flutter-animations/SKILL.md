---
name: flutter-animations
description: "Enterprise Flutter animation skill — Rive + Lottie dual-engine strategy for production mobile apps. Use when adding animations to Flutter, asking about Rive, Lottie, animated UI components, motion design, interactive states, loading indicators, onboarding flows, micro-interactions, character animations, splash screens, empty states, or any animated widget. Load BEFORE writing any Flutter animation code — enforces correct engine choice, architecture patterns, performance constraints, and accessibility."
risk: low
source: community (adapted for workspace)
date_added: "2026-03-15"
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: animation, Rive, Lottie, animated widget, motion design, loading indicator, onboarding animation, micro-interaction, character animation, splash screen, empty state animation, interactive toggle, progress ring, skeleton loader, confetti, state machine animation
  related-skills: flutter-mobile, mobile-design, riverpod-patterns, ui-standards-tokens, accessibility-audit
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-03-15"
---

## Iron Law

**BEFORE the engine choice, pass the "Before you animate" gates below. Then resolve engine choice (Rive vs Lottie) before writing a single line of animation code — use the decision table. Then read the relevant reference file. Never hardcode asset paths.**

# Flutter Animations — Rive + Lottie Dual-Engine

## Before you animate — decide in this order

1. **Should it move at all?** Only if motion measurably improves feedback, comprehension, continuity, state clarity or progress. "No animation" is a valid, reportable decision.
2. **What real event drives it?** Animate semantic changes (a status transition, a genuinely new item). Never animate framework mechanics: rebuilds, state invalidation, cache/local-DB hydration, background refresh, pagination, sort/filter, navigation restoration. Test: if equal data arriving again would re-animate, the trigger is wrong.
3. **List stability.** Existing rows stay put on load, refresh, sort, filter and return. Only a real insertion, removal or user-triggered row transition may move. Staggered entrances are for a first, deliberate reveal only.
4. **Engine.** Flutter native by default (implicit animations, `AnimatedSwitcher`, transitions); designer-owned decorative sequence → Lottie; data/input-driven multi-state → Rive. When unsure, default down that list. Use shared duration/curve tokens, not literals, if the project defines them.
5. **Reduced motion** (`MediaQuery.disableAnimationsOf(context)`): replace movement, never information or function.

| Normal | Reduced motion |
|---|---|
| Slide / scale | Instant state change, or a minimal opacity change |
| Shimmer | Static placeholder |
| Lottie / Rive | Static frame or icon + text |
| `Hero` | Standard route transition |
| Animated insertion | Immediate insertion, or a static highlight |
| Looping decoration / pulse | Static frame |

   Never pass a zero `Duration` to `AnimatedSize`/implicit animations that restart a controller during layout as a "reduced motion" shortcut — return the child unwrapped instead.
6. **Additive only.** Motion is never the sole signal of success, failure, progress, offline or sync state; pair it with text, an icon, or `Semantics`. Announce on the semantic event, not on animation completion; keep touch targets >= 48dp mid-transition.
7. **Lifecycle proportional to cost.** Scrutinise loops, motion inside scrolling rows, custom controllers, complex `Hero`. A press ripple or `AnimatedOpacity` needs no lifecycle machinery. Dispose every controller/listener you create; profile before optimising.
8. **`Hero` only if** the element is unique, visually stable, present in both screens, the same object, and genuinely improved by continuity. Tags must be unique across a list.
9. **No casual new animation dependency.** Adding a package is an explicit architecture decision, not a side effect of building a screen.

### Testing motion

Assert *state → visible result*, not millisecond timings. Cover: reduced-motion fallback renders and keeps the meaning readable (wrap the widget in `MediaQuery(data: const MediaQueryData(disableAnimations: true), child: ...)`); two fast taps do not double-trigger; equal data re-delivered causes no animation; cache-restored content appears without entrance motion; controllers dispose with no "ticker active when disposed"; asset-load failure shows the fallback. Use `pump(duration)` on infinite loops — `pumpAndSettle` never settles. Positive-control each test: break the behaviour on purpose and confirm it fails for the stated reason (see [flutter-testing-traps.md](../flutter-mobile/reference/flutter-testing-traps.md)).

## Engine Decision (Always resolve first)

| Use Case | Engine | Why |
|---|---|---|
| Interactive buttons, toggles, tab bars | **Rive** | State machines, pointer input |
| Onboarding with user-driven progression | **Rive** | Inputs map to gestures |
| Progress indicators tied to real data | **Rive** | Data binding at runtime |
| Auth flows (loading → success → error) | **Rive** | Multi-state without code branching |
| Games, character animations | **Rive** | 60fps, blending, bone rigs |
| Splash / intro screens (play-once) | **Lottie** | AF export, decorative |
| Empty states, "no results" illustrations | **Lottie** | Designer-owned, static loop |
| Celebration / confetti effects | **Lottie** | After Effects shine |
| Icon animations (email sent, checkmark) | **Lottie** | Simple, small JSON |
| Skeleton loaders with fixed timing | **Lottie** | Predictable, no interaction |

**If unsure:** "Does this animation need to respond to app state or user input?" Yes → Rive. No → Lottie.

---

## Package Versions

```yaml
dependencies:
  rive: 0.14.11          # rive.app verified publisher (pub.dev, checked)
  lottie: 3.8.2          # xaha.dev verified publisher (pub.dev, checked)
```

---

## Architecture

Never put animation controller logic directly in a screen widget. Use service + widget separation.

```
lib/
+-- core/
|   +-- animations/
|       +-- animation_assets.dart          # Typed asset path constants
|       +-- animation_preloader.dart       # Startup preloader (Rive + Lottie)
|       +-- animation_service.dart         # Unified facade for DI
|       +-- rive_controller_factory.dart   # State machine controller factory
|       +-- lottie_cache_manager.dart      # Composition cache singleton
+-- widgets/
|   +-- animations/
|       +-- rive_widget.dart               # Reusable Rive wrapper
|       +-- lottie_widget.dart             # Reusable Lottie wrappers (loop/once)
|       +-- animation_placeholder.dart     # Shimmer shown while loading
|       +-- safe_animation.dart            # Error-boundary animation widget
+-- assets/
    +-- rive/      # .riv files (< 500 KB each)
    +-- lottie/    # .json / .lottie files (< 300 KB each)
```

---

## Quick Rules (always apply)

1. **Preload on app start** — never lazy-load `.riv` or `.json` at first render
2. **Call `await RiveNative.init()` in `main()`** before `runApp`
3. **Dispose every controller** — `FileLoader`, `RiveWidgetController`, `AnimationController` must all be disposed
4. **Use `renderCache: RenderCache.raster`** for all Lottie loops
5. **Choose renderer explicitly** — `Factory.rive` for complex vector; `Factory.flutter` for simple UI
6. **Never hardcode asset paths** — use typed `AnimationAssets` constants class
7. **Wrap in error boundary** — `RiveWidgetBuilder` loading/failed states for Rive; try/catch for Lottie
8. **Semantic labels on all animations** — `Semantics(label: '...', child: ...)`
9. **Reduce motion** — check `MediaQuery.disableAnimationsOf(context)` and skip/pause the motion (never the function)
10. **Test with `flutter_test`** — pump and verify state transitions; mock asset loading
11. **Size budget** — `.riv` < 500 KB; `.json` < 300 KB; prefer `.lottie` (dotLottie zip) over raw JSON
12. **Multiple Rive widgets on screen** — wrap in `RivePanel(useSharedTexture: true)` for GPU performance

---

## Minimal Working Examples

### Rive — Interactive Toggle (modern API, rive 0.14.x)

> NOTE: `RiveAnimation.asset` + `StateMachineController.fromArtboard` is the LEGACY API.
> Use `FileLoader` + `RiveWidgetController` + `RiveWidgetBuilder` for all new code.

```dart
import 'package:flutter/material.dart';
import 'package:rive/rive.dart';

class AnimatedToggle extends StatefulWidget {
  final ValueChanged<bool> onChanged;
  const AnimatedToggle({super.key, required this.onChanged});

  @override
  State<AnimatedToggle> createState() => _AnimatedToggleState();
}

class _AnimatedToggleState extends State<AnimatedToggle> {
  late final FileLoader _fileLoader;
  late final RiveWidgetController _controller;
  SMIBool? _isOnInput;
  bool _isOn = false;

  @override
  void initState() {
    super.initState();
    _fileLoader = FileLoader.fromAsset(
      AnimationAssets.toggle,
      riveFactory: Factory.rive,
    );
    _controller = RiveWidgetController(
      _fileLoader,
      artboardSelector: ArtboardSelector.byName('ToggleArtboard'),
      stateMachineSelector: StateMachineSelector.byName('Toggle'),
    );
    _isOnInput =
        _controller.stateMachine('Toggle').input<bool>('isOn') as SMIBool?;
  }

  @override
  void dispose() {
    _fileLoader.dispose();
    _controller.dispose();
    super.dispose();
  }

  void _toggle() {
    final newValue = !_isOn;
    setState(() => _isOn = newValue);
    _isOnInput?.change(newValue);
    widget.onChanged(newValue);
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    return Semantics(
      label: 'Toggle button',
      button: true,
      child: GestureDetector(
        onTap: _toggle, // reduced motion removes movement, never the control
        child: reduceMotion
            ? _StaticToggleFallback(isOn: _isOn)
            : SizedBox(
                width: 64,
                height: 32,
                child: RiveWidgetBuilder(
                  fileLoader: _fileLoader,
                  builder: (context, state) => switch (state) {
                    RiveLoading() => const Center(
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    RiveFailed() => const Icon(
                        Icons.error_outline,
                        color: Colors.red,
                        size: 20,
                      ),
                    RiveLoaded() => RiveWidget(
                        controller: _controller,
                        fit: BoxFit.contain,
                      ),
                  },
                ),
              ),
      ),
    );
  }
}
```

### Lottie — Cached Empty State

```dart
import 'package:flutter/material.dart';
import 'package:lottie/lottie.dart';

class EmptyStateAnimation extends StatefulWidget {
  final String message;
  const EmptyStateAnimation({super.key, required this.message});

  @override
  State<EmptyStateAnimation> createState() => _EmptyStateAnimationState();
}

class _EmptyStateAnimationState extends State<EmptyStateAnimation>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          label: 'Empty state illustration',
          child: Lottie.asset(
            AnimationAssets.emptyState,
            controller: reduceMotion ? (_controller..stop()) : _controller,
            renderCache: RenderCache.raster,
            frameRate: FrameRate.composition,
            width: 240,
            height: 240,
            fit: BoxFit.contain,
            onLoaded: (composition) {
              if (!reduceMotion) {
                _controller
                  ..duration = composition.duration
                  ..repeat();
              }
            },
          ),
        ),
        const SizedBox(height: 16),
        Text(widget.message, style: Theme.of(context).textTheme.bodyLarge),
      ],
    );
  }
}
```

### Typed Asset Constants

```dart
// lib/core/animations/animation_assets.dart
abstract final class AnimationAssets {
  // Rive
  static const String toggle       = 'assets/rive/toggle.riv';
  static const String authFlow     = 'assets/rive/auth_flow.riv';
  static const String progressRing = 'assets/rive/progress_ring.riv';
  static const String onboarding   = 'assets/rive/onboarding.riv';
  static const String bottomNav    = 'assets/rive/bottom_nav.riv';

  // Lottie
  static const String splashLogo   = 'assets/lottie/splash_logo.lottie';
  static const String emptyState   = 'assets/lottie/empty_state.lottie';
  static const String successCheck = 'assets/lottie/success_check.lottie';
  static const String errorShake   = 'assets/lottie/error_shake.lottie';
  static const String skeleton     = 'assets/lottie/skeleton.lottie';
  static const String confetti     = 'assets/lottie/confetti.lottie';
}
```

### pubspec.yaml Asset Registration

```yaml
flutter:
  assets:
    - assets/rive/
    - assets/lottie/
```

---

## When to Read Reference Files

- Building a Rive state machine, data binding, or multi-artboard flow → read `references/rive.md`
- Building a Lottie scene with dynamic color, runtime text, or performance tuning → read `references/lottie.md`
- Setting up service layer, DI, preloading, CI/CD size checks, or code review checklist → read `references/architecture.md`

---

## Related Skills

- `flutter-mobile` — Flutter 3.41.x screen patterns, Riverpod, Freezed. Load alongside for full feature context.
- `mobile-design` — Load BEFORE this skill for touch psychology and MFRI scoring
- `riverpod-patterns` — Wire animation state to Riverpod providers
- `ui-standards-tokens` — ThemeData tokens for static fallback widgets
- `accessibility-audit` — WCAG 2.2 AA audit including reduce-motion compliance

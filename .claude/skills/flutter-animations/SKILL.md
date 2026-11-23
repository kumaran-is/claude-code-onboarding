---
name: flutter-animations
description: "Flutter animation with a Rive + Lottie dual-engine strategy: engine choice, architecture, performance and reduced-motion accessibility for loaders, onboarding, micro-interactions, splash and empty states. Load before writing Flutter animation code. Not for web animation performance (fixing-motion-performance)."
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
last-reviewed: "2026-11-23"
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
  material_ui: 1.11.1    # Flutter >= 3.47: replaces package:flutter/material.dart
  rive: 0.14.11          # rive.app verified publisher; native runtime rive_native 0.1.11
  lottie: 3.8.2          # xaha.dev verified publisher; needs Flutter >= 3.47
```

Resolved together on Flutter 3.50.1 / Dart 3.14.0 (`flutter pub get` exit 0, `flutter analyze` 0 issues). Package source on 3.50.1: lottie 3.8.2 imports only `flutter/widgets.dart`; rive 0.14.11 still imports the deprecated `flutter/material.dart` (one internal `CircularProgressIndicator`) but reads no theme. Neither picks up app colours on its own: pass them explicitly (Rive view-model colour properties, Lottie `ValueDelegate.color`). Under a `material_ui` app, a legacy `Theme.of()` returns the default light theme (widget-tested), which matters for legacy-Material plugins that do read the theme (for example `printing`'s `PdfPreview`).

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
|       +-- rive_file_cache.dart           # Decode-once Rive File cache
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
3. **Dispose what you create** — your `FileLoader` and `AnimationController`; `RiveWidgetBuilder` disposes the `RiveWidgetController` and view-model instance it creates (do not dispose them twice)
4. **Lottie render cache** — `RenderCache.drawingCommands` for loops (caches per-frame pictures); `RenderCache.raster` only for very short, small animations (memory grows with frames × size)
5. **Choose renderer explicitly** — `Factory.rive` for complex vector; `Factory.flutter` for simple UI
6. **Never hardcode asset paths** — use typed `AnimationAssets` constants class
7. **Visible failure state** — `RiveWidgetBuilder` `RiveFailed()` branch + `onFailed` reporting for Rive; `errorBuilder` for Lottie
8. **Semantic labels on all animations** — `Semantics(label: '...', child: ...)`
9. **Reduce motion** — check `MediaQuery.disableAnimationsOf(context)` and skip/pause the motion (never the function)
10. **Test with `flutter_test`** — pump and verify state transitions; mock asset loading
11. **Size budget** — `.riv` < 500 KB; `.json` < 300 KB; prefer `.lottie` (dotLottie zip) over raw JSON
12. **Multiple Rive widgets on screen** — wrap in `RivePanel(useSharedTexture: true)` for GPU performance

---

## Minimal Working Examples

### Rive — Interactive Toggle (modern API, rive 0.14.x)

> `RiveAnimation.asset`, `StateMachineController.fromArtboard` and `SMIBool` do not exist in rive 0.14. State machine
> inputs (`stateMachine.boolean/number/trigger`) are `@Deprecated` in 0.14.11: drive the file through Data Binding
> (a view model property, here `isOn`). Compiled on Flutter 3.50.1 with zero analyzer issues.

```dart
import 'package:material_ui/material_ui.dart';
import 'package:rive/rive.dart';

/// Rive toggle driven by Data Binding (rive 0.14). The `.riv` file exposes a
/// view model with a boolean property `isOn` bound to its state machine.
class AnimatedToggle extends StatefulWidget {
  const AnimatedToggle({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  State<AnimatedToggle> createState() => _AnimatedToggleState();
}

class _AnimatedToggleState extends State<AnimatedToggle> {
  // The widget owns the FileLoader; RiveWidgetBuilder owns the controller
  // and view-model instance it creates and disposes them itself.
  late final FileLoader _fileLoader = FileLoader.fromAsset(
    AnimationAssets.toggle,
    riveFactory: Factory.rive,
  );
  ViewModelInstanceBoolean? _isOn;

  @override
  void didUpdateWidget(AnimatedToggle oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.value != oldWidget.value) _isOn?.value = widget.value;
  }

  @override
  void dispose() {
    _isOn = null;
    _fileLoader.dispose();
    super.dispose();
  }

  void _onLoaded(RiveLoaded state) {
    _isOn = state.viewModelInstance?.boolean('isOn');
    _isOn?.value = widget.value;
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    return Semantics(
      label: widget.label,
      toggled: widget.value,
      button: true,
      excludeSemantics: true,
      onTap: () => widget.onChanged(!widget.value),
      child: InkWell(
        onTap: () => widget.onChanged(!widget.value),
        child: SizedBox(
          width: 64,
          height: 48,
          // Reduced motion removes the movement, never the control.
          child: reduceMotion
              ? Switch(value: widget.value, onChanged: widget.onChanged)
              : RiveWidgetBuilder(
                  fileLoader: _fileLoader,
                  artboardSelector: ArtboardSelector.byName('Toggle'),
                  stateMachineSelector: StateMachineSelector.byName('Main'),
                  dataBind: DataBind.auto(),
                  onLoaded: _onLoaded,
                  onFailed: (error, stack) => FlutterError.reportError(
                    FlutterErrorDetails(
                      exception: error,
                      stack: stack,
                      library: 'rive',
                    ),
                  ),
                  builder: (context, state) => switch (state) {
                    RiveLoading() => const SizedBox.shrink(),
                    // Visible, working fallback: the switch still toggles.
                    RiveFailed() => Switch(
                      value: widget.value,
                      onChanged: widget.onChanged,
                    ),
                    RiveLoaded(:final controller) => RiveWidget(
                      controller: controller,
                      fit: Fit.contain,
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

`errorBuilder` shows a static icon when the asset is missing or corrupt (widget-tested on 3.50.1); playback starts and stops in `didChangeDependencies`, so reduced motion can change at runtime.

```dart
import 'package:lottie/lottie.dart';
import 'package:material_ui/material_ui.dart';

/// Decorative Lottie loop with a static reduced-motion frame. The message
/// carries the meaning; the illustration is excluded from semantics.
class EmptyStateAnimation extends StatefulWidget {
  const EmptyStateAnimation({super.key, required this.message});

  final String message;

  @override
  State<EmptyStateAnimation> createState() => _EmptyStateAnimationState();
}

class _EmptyStateAnimationState extends State<EmptyStateAnimation>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this);
  bool _loaded = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _syncPlayback();
  }

  // Start/stop outside build(): reduced motion can change at runtime.
  void _syncPlayback() {
    if (!_loaded) return;
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller.stop();
    } else if (!_controller.isAnimating) {
      _controller.repeat();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ExcludeSemantics(
          child: Lottie.asset(
            AnimationAssets
                .emptyState, // .lottie (dotLottie) decodes by default
            controller: _controller,
            width: 240,
            height: 240,
            fit: BoxFit.contain,
            // drawingCommands caches per-frame Pictures (CPU saving);
            // RenderCache.raster is for very short, small animations only.
            renderCache: RenderCache.drawingCommands,
            frameRate: FrameRate.composition,
            onLoaded: (composition) {
              _controller.duration = composition.duration;
              _loaded = true;
              _syncPlayback();
            },
            errorBuilder: (context, error, stack) => Icon(
              Icons.inbox_outlined,
              size: 96,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
        Text(widget.message, style: theme.textTheme.bodyLarge),
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

- `flutter-mobile` — Flutter 3.50.x screen patterns, Riverpod, Freezed. Load alongside for full feature context.
- `mobile-design` — Load BEFORE this skill for touch psychology and MFRI scoring
- `riverpod-patterns` — Wire animation state to Riverpod providers
- `ui-standards-tokens` — ThemeData tokens for static fallback widgets
- `accessibility-audit` — WCAG 2.2 AA audit including reduce-motion compliance

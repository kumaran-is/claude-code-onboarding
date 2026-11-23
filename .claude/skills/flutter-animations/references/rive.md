# Rive — Enterprise Flutter Reference

## Table of Contents
1. [Renderer Selection](#1-renderer-selection)
2. [State Machines](#2-state-machines--modern-api-rive-014x)
3. [Inputs — Bool, Number, Trigger](#3-inputs--bool-number-trigger)
4. [Data Binding](#4-data-binding)
5. [Multi-Artboard Strategy](#5-multi-artboard-strategy)
6. [Preloading & Caching](#6-preloading--caching)
7. [Error Handling](#7-error-handling)
8. [RiveNative.init()](#8-rivenativeinit)
9. [RivePanel — Shared Texture](#9-rivepanel--shared-texture)
10. [Testing](#10-testing)
11. [Performance Checklist](#11-performance-checklist)

---

## 1. Renderer Selection

Always declare the renderer explicitly. Never rely on defaults in production.

```dart
// Prefer Rive renderer for complex vector / gradients / bones
final riveFile = (await File.asset(
  'assets/rive/character.riv',
  riveFactory: Factory.rive,     // Rive's own renderer (recommended)
))!;

// Use Flutter renderer for simple UI glyphs (less overhead on simple shapes)
final simpleFile = (await File.asset(
  'assets/rive/icon.riv',
  riveFactory: Factory.flutter,
))!;
```

**Rule:** If your `.riv` file was built with gradient fills, procedural meshes, or bone rigs → `Factory.rive`.
For flat icon-level animations embedded in lists → `Factory.flutter`.

### Impeller Gotcha (iOS / future Android)
On Impeller-enabled devices, some Rive effects may render differently:
```dart
// Fallback check — add to your QA matrix
// flutter run --no-enable-impeller   <- Skia path for comparison
```
File Rive issues at github.com/rive-app/rive-flutter.

---

## 2. State Machines — Modern API (rive 0.14.x)

> **The `RiveAnimation` widget + `StateMachineController.fromArtboard` is the legacy API.**
> All new enterprise code must use `FileLoader` + `RiveWidgetController` + `RiveWidgetBuilder`.

### Modern Pattern — Full Widget

```dart
class RiveStateMachineWidget extends StatefulWidget {
  final String assetPath;
  final String artboardName;
  final String stateMachineName;

  const RiveStateMachineWidget({
    super.key,
    required this.assetPath,
    required this.artboardName,
    required this.stateMachineName,
  });

  @override
  State<RiveStateMachineWidget> createState() => _RiveStateMachineWidgetState();
}

class _RiveStateMachineWidgetState extends State<RiveStateMachineWidget> {
  late final FileLoader _fileLoader;
  late final RiveWidgetController _controller;

  @override
  void initState() {
    super.initState();
    _fileLoader = FileLoader.fromAsset(
      widget.assetPath,
      riveFactory: Factory.rive,
    );
    _controller = RiveWidgetController(
      _fileLoader,
      artboardSelector: ArtboardSelector.byName(widget.artboardName),
      stateMachineSelector: StateMachineSelector.byName(widget.stateMachineName),
    );
  }

  @override
  void dispose() {
    _fileLoader.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RiveWidgetBuilder(
      fileLoader: _fileLoader,
      builder: (context, state) => switch (state) {
        RiveLoading() => const AnimationPlaceholder(),
        RiveFailed(:final error) => _ErrorFallback(message: error.toString()),
        RiveLoaded() => RiveWidget(
            controller: _controller,
            fit: BoxFit.contain,
          ),
      },
    );
  }
}
```

### Legacy API — Migration Reference Only

```dart
// DO NOT USE IN NEW CODE — legacy API, kept for migration awareness only
void _onRiveInit(Artboard artboard) {
  final controller = StateMachineController.fromArtboard(artboard, 'StateMachineName');
  if (controller == null) return;
  artboard.addController(controller);  // Risk: can add duplicate controllers
}
// RiveAnimation.asset(path, stateMachines: ['name'], onInit: _onRiveInit)
```

---

## 3. Inputs — Bool, Number, Trigger

### Safe Input Access (modern controller)

```dart
// In initState after _controller is created:
final sm = _controller.stateMachine('Toggle');

final SMIBool?    isActive  = sm.input<bool>('isActive')   as SMIBool?;
final SMINumber?  progress  = sm.input<double>('progress') as SMINumber?;
final SMITrigger? tapEvent  = sm.input<bool>('onTap')      as SMITrigger?;

isActive?.change(true);
progress?.change(0.75);   // 0.0 to 1.0
tapEvent?.fire();
```

### Typed Input Helper Extension

```dart
extension RiveStateMachineExtension on StateMachine {
  SMIBool?    boolInput(String name)    => input<bool>(name)   as SMIBool?;
  SMINumber?  numberInput(String name)  => input<double>(name) as SMINumber?;
  SMITrigger? triggerInput(String name) => input<bool>(name)   as SMITrigger?;
}
```

### Connecting to App State (Riverpod pattern)

```dart
@override
void didUpdateWidget(covariant MyRiveWidget oldWidget) {
  super.didUpdateWidget(oldWidget);
  if (widget.loadingState != oldWidget.loadingState) {
    _syncState(widget.loadingState);
  }
}

void _syncState(LoadingState state) {
  switch (state) {
    case LoadingState.loading:
      _isLoading?.change(true);
      _isError?.change(false);
    case LoadingState.success:
      _isLoading?.change(false);
      _onSuccess?.fire();
    case LoadingState.error:
      _isLoading?.change(false);
      _isError?.change(true);
    case LoadingState.idle:
      _isLoading?.change(false);
      _isError?.change(false);
  }
}
```

---

## 4. Data Binding

Rive data binding (rive 0.14.x) allows direct wiring of Dart values to Rive viewmodel properties.
Prefer this over manual SMINumber updates for progress rings, charts, and real-time displays.

```dart
void _onRiveInit(Artboard artboard) {
  final controller = StateMachineController.fromArtboard(artboard, 'Main');
  if (controller == null) return;
  artboard.addController(controller);

  final vm = controller.viewModelInstance;
  vm?.getNumber('progress')?.change(0.0);
  _progressProperty = vm?.getNumber('progress');
}

void updateProgress(double value) {
  _progressProperty?.change(value.clamp(0.0, 1.0));
}
```

**Note:** Data binding is more efficient than polling SMINumber in an AnimationController.
Prefer it for any animation driven by live/streaming data.

---

## 5. Multi-Artboard Strategy

For large `.riv` files with multiple artboards (e.g., onboarding with 5 screens):

```dart
class OnboardingAnimation extends StatefulWidget {
  final int step;  // 0 to 4
  const OnboardingAnimation({super.key, required this.step});

  @override
  State<OnboardingAnimation> createState() => _OnboardingAnimationState();
}

class _OnboardingAnimationState extends State<OnboardingAnimation> {
  static const _artboards = [
    'Welcome', 'Features', 'Permissions', 'Profile', 'Done',
  ];

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 400),
      child: RiveAnimation.asset(
        AnimationAssets.onboarding,
        key: ValueKey(widget.step),
        artboard: _artboards[widget.step],
        stateMachines: const ['Main'],
        fit: BoxFit.contain,
      ),
    );
  }
}
```

**Why single `.riv` file for multiple artboards:**
- One asset load — cheaper on cold start
- Shared assets deduplicated by Rive runtime
- Simpler CI/CD version management

---

## 6. Preloading & Caching

Never let the first frame trigger an asset load. Preload at app startup.

```dart
// lib/core/animations/animation_preloader.dart
import 'package:flutter/services.dart';
import 'package:rive/rive.dart';

class RivePreloader {
  RivePreloader._();
  static final RivePreloader instance = RivePreloader._();

  final Map<String, RiveFile> _cache = {};
  bool get isAllLoaded => _expectedAssets.every(_cache.containsKey);

  Future<void> preloadAll() async {
    await Future.wait([
      _load(AnimationAssets.authFlow),
      _load(AnimationAssets.progressRing),
      _load(AnimationAssets.toggle),
    ]);
  }

  Future<void> _load(String assetPath) async {
    if (_cache.containsKey(assetPath)) return;
    final data = await rootBundle.load(assetPath);
    final file = RiveFile.import(data);
    _cache[assetPath] = file;
  }

  RiveFile get(String assetPath) {
    final file = _cache[assetPath];
    assert(file != null, '$assetPath was not preloaded. Call preloadAll() first.');
    return file!;
  }
}
```

---

## 7. Error Handling

```dart
// In your app setup — log Rive errors to crash analytics
void setupErrorHandling() {
  FlutterError.onError = (details) {
    if (details.exception is RiveException ||
        details.library?.contains('rive') == true) {
      FirebaseCrashlytics.instance.recordFlutterError(details);
    } else {
      FlutterError.presentError(details);
    }
  };
}
```

Always use `RiveWidgetBuilder` with explicit `RiveFailed` state — never let failures silently produce a blank widget.

---

## 8. RiveNative.init()

Required for `rive 0.14.x`. Must be called before `runApp`.

```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await RiveNative.init();                         // Required — initialises native renderer
  await AnimationPreloader.instance.preloadAll();  // Then preload .riv files
  runApp(const MyApp());
}
```

Omitting `RiveNative.init()` causes blank/flash first frame and unpredictable startup on iOS (Impeller).

---

## 9. RivePanel — Shared Texture

When rendering 3+ Rive widgets on the same screen, wrap in `RivePanel(useSharedTexture: true)`.
Shares a single GPU texture atlas — reduces VRAM usage and draw calls significantly.

```dart
class AnimatedBottomNav extends StatelessWidget {
  const AnimatedBottomNav({super.key});

  @override
  Widget build(BuildContext context) {
    return RivePanel(
      useSharedTexture: true,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: const [
          _NavIcon(asset: AnimationAssets.navHome,     label: 'Home'),
          _NavIcon(asset: AnimationAssets.navSearch,   label: 'Search'),
          _NavIcon(asset: AnimationAssets.navProfile,  label: 'Profile'),
          _NavIcon(asset: AnimationAssets.navSettings, label: 'Settings'),
        ],
      ),
    );
  }
}
```

**Rule:** Any screen with 3+ Rive widgets must use `RivePanel(useSharedTexture: true)`.

---

## 10. Testing

```dart
testWidgets('AnimatedToggle renders fallback when motion disabled', (tester) async {
  await tester.pumpWidget(
    MediaQuery(
      data: const MediaQueryData(disableAnimations: true),
      child: MaterialApp(
        home: AnimatedToggle(onChanged: (_) {}),
      ),
    ),
  );
  expect(find.byType(RiveAnimation), findsNothing);
  expect(find.byType(_StaticToggleFallback), findsOneWidget);
});

testWidgets('AnimatedToggle calls onChanged on tap', (tester) async {
  bool? result;
  await tester.pumpWidget(
    MaterialApp(
      home: AnimatedToggle(onChanged: (v) => result = v),
    ),
  );
  await tester.tap(find.byType(AnimatedToggle));
  await tester.pump();
  expect(result, isNotNull);
});
```

---

## 11. Performance Checklist

- [ ] `.riv` file size < 500 KB
- [ ] `await RiveNative.init()` called in `main()` before `runApp`
- [ ] Renderer declared explicitly (`Factory.rive` or `Factory.flutter`)
- [ ] File preloaded before first paint via `RivePreloader`
- [ ] `FileLoader` AND `RiveWidgetController` both disposed in `dispose()`
- [ ] `RiveWidgetBuilder` used — explicit loading/failed states
- [ ] 3+ Rive widgets on same screen wrapped in `RivePanel(useSharedTexture: true)`
- [ ] Reduce-motion branch implemented with static fallback widget
- [ ] Semantic labels on all animation containers
- [ ] No `setState` calls inside state machine callbacks
- [ ] Input access uses typed extension helpers
- [ ] Multi-artboard files use `AnimatedSwitcher` with `ValueKey`
- [ ] CI script validates: `find assets/rive -name "*.riv" -size +500k`

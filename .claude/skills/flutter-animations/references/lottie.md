# Lottie — Enterprise Flutter Reference

## Table of Contents
1. [Core Widget Patterns](#core-patterns)
2. [Composition Caching](#caching)
3. [RenderCache — Production Performance](#rendercache)
4. [Runtime Delegates — Dynamic Colors & Text](#delegates)
5. [Frame Rate Control](#framerate)
6. [dotLottie & TGS Support](#formats)
7. [Network Animations](#network)
8. [Error Handling & Fallbacks](#errors)
9. [Testing](#testing)
10. [Performance Checklist](#performance)

---

## 1. Core Widget Patterns {#core-patterns}

### Play-Once (splash, success confirmation)
```dart
class PlayOnceLottie extends StatefulWidget {
  final String assetPath;
  final VoidCallback? onComplete;
  final double size;

  const PlayOnceLottie({
    super.key,
    required this.assetPath,
    this.onComplete,
    this.size = 200,
  });

  @override
  State<PlayOnceLottie> createState() => _PlayOnceLottieState();
}

class _PlayOnceLottieState extends State<PlayOnceLottie>
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
    return Semantics(
      label: 'Animation',
      child: Lottie.asset(
        widget.assetPath,
        controller: _controller,
        renderCache: RenderCache.raster,
        frameRate: FrameRate.composition,
        width: widget.size,
        height: widget.size,
        fit: BoxFit.contain,
        onLoaded: (composition) {
          _controller
            ..duration = composition.duration
            ..forward().whenComplete(() => widget.onComplete?.call());
        },
      ),
    );
  }
}
```

### Looping (empty states, skeleton, background)
```dart
class LoopingLottie extends StatefulWidget {
  final String assetPath;
  final double? width;
  final double? height;
  final String semanticLabel;

  const LoopingLottie({
    super.key,
    required this.assetPath,
    required this.semanticLabel,
    this.width,
    this.height,
  });

  @override
  State<LoopingLottie> createState() => _LoopingLottieState();
}

class _LoopingLottieState extends State<LoopingLottie>
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
    return Semantics(
      label: widget.semanticLabel,
      child: Lottie.asset(
        widget.assetPath,
        controller: _controller,
        renderCache: RenderCache.raster,
        frameRate: FrameRate.composition,
        width: widget.width,
        height: widget.height,
        fit: BoxFit.contain,
        onLoaded: (composition) {
          _controller.duration = composition.duration;
          if (!reduceMotion) {
            _controller.repeat();
          } else {
            _controller.value = 0;  // Static first frame
          }
        },
      ),
    );
  }
}
```

---

## 2. Composition Caching {#caching}

Lottie parses JSON on load. In lists or repeated use, cache the `LottieComposition`.

```dart
// lib/core/animations/lottie_cache_manager.dart
import 'package:lottie/lottie.dart';
import 'package:flutter/services.dart';

class LottieCacheManager {
  LottieCacheManager._();
  static final LottieCacheManager instance = LottieCacheManager._();

  final Map<String, LottieComposition> _cache = {};
  bool get isAllLoaded => _expectedPaths.every(_cache.containsKey);

  Future<LottieComposition> load(String assetPath) async {
    if (_cache.containsKey(assetPath)) return _cache[assetPath]!;
    final composition = await AssetLottie(assetPath).load();
    _cache[assetPath] = composition;
    return composition;
  }

  Future<void> preloadAll(List<String> paths) async {
    await Future.wait(paths.map(load));
  }

  LottieComposition? getCached(String assetPath) => _cache[assetPath];
  void evict(String assetPath) => _cache.remove(assetPath);
  void clear() => _cache.clear();
}
```

---

## 3. RenderCache — Production Performance {#rendercache}

`renderCache` is the single most impactful Lottie performance setting.

```
RenderCache.none             -- re-renders every frame (default, highest CPU)
RenderCache.raster           -- GPU texture cache (best for loops on mid/high-end devices)
RenderCache.drawingCommands  -- CPU display list (best for low-memory devices)
```

**Rule:**
- Looping decorative animations → `RenderCache.raster`
- Complex frame-perfect animations → `RenderCache.drawingCommands`
- Animations that change delegates at runtime → `RenderCache.none`

**Memory trade-off:** `RenderCache.raster` caches all frames as GPU textures.
For very large animations (> 500 frames at high res), prefer `RenderCache.drawingCommands`.

---

## 4. Runtime Delegates — Dynamic Colors & Text {#delegates}

Use `LottieDelegates` to theme animations at runtime without modifying the source `.json`.

```dart
class ThemedLottie extends StatelessWidget {
  final String assetPath;
  final Color brandColor;
  final String? userName;

  const ThemedLottie({
    super.key,
    required this.assetPath,
    required this.brandColor,
    this.userName,
  });

  @override
  Widget build(BuildContext context) {
    return Lottie.asset(
      assetPath,
      renderCache: RenderCache.none,  // Must be none when delegates change at runtime
      delegates: LottieDelegates(
        text: (initialText) => userName ?? initialText,
        values: [
          ValueDelegate.color(
            const ['Brand Layer', 'Shape', 'Fill 1'],
            value: brandColor,
          ),
          ValueDelegate.opacity(
            const ['Background'],
            callback: (frameInfo) =>
                (frameInfo.overallProgress * 100).round().clamp(0, 100),
          ),
        ],
      ),
    );
  }
}
```

**Layer path syntax:** `['Layer Name', 'Group Name', 'Property Name']`
Use `**` as wildcard: `['**', 'Fill 1']` targets all Fill 1 properties.

**Important:** Static color overrides (brand theming) → `RenderCache.raster` is fine.
Dynamic per-frame delegate values → `RenderCache.none` required.

---

## 5. Frame Rate Control {#framerate}

```dart
// FrameRate.composition  -- exported FPS from After Effects (default, power-friendly)
// FrameRate.max          -- up to 120fps, smoothest, highest battery cost
// FrameRate(30)          -- explicit cap

// Production recommendation:
// Looping background/decorative: FrameRate.composition
// Premium interactive feedback:  FrameRate.max (use sparingly)
// Battery-sensitive (wearables): FrameRate(15)
```

---

## 6. dotLottie & TGS Support {#formats}

### dotLottie (.lottie) — preferred format for production
```dart
Future<LottieComposition?> dotLottieDecoder(List<int> bytes) {
  return LottieComposition.decodeZip(
    bytes,
    filePicker: (files) => files.firstWhereOrNull(
      (f) => f.name.startsWith('animations/') && f.name.endsWith('.json'),
    ),
  );
}

// Usage:
Lottie.asset('assets/lottie/hero.lottie', decoder: dotLottieDecoder)
```

### Telegram Stickers (.tgs)
```dart
Lottie.asset(
  'assets/lottie/sticker.tgs',
  decoder: LottieComposition.decodeGZip,
)
```

---

## 7. Network Animations {#network}

```dart
class RemoteLottie extends StatefulWidget {
  final String url;
  final Widget placeholder;
  final Widget errorWidget;

  const RemoteLottie({
    super.key,
    required this.url,
    required this.placeholder,
    required this.errorWidget,
  });

  @override
  State<RemoteLottie> createState() => _RemoteLottieState();
}

class _RemoteLottieState extends State<RemoteLottie>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  LottieComposition? _composition;
  bool _hasError = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this);
    _loadRemote();
  }

  Future<void> _loadRemote() async {
    try {
      final composition = await NetworkLottie(widget.url).load();
      if (!mounted) return;
      setState(() => _composition = composition);
      _controller
        ..duration = composition.duration
        ..repeat();
    } catch (e, st) {
      if (!mounted) return;
      setState(() => _hasError = true);
      debugPrint('RemoteLottie load failed: $e\n$st');
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_hasError) return widget.errorWidget;
    final composition = _composition;
    if (composition == null) return widget.placeholder;
    return Lottie(
      composition: composition,
      controller: _controller,
      renderCache: RenderCache.raster,
    );
  }
}
```

---

## 8. Error Handling & Fallbacks {#errors}

All Lottie widgets must surface failures — never produce a blank widget silently.
Wrap composition loads in try/catch. Show `errorWidget` for missing/corrupt assets, unsupported JSON schema, and network failures.

See `RemoteLottie` above for the full pattern.

---

## 9. Testing {#testing}

```dart
testWidgets('LoopingLottie pauses when reduce motion enabled', (tester) async {
  await tester.pumpWidget(
    MediaQuery(
      data: const MediaQueryData(disableAnimations: true),
      child: MaterialApp(
        home: LoopingLottie(
          assetPath: 'assets/lottie/test.json',
          semanticLabel: 'Test animation',
        ),
      ),
    ),
  );
  expect(find.byType(LoopingLottie), findsOneWidget);
  // Controller.value == 0, not repeating
});

testWidgets('PlayOnceLottie calls onComplete', (tester) async {
  bool completed = false;
  await tester.pumpWidget(
    MaterialApp(
      home: PlayOnceLottie(
        assetPath: 'assets/lottie/test.json',
        onComplete: () => completed = true,
      ),
    ),
  );
  await tester.pump(const Duration(seconds: 3));
  expect(completed, isTrue);
});
```

---

## 10. Performance Checklist {#performance}

- [ ] `.json` file size < 300 KB; prefer `.lottie` (dotLottie zip) format
- [ ] `renderCache: RenderCache.raster` on all looping animations
- [ ] `frameRate: FrameRate.composition` unless premium smoothness required
- [ ] `AnimationController` disposed in `dispose()`
- [ ] Compositions preloaded via `LottieCacheManager` before first render
- [ ] `renderCache: RenderCache.none` only when delegates are dynamic per-frame
- [ ] Reduce-motion branch implemented (pause at frame 0)
- [ ] Semantic labels on all Lottie containers
- [ ] Network animations have placeholder + error fallback states
- [ ] CI script validates: `find assets/lottie -name "*.json" -size +300k`
- [ ] `.lottie` zip format used in production bundles

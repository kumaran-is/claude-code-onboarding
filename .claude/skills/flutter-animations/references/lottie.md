# Lottie — Enterprise Flutter Reference

Verified on Flutter 3.50.1 / Dart 3.14.0 with `lottie: 3.8.2` (needs Flutter >= 3.47) and `material_ui: 1.11.1`.
Every snippet below compiles with zero analyzer issues; the widget tests in §9 pass.

## Table of Contents
1. [Core Widget Patterns](#1-core-widget-patterns)
2. [Composition Caching](#2-composition-caching)
3. [RenderCache — Production Performance](#3-rendercache--production-performance)
4. [Runtime Delegates — Colours & Text](#4-runtime-delegates--colours--text)
5. [Frame Rate Control](#5-frame-rate-control)
6. [dotLottie & TGS Support](#6-dotlottie--tgs-support)
7. [Network Animations](#7-network-animations)
8. [Error Handling & Fallbacks](#8-error-handling--fallbacks)
9. [Testing](#9-testing)
10. [Performance Checklist](#10-performance-checklist)

---

## 1. Core Widget Patterns

`lottie` 3.8.2 imports only `package:flutter/widgets.dart`-level libraries (no Material), so it works unchanged under a
`material_ui` app. It never reads the app theme: pass colours explicitly (§4).

### Play-once (splash, success confirmation)
```dart
import 'package:lottie/lottie.dart';
import 'package:material_ui/material_ui.dart';

class PlayOnceLottie extends StatefulWidget {
  const PlayOnceLottie({
    super.key,
    required this.assetPath,
    required this.semanticLabel,
    this.onComplete,
    this.size = 200,
  });

  final String assetPath;
  final String semanticLabel;
  final VoidCallback? onComplete;
  final double size;

  @override
  State<PlayOnceLottie> createState() => _PlayOnceLottieState();
}

class _PlayOnceLottieState extends State<PlayOnceLottie>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: widget.semanticLabel,
      child: Lottie.asset(
        widget.assetPath,
        controller: _controller,
        frameRate: FrameRate.composition,
        width: widget.size,
        height: widget.size,
        fit: BoxFit.contain,
        onLoaded: (composition) {
          _controller.duration = composition.duration;
          if (MediaQuery.disableAnimationsOf(context)) {
            // Reduced motion: jump to the final frame, still report completion.
            _controller.value = 1;
            widget.onComplete?.call();
            return;
          }
          _controller.forward().whenComplete(() => widget.onComplete?.call());
        },
        errorBuilder: (context, error, stack) => Icon(
          Icons.check_circle_outline,
          size: widget.size / 2,
          color: Theme.of(context).colorScheme.primary,
        ),
      ),
    );
  }
}
```

### Looping (empty states, background)
Start and stop the loop outside `build()`: `MediaQuery.disableAnimationsOf` can change while the screen is open.
```dart
import 'package:lottie/lottie.dart';
import 'package:material_ui/material_ui.dart';

class LoopingLottie extends StatefulWidget {
  const LoopingLottie({
    super.key,
    required this.assetPath,
    this.width,
    this.height,
  });

  final String assetPath;
  final double? width;
  final double? height;

  @override
  State<LoopingLottie> createState() => _LoopingLottieState();
}

class _LoopingLottieState extends State<LoopingLottie>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this);
  bool _loaded = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _syncPlayback();
  }

  void _syncPlayback() {
    if (!_loaded) return;
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller
        ..stop()
        ..value = 0; // static first frame
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
    // Decorative: the surrounding text carries the meaning.
    return ExcludeSemantics(
      child: Lottie.asset(
        widget.assetPath,
        controller: _controller,
        renderCache: RenderCache.drawingCommands,
        frameRate: FrameRate.composition,
        width: widget.width,
        height: widget.height,
        fit: BoxFit.contain,
        onLoaded: (composition) {
          _controller.duration = composition.duration;
          _loaded = true;
          _syncPlayback();
        },
        errorBuilder: (context, error, stack) => const SizedBox.shrink(),
      ),
    );
  }
}
```

---

## 2. Composition Caching

`Lottie.asset` already caches parsed compositions per provider (`Lottie.cache`). Keep an explicit cache only when you
need to preload before first frame or share one composition across many list items.

```dart
// lib/core/animations/lottie_cache_manager.dart
import 'package:lottie/lottie.dart';

class LottieCacheManager {
  LottieCacheManager._();
  static final LottieCacheManager instance = LottieCacheManager._();

  final Map<String, Future<LottieComposition>> _cache = {};

  /// Loads once; concurrent callers share the same future. A failed load is
  /// evicted so the next call retries, and the error reaches the caller.
  Future<LottieComposition> load(String assetPath) {
    return _cache.putIfAbsent(assetPath, () {
      final future = AssetLottie(assetPath).load();
      future.catchError((Object _) {
        _cache.remove(assetPath);
        return future;
      });
      return future;
    });
  }

  Future<void> preloadAll(Iterable<String> paths) =>
      Future.wait(paths.map(load));

  void evict(String assetPath) => _cache.remove(assetPath);
  void clear() => _cache.clear();
}
```

Render a cached composition with `Lottie(composition: composition, controller: ...)`.

---

## 3. RenderCache — Production Performance

`renderCache` is nullable; `null` (the default) renders every frame. From the 3.8.2 source:

| Value | What it stores | Use for |
|---|---|---|
| `null` (default) | nothing | delegates whose value changes every frame |
| `RenderCache.drawingCommands` | each frame as a `dart:ui` `Picture` (saves CPU, same GPU work) | **default for loops** |
| `RenderCache.raster` | each frame as a rasterised image, max 50 MB | only very short, very small animations |

There is no `RenderCache.none`. A large animation under `raster` can hit the 50 MB cap and evict frames constantly;
measure memory in DevTools before choosing it.

---

## 4. Runtime Delegates — Colours & Text

Neither engine reads `Theme.of(context)`. Theme an animation with `LottieDelegates`; the layer paths come from the
After Effects/Lottie file (`'**'` matches any depth).

```dart
import 'package:lottie/lottie.dart';
import 'package:material_ui/material_ui.dart';

class ThemedLottie extends StatelessWidget {
  const ThemedLottie({super.key, required this.assetPath, this.userName});

  final String assetPath;
  final String? userName;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Lottie.asset(
      assetPath,
      // Static overrides keep the cache valid; per-frame callbacks need null.
      renderCache: RenderCache.drawingCommands,
      delegates: LottieDelegates(
        text: (initialText) => userName ?? initialText,
        values: [
          ValueDelegate.color(const ['**', 'Brand Fill', '**'], value: scheme.primary),
          ValueDelegate.color(const ['**', 'Background', '**'], value: scheme.surface),
        ],
      ),
      errorBuilder: (context, error, stack) => const SizedBox.shrink(),
    );
  }
}
```

A delegate with a per-frame `callback:` (for example `ValueDelegate.opacity(path, callback: (frame) => ...)`) changes
every frame: leave `renderCache` null for that widget.

---

## 5. Frame Rate Control

```dart
import 'package:lottie/lottie.dart';

// FrameRate.composition  -- the file's own FPS (power-friendly; recommended default)
// FrameRate.max          -- every display frame (up to 120 Hz); highest battery cost
// FrameRate(30)          -- explicit cap
const decorative = FrameRate.composition;
const premiumFeedback = FrameRate.max; // use sparingly
const batterySensitive = FrameRate(15);
```

---

## 6. dotLottie & TGS Support

`Lottie.asset/network/memory/file` default to `LottieComposition.decodeZip`, which falls back to plain JSON. A
`.lottie` (dotLottie zip) file therefore needs **no custom decoder**; pass `decoder:` only to pick a specific
animation out of a multi-animation archive.

```dart
import 'package:lottie/lottie.dart';
import 'package:material_ui/material_ui.dart';

Widget heroAnimation() => Lottie.asset('assets/lottie/hero.lottie');

Widget sticker() => Lottie.asset(
  'assets/lottie/sticker.tgs',
  decoder: LottieComposition.decodeGZip, // Telegram stickers are gzip JSON
);

Future<LottieComposition?> pickSecondAnimation(List<int> bytes) =>
    LottieComposition.decodeZip(
      bytes,
      filePicker: (files) => files
          .where((f) => f.name.startsWith('animations/') && f.name.endsWith('.json'))
          .elementAtOrNull(1),
    );
```

---

## 7. Network Animations

Prefer bundled assets. When an animation must come from a server, use `Lottie.network` with `errorBuilder` and a
size-bounded box; never block content on it. Use HTTPS from a host you control.

```dart
import 'package:lottie/lottie.dart';
import 'package:material_ui/material_ui.dart';

class RemoteLottie extends StatelessWidget {
  const RemoteLottie({super.key, required this.url, required this.fallback});

  final String url;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: 160,
      child: ExcludeSemantics(
        child: Lottie.network(
          url,
          renderCache: RenderCache.drawingCommands,
          animate: !MediaQuery.disableAnimationsOf(context),
          errorBuilder: (context, error, stack) {
            // Report, then show the static fallback.
            FlutterError.reportError(
              FlutterErrorDetails(exception: error, stack: stack, library: 'RemoteLottie'),
            );
            return fallback;
          },
        ),
      ),
    );
  }
}
```

---

## 8. Error Handling & Fallbacks

Every `Lottie.*` call sets `errorBuilder`. Missing assets, corrupt JSON and network failures then show a visible
fallback instead of an empty box. Report the error (crash reporter or `FlutterError.reportError`) in the builder.
Never wrap the widget in try/catch: loading is asynchronous and the exception reaches `errorBuilder`, not your catch.

---

## 9. Testing

Decoding is asynchronous real work: in widget tests, load from memory and let it finish inside `tester.runAsync`.

```dart
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:lottie/lottie.dart';
import 'package:material_ui/material_ui.dart';

// Minimal valid Lottie: 1 s at 30 fps, one solid layer.
final tinyLottie = utf8.encode(
  jsonEncode({
    'v': '5.7.4', 'fr': 30, 'ip': 0, 'op': 30, 'w': 100, 'h': 100,
    'layers': [
      {
        'ty': 1, 'ind': 1, 'sc': '#3366ff', 'sw': 100, 'sh': 100,
        'ip': 0, 'op': 30, 'st': 0,
        'ks': {
          'o': {'a': 0, 'k': 100},
          'r': {'a': 0, 'k': 0},
          'p': {'a': 0, 'k': [50, 50, 0]},
          'a': {'a': 0, 'k': [50, 50, 0]},
          's': {'a': 0, 'k': [100, 100, 100]},
        },
      },
    ],
  }),
);

void main() {
  testWidgets('loads a composition without network', (tester) async {
    LottieComposition? loaded;
    await tester.pumpWidget(
      Directionality(
        textDirection: TextDirection.ltr,
        child: Lottie.memory(
          tinyLottie,
          renderCache: RenderCache.drawingCommands,
          onLoaded: (c) => loaded = c,
          errorBuilder: (context, error, stack) =>
              const Text('fallback', key: ValueKey('lottie-error')),
        ),
      ),
    );
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(loaded?.duration, const Duration(seconds: 1));
    expect(find.byKey(const ValueKey('lottie-error')), findsNothing);
  });

  testWidgets('corrupt bytes show the errorBuilder fallback', (tester) async {
    await tester.pumpWidget(
      Directionality(
        textDirection: TextDirection.ltr,
        child: Lottie.memory(
          utf8.encode('{"not":"lottie"'),
          errorBuilder: (context, error, stack) =>
              const Text('fallback', key: ValueKey('lottie-error')),
        ),
      ),
    );
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(find.byKey(const ValueKey('lottie-error')), findsOneWidget);
  });
}
```

Reduced motion: pump the widget under `MediaQuery(data: const MediaQueryData(disableAnimations: true), ...)` and
assert the controller is not animating. Device-level checks of the real app use Maestro, never a browser.

---

## 10. Performance Checklist

- [ ] `lottie: 3.8.2` pinned (Flutter >= 3.47); `.lottie` (dotLottie) preferred over raw `.json`
- [ ] `.json`/`.lottie` file size < 300 KB (CI: `find assets/lottie -size +300k`)
- [ ] Loops use `RenderCache.drawingCommands`; `raster` only for very short, small animations; `null` only with per-frame delegates
- [ ] `frameRate: FrameRate.composition` unless premium smoothness is required
- [ ] `AnimationController` disposed in `dispose()`
- [ ] Loop start/stop driven from `didChangeDependencies`, honouring `MediaQuery.disableAnimationsOf`
- [ ] `errorBuilder` on every `Lottie.*` call; errors reported
- [ ] Decorative animations wrapped in `ExcludeSemantics`; meaningful ones have a `Semantics` label
- [ ] Colours passed through `LottieDelegates` from `colorScheme` (Lottie does not read the theme)

# Mobile Performance Reference

Flutter-specific performance optimization for 60fps animations, efficient list rendering, memory management, and battery considerations. This is the #1 area where AI-generated Flutter code fails.

**Note:** This file covers Flutter exclusively. React Native patterns are not applicable in this workspace.

---

## 1. The Mobile Performance Mindset

### Why Mobile Performance is Different

```
DESKTOP:                          MOBILE:
+-- Unlimited power               +-- Battery matters
+-- Abundant RAM                  +-- RAM is shared, limited
+-- Stable network                +-- Network is unreliable
+-- CPU always available          +-- CPU throttles when hot
+-- User expects fast anyway      +-- User expects INSTANT
```

### Performance Budget

```
Every frame must complete in:
+-- 60fps  -> 16.67ms per frame
+-- 120fps (ProMotion) -> 8.33ms per frame

If your code takes longer:
+-- Frame drops -> Janky scroll/animation
+-- User perceives as "slow" or "broken"
+-- They WILL uninstall your app
```

---

## 2. Flutter Performance

### The #1 AI Mistake: setState Overuse

```dart
// WRONG: setState rebuilds ENTIRE widget tree
class BadCounter extends StatefulWidget {
  @override
  State<BadCounter> createState() => _BadCounterState();
}

class _BadCounterState extends State<BadCounter> {
  int _counter = 0;

  void _increment() {
    setState(() {
      _counter++; // This rebuilds EVERYTHING below!
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text('Counter: $_counter'),
        ExpensiveWidget(),        // Rebuilds unnecessarily!
        AnotherExpensiveWidget(), // Rebuilds unnecessarily!
      ],
    );
  }
}
```

### The const Constructor Rule

```dart
// CORRECT: const prevents rebuilds
class GoodCounter extends StatefulWidget {
  const GoodCounter({super.key}); // CONST constructor!

  @override
  State<GoodCounter> createState() => _GoodCounterState();
}

class _GoodCounterState extends State<GoodCounter> {
  int _counter = 0;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text('Counter: $_counter'),
        const ExpensiveWidget(),        // Won't rebuild!
        const AnotherExpensiveWidget(), // Won't rebuild!
      ],
    );
  }
}

// RULE: Add const to EVERY widget that doesn't depend on runtime state
```

### Targeted State Management with Riverpod

```dart
// WRONG: Reading entire provider — rebuilds on ANY change
Widget build(BuildContext context) {
  final state = ref.watch(myProvider); // Rebuilds on ANY field change
  return Text(state.name);
}

// CORRECT: Select only what you need
Widget build(BuildContext context) {
  final name = ref.watch(myProvider.select((s) => s.name));
  return Text(name); // Only rebuilds when name changes
}
```

### ListView Optimization

```dart
// WRONG: ListView without builder — renders all items immediately
ListView(
  children: items.map((item) => ItemWidget(item)).toList(),
)

// CORRECT: ListView.builder — lazy rendering (only visible items)
ListView.builder(
  itemCount: items.length,
  itemBuilder: (context, index) => ItemWidget(items[index]),
  // Additional optimizations:
  itemExtent: 56,       // Fixed height = faster layout calculation
  // Pre-render distance. cacheExtent is deprecated since 3.41: use scrollCacheExtent.
  scrollCacheExtent: const ScrollCacheExtent.pixels(100),
)

// For dividers:
ListView.separated(
  itemCount: items.length,
  itemBuilder: (context, index) => ItemWidget(items[index]),
  separatorBuilder: (context, index) => const Divider(),
)
```

### SingleChildScrollView: Hard Ban for Long Content

```dart
// NEVER for long content:
SingleChildScrollView(
  child: Column(
    children: items.map((item) => ItemWidget(item)).toList(),
  ),
)

// ALWAYS for long content:
ListView.builder(
  itemCount: items.length,
  itemBuilder: (context, index) => ItemWidget(items[index]),
)

// Or use Sliver for mixed content:
CustomScrollView(
  slivers: [
    const SliverAppBar(title: Text('Title')),
    SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) => ItemWidget(items[index]),
        childCount: items.length,
      ),
    ),
  ],
)
```

### Image Optimization

```dart
// WRONG: No caching, full resolution
Image.network(url)

// CORRECT: Cached with proper sizing
// Add to pubspec.yaml: cached_network_image: 4.0.7  (needs Flutter >= 3.44)
CachedNetworkImage(
  imageUrl: url,
  width: 100,
  height: 100,
  fit: BoxFit.cover,
  memCacheWidth: 200,   // Cache at 2x for retina
  memCacheHeight: 200,
  placeholder: (context, url) => const SkeletonLoader(),
  errorWidget: (context, url, error) => const Icon(Icons.broken_image),
)
```

### RepaintBoundary for Isolated Widgets

```dart
// Isolate expensive widgets from parent repaints
RepaintBoundary(
  child: ExpensiveAnimatedWidget(),
)

// Use when:
// - Widget has its own animation
// - Widget updates frequently but parent does not
// - Widget is complex (charts, custom painters)
```

### Dispose Pattern: Non-Negotiable

```dart
class MyWidget extends StatefulWidget {
  @override
  State<MyWidget> createState() => _MyWidgetState();
}

class _MyWidgetState extends State<MyWidget> {
  late final StreamSubscription _subscription;
  late final AnimationController _controller;
  late final TextEditingController _textController;

  @override
  void initState() {
    super.initState();
    _subscription = stream.listen((_) {});
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 300));
    _textController = TextEditingController();
  }

  @override
  void dispose() {
    // ALWAYS dispose in reverse order of creation
    _textController.dispose();
    _controller.dispose();
    _subscription.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Container();
}
```

### Flutter Performance Checklist

```
Before Every Widget:
- [ ] const constructor added (if no runtime args)
- [ ] const keywords on all static children
- [ ] Minimal setState scope (extract state to smallest widget)
- [ ] Using ref.watch(provider.select(...)) instead of full provider

Before Every List:
- [ ] Using ListView.builder (NOT ListView with children list)
- [ ] NOT using SingleChildScrollView with Column for long content
- [ ] itemExtent provided if fixed height
- [ ] Image caching with size limits (CachedNetworkImage)

Before Any Animation:
- [ ] Impeller is the renderer (the default on iOS and Android; the device log names the backend). Profile in `--profile` mode on a real device, never in debug
- [ ] Avoiding Opacity widget — use FadeTransition instead
- [ ] TickerProviderStateMixin or SingleTickerProviderStateMixin for AnimationController
- [ ] RepaintBoundary wrapping isolated animated subtrees

Before Any Release:
- [ ] All dispose() methods implemented
- [ ] No print() in production code
- [ ] Tested in profile/release mode: flutter run --profile
- [ ] Flutter DevTools performance overlay checked
```

---

## 3. Animation Performance

### The 60fps Imperative

```
Human eye detects:
+-- < 24 fps  -> "Slideshow" (broken)
+-- 24-30 fps -> "Choppy" (uncomfortable)
+-- 30-45 fps -> "Noticeably not smooth"
+-- 45-60 fps -> "Smooth" (acceptable)
+-- 60 fps    -> "Buttery" (target)
+-- 120 fps   -> "Premium" (ProMotion devices)

NEVER ship < 60fps animations.
```

### GPU vs CPU Animation in Flutter

```
GPU-ACCELERATED (FAST):          CPU-BOUND (SLOW):
+-- transform: translate          +-- width, height changes
+-- transform: scale              +-- Opacity widget (use FadeTransition)
+-- transform: rotate             +-- ClipRect with complex paths
+-- opacity (FadeTransition)      +-- BoxDecoration changes in animation
+-- (Composited via Impeller)     +-- Heavy CustomPainter every frame

RULE: Only animate transform and opacity.
Anything else triggers layout recalculation.
```

### Flutter Animation Patterns

```dart
// WRONG: Opacity widget causes compositing issues
Opacity(opacity: _animation.value, child: widget)

// CORRECT: FadeTransition uses GPU layer
FadeTransition(
  opacity: _animation,
  child: widget,
)

// CORRECT: ScaleTransition for scale animation
ScaleTransition(
  scale: _animation,
  child: widget,
)

// Spring physics in Flutter
SpringSimulation(
  const SpringDescription(
    mass: 1,
    stiffness: 150,
    damping: 15,
  ),
  start,
  end,
  velocity,
)
```

### Animation Timing Guide

| Animation Type | Duration | Easing |
|----------------|----------|--------|
| Micro-interaction | 100-200ms | Curves.easeOut |
| Standard transition | 200-300ms | Curves.easeOut |
| Page transition | 300-400ms | Curves.easeInOut |
| Complex/dramatic | 400-600ms | Curves.easeInOut |
| Loading skeletons | 1000-1500ms | linear (loop) |

---

## 4. Memory Management

### Common Flutter Memory Leaks

| Source | Solution |
|--------|----------|
| StreamSubscription not cancelled | `cancel()` in `dispose()` |
| AnimationController not disposed | `dispose()` in `dispose()` |
| TextEditingController not disposed | `dispose()` in `dispose()` |
| ScrollController not disposed | `dispose()` in `dispose()` |
| Large images in memory | Use `memCacheWidth`/`memCacheHeight` in CachedNetworkImage |

### Image Memory Formula

```
Image memory = width x height x 4 bytes (RGBA)

1080p image = 1920 x 1080 x 4 = 8.3 MB
4K image = 3840 x 2160 x 4 = 33.2 MB

10 full-res images = potential 83-332 MB -> App killed by OS

RULE: Always resize images to display size (or 2-3x for retina).
Use memCacheWidth / memCacheHeight to enforce this.
```

### Memory Profiling in Flutter

```
Flutter DevTools:
+-- flutter run --profile
+-- Open DevTools: flutter pub global run devtools
+-- Memory tab -> Watch for upward trend (leak)
+-- Timeline -> Identify dropped frames
+-- Widget inspector -> Find unnecessary rebuilds
```

---

## 5. Battery Optimization

### Battery Drain Sources

| Source | Impact | Mitigation |
|--------|--------|------------|
| **Screen on** | Highest | Dark mode on OLED devices |
| **Continuous GPS** | Very high | Use significant-change location updates |
| **Network requests** | High | Batch and cache aggressively |
| **Animations** | Medium | Reduce or pause in background |
| **Background work** | Medium | Defer non-critical work |
| **CPU computation** | Lower | Use `compute()` isolates; offload to backend |

### OLED Battery Saving

```
OLED screens: Black pixels = OFF = 0 power

Dark mode savings:
+-- True black (#000000) -> Maximum savings
+-- Dark gray (#1a1a1a) -> Slight savings
+-- Any color -> Some power
+-- White (#FFFFFF) -> Maximum power

RULE: On dark mode, use true black for backgrounds.
In Flutter: Colors.black, not Colors.grey.shade900
```

### Background Task Guidelines

```
iOS (via Flutter):
+-- Background fetch: Limited, system-scheduled
+-- Push notifications: Use FCM for important updates
+-- Background isolates: Use compute() for one-off work
+-- WorkmanagerPlugin: For scheduled background tasks

Android (via Flutter):
+-- WorkManager: flutter_workmanager package
+-- Foreground service: For continuous tasks (media player)
+-- Doze mode: Respect it, batch network operations
```

---

## 6. Network Performance

### Offline-First Architecture (Firebase Firestore)

This workspace uses Firebase Firestore for real-time data. Firestore has built-in offline support:

```dart
// Enable offline persistence (call once, before any queries)
FirebaseFirestore.instance.settings = const Settings(
  persistenceEnabled: true,
  cacheSizeBytes: Settings.CACHE_SIZE_UNLIMITED,
);

// Reads from cache first automatically — no extra code needed
// Writes are queued offline and synced when network returns
```

### Request Optimization

```
CACHE: Don't re-fetch unchanged data
+-- Firestore: Use snapshots() stream, cache is automatic
+-- REST APIs: Use ETag/If-None-Match headers
+-- Images: CachedNetworkImage handles this

PAGINATE: Never load all records
+-- Firestore: .limit(20), then .startAfterDocument(lastDoc)
+-- ListView.builder + pagination = efficient infinite scroll

COMPRESS: Reduce payload size
+-- gzip/brotli: Handled by Dio/http client automatically
+-- Request only needed Firestore fields with .select()
```

---

## 7. Performance Testing

### What to Test

| Metric | Target | Flutter Tool |
|--------|--------|--------------|
| **Frame rate** | >= 60fps | DevTools Performance tab |
| **Memory** | Stable, no growth | DevTools Memory tab |
| **Cold start** | < 2s | Manual timing, `flutter run --trace-startup` |
| **List scroll** | No jank | DevTools + manual feel |
| **Animation smoothness** | No frame drops | Performance overlay |

### Test on Real Devices

```
NEVER trust only:
+-- Simulator/emulator (faster than real device)
+-- Debug mode (slower than release)
+-- High-end devices only

ALWAYS test on:
+-- Low-end Android (< $200 phone, e.g. Samsung A series)
+-- Older iOS device (iPhone SE or iPhone 8)
+-- Release/profile build: flutter run --profile
+-- With real data volume (not 3 test items)
```

### Enable Performance Overlay

```dart
// In main.dart during debugging
MaterialApp(
  showPerformanceOverlay: true, // Shows GPU and CPU frame timing
  ...
)
```

---

## 8. Quick Reference

```dart
// Widgets: Always const
const MyWidget()

// Lists: Always builder
ListView.builder(itemBuilder: ...)

// State: Always targeted
ref.watch(provider.select((s) => s.specificField))

// Dispose: Always cleanup
@override
void dispose() {
  controller.dispose();
  subscription.cancel();
  super.dispose();
}

// Images: Always cached
CachedNetworkImage(
  imageUrl: url,
  memCacheWidth: displayWidth * 2, // 2x for retina
)

// Animation targets
// Only animate: transform (translate, scale, rotate), opacity
// Frame budget: 16.67ms at 60fps
// Test on: low-end Android in profile mode
```

---

> **Remember:** Performance is not optimization — it is baseline quality. A slow app is a broken app. Test on the worst device your users have, not the best device you have.

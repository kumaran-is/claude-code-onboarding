# Flutter Animations Workflow

> **When to use**: Adding Rive or Lottie animations to a Flutter feature, setting up animation architecture, optimising animation performance, or auditing animation accessibility
> **Skill**: `.claude/skills/flutter-animations/`
> **Prerequisites**: Engine decision resolved (Rive vs Lottie)

> **Iron Law**: RESOLVE ENGINE CHOICE FIRST using the decision table. Then read the relevant reference file. Never hardcode asset paths.

---

## Phase 0 — Engine Decision (Mandatory)

Resolve before writing any code. From `flutter-animations` SKILL.md decision table:

| Signal | Engine |
|---|---|
| Animation responds to user input or app state | **Rive** |
| Interactive state machine (toggle, auth flow, progress) | **Rive** |
| Play-once illustration (splash, success confirmation) | **Lottie** |
| Looping decorative / empty state | **Lottie** |
| Designer-exported After Effects animation | **Lottie** |

**Gate**: Engine choice documented before Phase 1 starts.

---

## Phase 1 — Architecture Setup

### 1.1 Add packages
```yaml
# pubspec.yaml
dependencies:
  rive: ^0.14.4
  lottie: ^3.3.2

flutter:
  assets:
    - assets/rive/
    - assets/lottie/
```

### 1.2 Create directory structure
```bash
mkdir -p lib/core/animations
mkdir -p lib/widgets/animations
mkdir -p assets/rive
mkdir -p assets/lottie
```

### 1.3 Create typed asset constants
Create `lib/core/animations/animation_assets.dart` — see `references/architecture.md §6`.

### 1.4 Initialise in main()
```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await RiveNative.init();                        // Required for rive ^0.14.x
  await AnimationService.instance.preloadAll();   // Preload all assets
  runApp(const MyApp());
}
```

**Gate**: `RiveNative.init()` present in `main()`, asset constants class created.

---

## Phase 2 — Implementation

### Rive path — read `references/rive.md` first
1. Use `FileLoader.fromAsset()` + `RiveWidgetController` (NOT legacy `RiveAnimation.asset`)
2. Wrap with `RiveWidgetBuilder` for explicit loading/failed/loaded states
3. Access inputs via typed extension helpers (`boolInput`, `numberInput`, `triggerInput`)
4. Wire to Riverpod state via `didUpdateWidget` + `_syncState()`
5. If 3+ Rive widgets on screen: wrap in `RivePanel(useSharedTexture: true)`

### Lottie path — read `references/lottie.md` first
1. Set `renderCache: RenderCache.raster` on all loops
2. Set `frameRate: FrameRate.composition` (honours exported FPS)
3. Use `LottieCacheManager` for preloading — never parse JSON on first frame
4. For dynamic colors/text: use `LottieDelegates` with `RenderCache.none`
5. For production assets: use `.lottie` (dotLottie zip) format over raw JSON

### Both paths
- Check `MediaQuery.of(context).disableAnimations` in every widget
- Wrap all animations in `Semantics(label: '...')`
- Provide static fallback widgets for reduce-motion users
- Use `AnimationAssets` constants — never raw string paths

**Gate**: All animations have semantic labels and reduce-motion branch.

---

## Phase 3 — Service Layer (for multi-animation features)

Read `references/architecture.md` for full patterns.

Key components to implement:
- `AnimationService` — unified facade for DI (get_it or Riverpod)
- `RivePreloader` — singleton cache for `.riv` files
- `LottieCacheManager` — singleton cache for `LottieComposition`
- `AnimationPlaceholder` — shimmer widget using `colorScheme` tokens

**Gate**: All controllers disposed in `dispose()`, preload wired to app startup.

---

## Phase 4 — Review & CI/CD

### Code review checklist (from `references/architecture.md §9`)
- [ ] Engine choice matches decision table
- [ ] `FileLoader` AND `RiveWidgetController` both disposed
- [ ] `AnimationController` (Lottie) disposed
- [ ] `RiveWidgetBuilder` used (not legacy API)
- [ ] `RenderCache.raster` on all Lottie loops
- [ ] `RiveNative.init()` in `main()`
- [ ] `Semantics` label on every animation
- [ ] Reduce-motion fallback per decision table
- [ ] Asset paths use `AnimationAssets` constants

### CI/CD size validation
Add to `.github/workflows/flutter.yml`:
```yaml
- name: Check Rive asset sizes
  run: |
    OVERSIZED=$(find assets/rive -name "*.riv" -size +500k)
    [ -n "$OVERSIZED" ] && echo "$OVERSIZED" && exit 1
    echo "All .riv files OK"

- name: Check Lottie asset sizes
  run: |
    OVERSIZED=$(find assets/lottie -name "*.json" -size +300k)
    [ -n "$OVERSIZED" ] && echo "$OVERSIZED" && exit 1
    echo "All Lottie files OK"
```

**Gate**: CI size checks passing. `/audit-security` and `flutter-mobile` review complete before merge.

---

## Common Pitfalls

| Pitfall | Correct Approach |
|---|---|
| Using `RiveAnimation.asset` (legacy) | Use `FileLoader` + `RiveWidgetController` + `RiveWidgetBuilder` |
| Omitting `RiveNative.init()` | Always call in `main()` before `runApp` |
| Lazy-loading on first render | Preload in `AnimationService.preloadAll()` at startup |
| Hardcoded asset paths | Use `AnimationAssets.toggle`, `AnimationAssets.emptyState` etc. |
| No reduce-motion branch | Check `MediaQuery.of(context).disableAnimations` in every widget |
| Disposing only controller, not FileLoader | Dispose BOTH `_fileLoader.dispose()` and `_controller.dispose()` |
| `RenderCache.raster` with dynamic delegates | Use `RenderCache.none` when delegates change at runtime |
| 3+ Rive widgets without RivePanel | Wrap in `RivePanel(useSharedTexture: true)` for GPU sharing |
| Raw JSON Lottie in production | Use `.lottie` (dotLottie zip) format — smaller APK/IPA |

---

## Related Workflows

- [feature-flutter-mobile.md](feature-flutter-mobile.md) — Full Flutter feature lifecycle
- [visual-regression-testing.md](visual-regression-testing.md) — Golden test setup for animated widgets
- [accessibility-audit.md](accessibility-audit.md) — WCAG 2.2 reduce-motion compliance
- [deployment-ci-cd.md](deployment-ci-cd.md) — CI/CD pipeline with animation size checks

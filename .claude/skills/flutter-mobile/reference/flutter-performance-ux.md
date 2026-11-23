# Flutter Performance & UX Templates

Accessibility, performance optimization, and UX polish patterns for modern Flutter (2025/2026).

## Accessibility (A11y) Templates

### Semantic Labels on Interactive Elements

```dart
// Always wrap tappable elements with Semantics
Semantics(
  label: 'Delete workout',
  hint: 'Double tap to delete this workout entry',
  button: true,
  child: IconButton(
    icon: const Icon(Icons.delete),
    onPressed: () => _deleteWorkout(workout.id),
  ),
)

// Use semanticLabel on images
Image.network(
  user.photoUrl,
  semanticLabel: '${user.displayName} profile photo',
)

// Exclude decorative elements from semantics
ExcludeSemantics(
  child: Icon(Icons.star, color: Theme.of(context).colorScheme.tertiary),
)
```

### Minimum Touch Targets (48x48 dp)

```dart
// Ensure all tappable elements meet minimum size
SizedBox(
  width: 48,
  height: 48,
  child: IconButton(
    icon: const Icon(Icons.close),
    onPressed: onClose,
  ),
)

// For custom tappable widgets
GestureDetector(
  onTap: onTap,
  child: ConstrainedBox(
    constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
    child: content,
  ),
)
```

### Screen Reader Focus Order

```dart
// Use FocusTraversalGroup for logical ordering
FocusTraversalGroup(
  policy: OrderedTraversalPolicy(),
  child: Column(
    children: [
      FocusTraversalOrder(
        order: const NumericFocusOrder(1),
        child: TextField(decoration: const InputDecoration(labelText: 'Email')),
      ),
      FocusTraversalOrder(
        order: const NumericFocusOrder(2),
        child: TextField(decoration: const InputDecoration(labelText: 'Password')),
      ),
      FocusTraversalOrder(
        order: const NumericFocusOrder(3),
        child: ElevatedButton(onPressed: _submit, child: const Text('Login')),
      ),
    ],
  ),
)

// Announce dynamic changes
SemanticsService.announce('Workout saved successfully', TextDirection.ltr);
```

### Dynamic Text / Font Scaling Support

```dart
// Use MediaQuery.textScalerOf for responsive text
final textScaler = MediaQuery.textScalerOf(context);

// Never constrain text containers to fixed heights
// DO:
Text('Workout Title', style: Theme.of(context).textTheme.headlineMedium)
// DON'T:
SizedBox(height: 24, child: Text('Workout Title')) // Clips at large font sizes

// Test at 200% with the widget-test harness in
// accessibility-audit/reference/flutter-a11y-automated.md §3 (TextScaler.linear(2)),
// then on a device/simulator via the system font-size setting.
// textScaleFactor / textScaleFactorOf are deprecated: use textScaler / textScalerOf.
```

## Performance Templates

### Paginated Lists

```dart
@riverpod
class PaginatedWorkouts extends _$PaginatedWorkouts {
  static const _pageSize = 20;
  DocumentSnapshot? _lastDoc;
  bool _hasMore = true;

  @override
  FutureOr<List<Workout>> build() async {
    _lastDoc = null;
    _hasMore = true;
    return _fetchPage();
  }

  Future<List<Workout>> _fetchPage() async {
    var query = FirebaseFirestore.instance
        .collection('workouts')
        .orderBy('createdAt', descending: true)
        .limit(_pageSize);

    if (_lastDoc != null) {
      query = query.startAfterDocument(_lastDoc!);
    }

    final snapshot = await query.get();
    if (snapshot.docs.length < _pageSize) _hasMore = false;
    if (snapshot.docs.isNotEmpty) _lastDoc = snapshot.docs.last;

    return snapshot.docs.map((d) => Workout.fromFirestore(d)).toList();
  }

  Future<void> loadMore() async {
    if (!_hasMore) return;
    final current = state.value ?? [];
    final nextPage = await _fetchPage();
    state = AsyncValue.data([...current, ...nextPage]);
  }
}
```

### Image Optimization

```dart
// Always specify cacheWidth/cacheHeight for memory efficiency
CachedNetworkImage(
  imageUrl: workout.imageUrl,
  cacheKey: workout.id,
  memCacheWidth: 300,  // Match display size
  memCacheHeight: 300,
  placeholder: (_, _) => const ShimmerPlaceholder(),
  errorWidget: (_, _, _) => const Icon(Icons.broken_image),
  fadeInDuration: const Duration(milliseconds: 200),
)
```

### Avoid Unnecessary Rebuilds

```dart
// Use const constructors everywhere possible
class WorkoutCard extends StatelessWidget {
  const WorkoutCard({super.key, required this.workout});
  final Workout workout;

  @override
  Widget build(BuildContext context) { /* ... */ }
}

// Use select() to watch specific fields only
final userName = ref.watch(
  userProvider.select((user) => user.value?.displayName ?? ''),
);

// Wrap expensive widgets with RepaintBoundary
RepaintBoundary(
  child: CustomPaint(painter: ChartPainter(data: chartData)),
)
```

## User Experience (UX) Templates

### Haptic Feedback

```dart
import 'package:flutter/services.dart';

// On key interactions
GestureDetector(
  onTap: () {
    HapticFeedback.lightImpact();
    _onItemSelected(item);
  },
  child: itemWidget,
)

// On destructive actions
onPressed: () {
  HapticFeedback.heavyImpact();
  _showDeleteConfirmation();
}

// On success
void _onSaveSuccess() {
  HapticFeedback.mediumImpact();
  ScaffoldMessenger.of(context).showSnackBar(/* ... */);
}
```

### Skeleton / Shimmer Loading States

```dart
// Skeleton only for a COLD read with no usable content (see interaction-contracts §6b).
class WorkoutListSkeleton extends StatelessWidget {
  const WorkoutListSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: 5,
      physics: const NeverScrollableScrollPhysics(),
      itemBuilder: (_, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: ShimmerEffect(
          child: Container(
            height: 80,
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(16),
            ),
          ),
        ),
      ),
    );
  }
}

// Usage in AsyncValue.when()
usersAsync.when(
  loading: () => const WorkoutListSkeleton(),
  error: (err, stack) => ErrorRetryWidget(error: err, onRetry: () => ref.invalidate(workoutListProvider)),
  data: (workouts) => WorkoutListView(workouts: workouts),
)
```

### Shimmer Effect Widget

```dart
class ShimmerEffect extends StatefulWidget {
  final Widget child;
  const ShimmerEffect({super.key, required this.child});

  @override
  State<ShimmerEffect> createState() => _ShimmerEffectState();
}

class _ShimmerEffectState extends State<ShimmerEffect>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Reduced motion: a static placeholder, no sweeping loop.
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
    final scheme = Theme.of(context).colorScheme;
    return AnimatedBuilder(
      animation: _controller,
      builder: (_, child) => ShaderMask(
        shaderCallback: (bounds) => LinearGradient(
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
          colors: [
            scheme.surfaceContainerHighest,
            scheme.surfaceContainerLow,
            scheme.surfaceContainerHighest,
          ],
          stops: [
            _controller.value - 0.3,
            _controller.value,
            _controller.value + 0.3,
          ],
        ).createShader(bounds),
        blendMode: BlendMode.srcATop,
        child: child,
      ),
      child: widget.child,
    );
  }
}
```

### Smooth Animations

```dart
// Page transitions with curves
PageRouteBuilder(
  pageBuilder: (_, _, _) => const DetailScreen(),
  transitionsBuilder: (_, animation, _, child) {
    return FadeTransition(
      opacity: CurvedAnimation(
        parent: animation,
        curve: Curves.easeOutCubic,
      ),
      child: SlideTransition(
        position: Tween<Offset>(
          begin: const Offset(0, 0.05),
          end: Offset.zero,
        ).animate(CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
        )),
        child: child,
      ),
    );
  },
  transitionDuration: const Duration(milliseconds: 300),
)

// AnimatedSwitcher for state changes
AnimatedSwitcher(
  duration: const Duration(milliseconds: 300),
  switchInCurve: Curves.easeOutCubic,
  switchOutCurve: Curves.easeInCubic,
  child: isCompleted
      ? const Icon(Icons.check_circle, key: ValueKey('done'), color: Colors.green)
      : const Icon(Icons.circle_outlined, key: ValueKey('pending')),
)
```

### Staged / Progressive Loading

For screens that load multiple independent data sources, load them in priority order so the user sees content immediately rather than waiting for everything.

```dart
// 1. Define loading stages as an enum
enum LoadStage { skeleton, primary, secondary, complete }

// 2. Track stage in the notifier
@riverpod
class HomeScreenNotifier extends _$HomeScreenNotifier {
  @override
  Future<HomeScreenState> build() async {
    return _loadProgressively();
  }

  Future<HomeScreenState> _loadProgressively() async {
    // Stage 0 — skeleton shown immediately via AsyncValue.loading()

    // Stage 1 — highest-priority data first (above-the-fold content)
    final categories = await ref.read(categoryRepositoryProvider).fetchAll();
    state = AsyncValue.data(
      HomeScreenState(stage: LoadStage.primary, categories: categories),
    );

    // Stage 2 — secondary data (below-the-fold or less critical)
    final items = await ref.read(scrapItemRepositoryProvider).fetchAll();
    state = AsyncValue.data(
      HomeScreenState(
        stage: LoadStage.secondary,
        categories: categories,
        items: items,
      ),
    );

    // Stage 3 — everything loaded
    return HomeScreenState(
      stage: LoadStage.complete,
      categories: categories,
      items: items,
    );
  }
}

// 3. Widget reacts to stage — progressive reveal, never a single long wait
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final homeAsync = ref.watch(homeScreenNotifierProvider);

    return homeAsync.when(
      loading: () => const HomeScreenSkeleton(),          // Stage 0
      error: (err, _) => ErrorRetryWidget(
        onRetry: () => ref.invalidate(homeScreenNotifierProvider),
      ),
      data: (state) => switch (state.stage) {
        LoadStage.skeleton  => const HomeScreenSkeleton(),
        LoadStage.primary   => HomePrimaryContent(categories: state.categories!),
        LoadStage.secondary => HomeFullContent(
            categories: state.categories!,
            items: state.items!,
          ),
        LoadStage.complete  => HomeFullContent(
            categories: state.categories!,
            items: state.items!,
          ),
      },
    );
  }
}
```

**Rules:**
- Stage 0 (skeleton) must render in under one frame — no async work before showing it
- Each stage emits a valid `AsyncValue.data` — never hold state in a local variable between stages
- Stages are additive: later stages include all data from earlier stages
- Use `ref.invalidate(provider)` on retry — don't re-implement the loading sequence in the widget

### Real-time Form Validation

```dart
class WorkoutForm extends ConsumerStatefulWidget {
  const WorkoutForm({super.key});

  @override
  ConsumerState<WorkoutForm> createState() => _WorkoutFormState();
}

class _WorkoutFormState extends ConsumerState<WorkoutForm> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  bool _submitted = false;

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      autovalidateMode: _submitted
          ? AutovalidateMode.onUserInteraction
          : AutovalidateMode.disabled,
      child: Column(
        children: [
          TextFormField(
            controller: _nameController,
            decoration: const InputDecoration(
              labelText: 'Workout Name',
              hintText: 'e.g., Morning Run',
            ),
            validator: (value) {
              if (value == null || value.trim().isEmpty) {
                return 'Workout name is required';
              }
              if (value.trim().length < 3) {
                return 'Name must be at least 3 characters';
              }
              return null;
            },
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _submit,
            child: const Text('Save Workout'),
          ),
        ],
      ),
    );
  }

  void _submit() {
    setState(() => _submitted = true);
    if (_formKey.currentState!.validate()) {
      HapticFeedback.mediumImpact();
      // Save workout...
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }
}
```

---

## Responsive Layout — `context.responsive()` Extension

A `BuildContext` extension that selects a value based on current screen width. Zero widget nesting — call it directly inside `build()` for any value (padding, column count, font size, widget).

**Breakpoints** (Material 3 / adaptive layout grid):

| Name | Min width | Typical device |
|------|-----------|---------------|
| mobile | 0 | phones |
| tablet | 600 | small tablets |
| desktop | 1200 | large tablets, desktop |
| largeDesktop | 1600 | wide monitors |

```dart
// lib/core/extensions/responsive_extension.dart

extension ResponsiveExtension on BuildContext {
  /// Returns the value matching the current screen-width breakpoint.
  /// Falls back to the next smaller breakpoint if a larger one is not provided.
  ///
  /// Example:
  ///   final padding = context.responsive(mobile: 16.0, tablet: 24.0, desktop: 32.0);
  T responsive<T>({
    required T mobile,
    T? tablet,
    T? desktop,
    T? largeDesktop,
  }) {
    final width = MediaQuery.sizeOf(this).width;
    if (width >= 1600 && largeDesktop != null) return largeDesktop;
    if (width >= 1200 && desktop != null) return desktop;
    if (width >= 600 && tablet != null) return tablet;
    return mobile;
  }

  /// Convenience booleans — use these for platform-branch logic.
  bool get isMobile   => MediaQuery.sizeOf(this).width < 600;
  bool get isTablet   => MediaQuery.sizeOf(this).width >= 600 && MediaQuery.sizeOf(this).width < 1200;
  bool get isDesktop  => MediaQuery.sizeOf(this).width >= 1200;

  /// Responsive column count for grid layouts.
  int get responsiveColumns {
    final w = MediaQuery.sizeOf(this).width;
    if (w >= 1600) return 4;
    if (w >= 1200) return 3;
    if (w >= 840)  return 2;
    return 1;
  }

  /// Responsive horizontal content padding.
  EdgeInsets get responsiveContentPadding => EdgeInsets.symmetric(
    horizontal: responsive(mobile: 16.0, tablet: 24.0, desktop: 40.0),
  );
}
```

**Usage in a widget:**

```dart
// ✅ Clean — no nested LayoutBuilder or MediaQuery.of() scattered everywhere
class ProductGrid extends StatelessWidget {
  final List<Product> products;
  const ProductGrid({required this.products, super.key});

  @override
  Widget build(BuildContext context) {
    final columns  = context.responsiveColumns;
    final padding  = context.responsiveContentPadding;
    final spacing  = context.responsive(mobile: 8.0, tablet: 12.0, desktop: 16.0);

    return Padding(
      padding: padding,
      child: GridView.builder(
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: columns,
          crossAxisSpacing: spacing,
          mainAxisSpacing: spacing,
          childAspectRatio: 0.75,
        ),
        itemCount: products.length,
        itemBuilder: (_, i) => ProductCard(product: products[i]),
      ),
    );
  }
}
```

**Rules:**

- Always use `MediaQuery.sizeOf(this)` (not `MediaQuery.of(this).size`) — rebuilds only when size changes, not on every MediaQuery field change
- `mobile` is required — it is the safe fallback for all unspecified breakpoints
- Use `context.responsive()` for values; use `context.isMobile` / `context.isDesktop` only for widget-branch decisions (e.g. showing a drawer vs a rail)
- Never hardcode breakpoint numbers outside this extension — all screen-size decisions go through `responsive()` or the bool getters
- Works with `const` widgets only if the value passed is itself `const` — pass it to a non-const constructor or use `final`

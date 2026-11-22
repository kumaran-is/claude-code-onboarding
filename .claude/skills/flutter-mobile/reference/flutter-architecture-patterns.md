# Flutter Architecture Patterns

Core architecture patterns for modern Flutter (2025/2026) — sealed classes, Result types, and Riverpod AsyncNotifier.

## Freezed Sealed State Classes (Riverpod 3.x standard)

Use `@freezed sealed class` for all state objects. This generates `when()`, `map()`,
`maybeWhen()`, and `copyWith()` automatically — do NOT use plain `sealed class` for state.

```dart
import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:your_app/features/auth/domain/entities/user.dart';

part 'auth_state.freezed.dart';

@freezed
sealed class AuthState with _$AuthState {
  const factory AuthState.initial()                    = _Initial;
  const factory AuthState.loading()                    = _Loading;
  const factory AuthState.authenticated(User user)     = _Authenticated;
  const factory AuthState.unauthenticated()            = _Unauthenticated;
  const factory AuthState.error(String message)        = _Error;
}
```

Always place in its own file: `presentation/providers/auth_state.dart`
Always add `part 'auth_state.freezed.dart';` — run `dart run build_runner build --delete-conflicting-outputs` after changes.

Usage in notifier:
```dart
// In auth_provider.dart
state = const AuthState.loading();
state = AuthState.authenticated(user);
state = AuthState.error(failure.message);
```

Usage in widget (exhaustive pattern matching — compile-time safe):
```dart
ref.watch(authProvider).when(
  initial:         ()      => const SplashScreen(),
  loading:         ()      => const CircularProgressIndicator(),
  authenticated:   (user)  => HomeScreen(user: user),
  unauthenticated: ()      => const LoginScreen(),
  error:           (msg)   => ErrorWidget(msg),
);
```

**Rule:** Every feature state file MUST be a separate `*_state.dart` file.
Never define state inline in the provider file.

## Functional Error Handling with Result Type

```dart
// Simple Result type (no external dependency)
sealed class Result<T> {
  const Result();
}

class Success<T> extends Result<T> {
  final T value;
  const Success(this.value);
}

class Failure<T> extends Result<T> {
  final AppException error;
  const Failure(this.error);
}

// Usage in repository
Future<Result<User>> getUser(String id) async {
  try {
    final doc = await _firestore.collection('users').doc(id).get();
    if (!doc.exists) return Failure(NotFoundException('User not found'));
    return Success(UserModel.fromFirestore(doc).toEntity());
  } on FirebaseException catch (e) {
    return Failure(NetworkException(e.message ?? 'Firestore error'));
  }
}

## DTO → Domain Model Mapper Pattern

API models (DTOs) live in the data layer and are never passed to the UI or ViewModels. A mapper method converts them to domain entities at the repository boundary.

**Rule:** UI and ViewModels receive domain entities only — never raw API models.
**Location:** Mappers live in the data layer (`data/models/`) alongside the API model class.

```dart
// lib/features/properties/data/models/property_api_model.dart

/// DTO — represents the raw API/Firestore document shape.
/// Never expose this to the presentation layer.
class PropertyApiModel {
  final String id;
  final String address;
  final int bedroomCount;
  final String statusCode; // raw string from API, e.g. "active"

  const PropertyApiModel({
    required this.id,
    required this.address,
    required this.bedroomCount,
    required this.statusCode,
  });

  factory PropertyApiModel.fromJson(Map<String, dynamic> json) =>
      PropertyApiModel(
        id: json['id'] as String,
        address: json['address'] as String,
        bedroomCount: json['bedroom_count'] as int,
        statusCode: json['status'] as String,
      );

  /// Mapper — converts DTO to the domain entity.
  /// Called inside the repository; never called from a ViewModel or widget.
  Property toDomain() => Property(
        id: id,
        address: address,
        bedroomCount: bedroomCount,
        status: PropertyStatus.fromCode(statusCode),
      );
}
```

The repository calls `toDomain()` before returning to callers:
```dart
Future<Result<Property>> getProperty(String id) async {
  final doc = await _firestore.collection('properties').doc(id).get();
  return Success(PropertyApiModel.fromJson(doc.data()!).toDomain());
}
```

// Usage in provider
@riverpod
class UserDetail extends _$UserDetail {
  @override
  FutureOr<User> build(String userId) async {
    final result = await ref.read(userRepositoryProvider).getUser(userId);
    return switch (result) {
      Success(:final value) => value,
      Failure(:final error) => throw error,
    };
  }
}
```

## Riverpod 3.x AsyncNotifier Pattern

```dart
@riverpod
class WorkoutList extends _$WorkoutList {
  @override
  FutureOr<List<Workout>> build() async {
    final repo = ref.read(workoutRepositoryProvider);
    return repo.getWorkouts();
  }

  Future<void> addWorkout(CreateWorkoutDto dto) async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      await ref.read(workoutRepositoryProvider).create(dto);
      return ref.read(workoutRepositoryProvider).getWorkouts();
    });
  }

  Future<void> deleteWorkout(String id) async {
    // Optimistic UI: remove immediately, restore on failure
    final previous = state.value ?? [];
    state = AsyncValue.data(previous.where((w) => w.id != id).toList());

    final result = await ref.read(workoutRepositoryProvider).delete(id);
    if (result case Failure(:final error)) {
      state = AsyncValue.data(previous); // Restore on failure
      throw error;
    }
  }
}
```

## Repository Error Handling with Crashlytics

Every repository catch block MUST do two things: log locally AND record to Crashlytics.
This pattern applies regardless of which database or backend you use.

```dart
import 'package:firebase_crashlytics/firebase_crashlytics.dart';

// ✅ REQUIRED pattern — applies to ALL repositories (REST, Firebase, local DB, etc.)
Future<Result<List<Order>>> getOrders(String userId) async {
  try {
    final response = await _apiClient.get('/orders/$userId');
    return Success(response.map(Order.fromJson).toList());
  } on NetworkException catch (e, stackTrace) {
    _logger.error('getOrders failed', userId: userId, error: e);
    await FirebaseCrashlytics.instance.recordError(e, stackTrace,
        reason: 'getOrders failed for user $userId');
    return Failure(e);
  } catch (e, stackTrace) {
    _logger.error('getOrders unexpected error', error: e);
    await FirebaseCrashlytics.instance.recordError(e, stackTrace,
        reason: 'getOrders unexpected error');
    return Failure(UnexpectedException(e.toString()));
  }
}

// ❌ FORBIDDEN — silent failure, user sees blank screen with no explanation
Future<List<Order>> getOrders(String userId) async {
  try {
    return await _apiClient.getOrders(userId);
  } catch (e) {
    return []; // Never do this
  }
}
```

**Rules:**
- `recordError()` takes `(error, stackTrace)` — always pass both
- Pass a `reason:` string with enough context to identify the call site in Crashlytics dashboard
- Always use `await` — `recordError` is async and dropping it silently loses crash reports
- Use `Result<T>` return type so callers are forced to handle the failure case

## Patterns

### Riverpod: Unnecessary flutter_riverpod Import

When using `riverpod_annotation`, `flutter_riverpod` is often redundant.
Use `package:riverpod_annotation/riverpod_annotation.dart` only, unless you
explicitly need `ProviderScope`, `ConsumerWidget`, etc. from `flutter_riverpod`.

### Test Error Propagation

Do NOT use `Future.then(..., onError: ...)` to capture typed exceptions — the
return type constraint causes a runtime error. Use try/catch instead:
```dart
Object? err;
try { await container.read(provider.future); } catch (e) { err = e; }
expect(err, isA<MyException>());
```

### StatefulShellRoute for Bottom Nav (GoRouter 17+)

Use `StatefulShellRoute.indexedStack` + `StatefulShellBranch` per tab.
Access navigation via `StatefulNavigationShell.goBranch()`. Do NOT use the old
`ShellRoute` pattern — it does not preserve per-tab state.

### Auth Provider with Sealed State

Wrapping a sealed class in `AsyncValue<AuthState>` works well.
Set state as `AsyncValue.data(AuthLoading())` during operations,
`AsyncValue.data(AuthAuthenticated(...))` on success.
Initial build reads from TokenStore to determine initial state.

### Code Generation After Provider Changes

Run `dart run build_runner build --delete-conflicting-outputs` after ANY
provider signature or model field change. Generated `.g.dart` files
reflect the parameter field names used in notifier methods.

### GoRouter + Riverpod Auth Integration

Connect `authProvider` state changes to GoRouter redirects using `refreshListenable`:
```dart
@Riverpod(keepAlive: true)
GoRouter appRouter(Ref ref) {
  final notifier = _RouterNotifier();
  ref.listen(authProvider, (_, __) => notifier.notifyListeners());
  return GoRouter(
    refreshListenable: notifier,
    redirect: (context, state) {
      final authState = ref.read(authProvider).value; // Riverpod 3: `value` (was valueOrNull)
      final isAuthenticated = authState is AuthAuthenticated;
      // ... redirect logic
    },
  );
}
class _RouterNotifier extends ChangeNotifier {}
```

Read in `redirect` with `ref.read`, refresh with `ref.listen` → `refreshListenable`; never `ref.watch` in the router provider (it rebuilds and disposes the live router). `return null` in a redirect means "build the requested route", so never return it while a gate is still undecided — see [flutter-navigation-and-auth-boot.md](flutter-navigation-and-auth-boot.md).

### Type-Safe Route Parameters (go_router 15+)

The default `state.pathParameters['id']!` string lookup is **unsafe** — it crashes at runtime if the parameter is missing or renamed. Use typed route classes instead.

```dart
// lib/core/router/app_routes.dart
import 'package:go_router/go_router.dart';

// 1. Define typed route classes — one per route with path parameters
@TypedGoRoute<ProductDetailRoute>(path: '/products/:productId')
class ProductDetailRoute extends GoRouteData {
  const ProductDetailRoute({required this.productId});
  final String productId;

  @override
  Widget build(BuildContext context, GoRouterState state) =>
      ProductDetailScreen(productId: productId);
}

@TypedGoRoute<UserProfileRoute>(path: '/users/:userId')
class UserProfileRoute extends GoRouteData {
  const UserProfileRoute({required this.userId});
  final String userId;

  @override
  Widget build(BuildContext context, GoRouterState state) =>
      UserProfileScreen(userId: userId);
}
```

```dart
// lib/core/router/app_router.dart
part 'app_router.g.dart';                    // generated by go_router_builder

@TypedGoRoute<HomeRoute>(
  path: '/',
  routes: [
    TypedGoRoute<ProductDetailRoute>(path: 'products/:productId'),
    TypedGoRoute<UserProfileRoute>(path: 'users/:userId'),
  ],
)
class HomeRoute extends GoRouteData {
  @override
  Widget build(BuildContext context, GoRouterState state) => const HomeScreen();
}
```

Navigate with compile-time safety:
```dart
// ✅ Compile-time safe — rename productId and the compiler tells you immediately
ProductDetailRoute(productId: product.id).go(context);

// ❌ Runtime crash if 'productId' is misspelled
context.go('/products/${product.id}');
```

Add `go_router_builder` to `pubspec.yaml`:
```yaml
dev_dependencies:
  go_router_builder: ^4.0.0   # generates app_router.g.dart
  build_runner: ^2.4.0
```

Run after route changes:
```bash
dart run build_runner build --delete-conflicting-outputs
```

**Rules:**

- **All routes with path parameters MUST use `TypedGoRoute`** — no raw `state.pathParameters[...]` lookups
- **Rename safety** — refactor route parameter names in one place; the compiler catches all call sites
- Place all `@TypedGoRoute` classes in `lib/core/router/app_routes.dart`
- The generated `app_router.g.dart` sits beside `app_router.dart` — commit it to source control
- Query parameters use `$extra` field for complex objects; primitive query params are typed fields with `@Default`

### Correct Error State in AsyncNotifier Mutations

WRONG — hides errors from the framework:
```dart
state = AsyncValue.data(AuthError(e.toString())); // hasError == false
```
CORRECT — uses native AsyncValue error:
```dart
state = AsyncValue.error(e, st); // hasError == true
```

### TextEditingController in Bottom Sheets

Extract to a `StatefulWidget` with `dispose()` — never create controllers inside
`ConsumerWidget` methods or `showModalBottomSheet` builder callbacks without disposal.

### ref.watch vs ref.read in build()

- `ref.watch(dep)` in `build()` = reactive (rebuilds when dep changes) — USE THIS
- `ref.read(dep)` in `build()` = one-time read, no tracking — only for `keepAlive` singletons, must be commented

### Async Operations in Sync Notifier

If a `Notifier<T>` has async methods, errors must be surfaced:
- Option A: Convert to `AsyncNotifier<T?>` — state machine includes loading/error
- Option B: Keep sync, catch errors in every method, store in separate error field, emit SnackBar via `ref.listen`

### BuildContext Usage After Async Gap

WRONG — widget may have been disposed during the await; context is stale:
```dart
Future<void> _submit() async {
  await ref.read(authProvider.notifier).signIn(email, password);
  // Widget may be gone by now — context is invalid
  Navigator.of(context).pushReplacementNamed('/home');
}
```

CORRECT — check mounted before any context access after an await:
```dart
Future<void> _submit() async {
  await ref.read(authProvider.notifier).signIn(email, password);
  if (!mounted) return; // Guard: widget was disposed during await
  Navigator.of(context).pushReplacementNamed('/home');
}
```

Rule: every `await` that is followed by a `context` usage (Navigator, ScaffoldMessenger,
Theme, etc.) MUST be preceded by `if (!mounted) return;`.

### StreamBuilder Firestore Write Loop

WRONG — writing to Firestore inside a StreamBuilder builder creates an infinite loop:
```dart
StreamBuilder<QuerySnapshot>(
  stream: _firestore.collection('items').snapshots(),
  builder: (context, snapshot) {
    if (snapshot.hasData) {
      // Each write → Firestore emits new snapshot → builder reruns → write again
      _firestore.collection('log').add({'event': 'viewed'});
      return ItemList(snapshot.data!.docs);
    }
    return const CircularProgressIndicator();
  },
)
```

CORRECT — perform side effects and writes in a StreamSubscription, not the builder:
```dart
class _ItemScreenState extends ConsumerState<ItemScreen> {
  StreamSubscription<QuerySnapshot>? _sub;

  @override
  void initState() {
    super.initState();
    _sub = FirebaseFirestore.instance
        .collection('items')
        .snapshots()
        .listen((snapshot) {
      // Side effects and writes belong here — runs once per snapshot, not in build
      FirebaseFirestore.instance.collection('log').add({'event': 'viewed'});
      ref.read(itemsProvider.notifier).updateFromSnapshot(snapshot);
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Builder is pure — no writes, no side effects
    final items = ref.watch(itemsProvider);
    return ItemList(items);
  }
}
```

### StreamBuilder Expensive Computation on Every Rebuild

WRONG — heavy computation runs on every Firestore snapshot, blocking the UI thread:
```dart
StreamBuilder<QuerySnapshot>(
  stream: _firestore.collection('items').snapshots(),
  builder: (context, snapshot) {
    if (!snapshot.hasData) return const CircularProgressIndicator();
    // Runs synchronously on the UI thread for every snapshot
    final sorted = snapshot.data!.docs
        .map((d) => ItemModel.fromFirestore(d))
        .where((i) => i.isActive)
        .toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return ItemList(sorted);
  },
)
```

CORRECT — move data transformation into a Riverpod provider so it is computed once
per snapshot and widgets use select() to avoid unnecessary rebuilds:
```dart
@riverpod
Stream<List<ItemModel>> activeItems(Ref ref) {
  return FirebaseFirestore.instance
      .collection('items')
      .snapshots()
      .map((snapshot) => snapshot.docs
          .map((d) => ItemModel.fromFirestore(d))
          .where((i) => i.isActive)
          .toList()
        ..sort((a, b) => b.createdAt.compareTo(a.createdAt)));
}

// Widget is now pure and efficient
class ItemScreen extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final itemsAsync = ref.watch(activeItemsProvider);
    return itemsAsync.when(
      data: (items) => ItemList(items),
      loading: () => const CircularProgressIndicator(),
      error: (e, _) => ErrorDisplay(error: e),
    );
  }
}
```

---

## Mixin-Based Data Source Error Handler

Eliminates duplicate try-catch blocks across repository implementations by centralising error handling in a single reusable mixin.

**When to use:** Any class that makes outbound network or database calls (repositories, remote data sources). Apply once — every `executeRemoteCall` automatically logs, maps, and returns a structured `Result<T>`.

```dart
// lib/core/data/mixins/remote_data_source_error_handler.dart

/// Mixin providing consistent error handling for remote data sources.
/// Pair with Result<T> from flutter-architecture-patterns.md §Result type.
mixin RemoteDataSourceErrorHandler {
  /// Implementing class must declare its own name — appears in every log line.
  String get dataSourceName;

  /// Execute a remote operation with consistent error handling.
  ///
  /// Handles typed exceptions in order of specificity:
  ///   FirebaseException → structured Crashlytics log + Failure(e)
  ///   SocketException   → network error + Failure(e)
  ///   Exception         → unexpected error + Failure(e)
  ///
  /// [operationName] — included in every log line; make it "[method]" e.g. 'fetchById'
  Future<Result<T>> executeRemoteCall<T>(
    Future<T> Function() operation, {
    required String operationName,
  }) async {
    try {
      return Success(await operation());
    } on FirebaseException catch (e, stack) {
      FirebaseCrashlytics.instance.log(
        '[$dataSourceName.$operationName] FirebaseException: ${e.code}',
      );
      await FirebaseCrashlytics.instance.recordError(
        e, stack,
        reason: '$dataSourceName.$operationName',
        printDetails: false,
      );
      return Failure(e);
    } on SocketException catch (e, stack) {
      FirebaseCrashlytics.instance.log(
        '[$dataSourceName.$operationName] SocketException: $e',
      );
      await FirebaseCrashlytics.instance.recordError(
        e, stack,
        reason: '$dataSourceName.$operationName — network',
        printDetails: false,
      );
      return Failure(NetworkException(e.message));
    } catch (e, stack) {
      FirebaseCrashlytics.instance.log(
        '[$dataSourceName.$operationName] Unexpected: $e',
      );
      await FirebaseCrashlytics.instance.recordError(
        e, stack,
        reason: '$dataSourceName.$operationName — unexpected',
        printDetails: false,
      );
      return Failure(UnexpectedException(e.toString()));
    }
  }

  /// Variant for queries that legitimately return null (e.g. .maybeSingle()).
  /// Returns Success(null) on not-found; Failure on real errors.
  Future<Result<T?>> executeRemoteCallNullable<T>(
    Future<T?> Function() operation, {
    required String operationName,
  }) async {
    try {
      return Success(await operation());
    } on FirebaseException catch (e, stack) {
      FirebaseCrashlytics.instance.log(
        '[$dataSourceName.$operationName] FirebaseException: ${e.code}',
      );
      await FirebaseCrashlytics.instance.recordError(
        e, stack,
        reason: '$dataSourceName.$operationName',
        printDetails: false,
      );
      return Failure(e);
    } catch (e, stack) {
      FirebaseCrashlytics.instance.log(
        '[$dataSourceName.$operationName] Unexpected: $e',
      );
      await FirebaseCrashlytics.instance.recordError(
        e, stack,
        reason: '$dataSourceName.$operationName — unexpected',
        printDetails: false,
      );
      return Failure(UnexpectedException(e.toString()));
    }
  }
}
```

**Usage — apply the mixin:**

```dart
// lib/features/orders/data/repositories/order_repository_impl.dart
class OrderRepositoryImpl with RemoteDataSourceErrorHandler
    implements OrderRepository {

  @override
  String get dataSourceName => 'OrderRepository';

  final FirebaseFirestore _firestore;
  OrderRepositoryImpl(this._firestore);

  @override
  Future<Result<Order>> fetchById(String id) =>
      executeRemoteCall(
        () async {
          final doc = await _firestore.collection('orders').doc(id).get();
          return Order.fromFirestore(doc);
        },
        operationName: 'fetchById',
      );

  @override
  Future<Result<Order?>> findByCode(String code) =>
      executeRemoteCallNullable(
        () async {
          final snap = await _firestore
              .collection('orders')
              .where('code', isEqualTo: code)
              .limit(1)
              .get();
          if (snap.docs.isEmpty) return null;
          return Order.fromFirestore(snap.docs.first);
        },
        operationName: 'findByCode',
      );
}
```

**Rules:**

- `dataSourceName` must follow `[FeatureName]Repository` or `[FeatureName]DataSource` — makes Crashlytics logs `grep`-able
- Always pass `operationName` as the method name — never a generic string like `'operation'`
- Never add additional try-catch inside the lambda passed to `executeRemoteCall` — let the mixin handle it
- `executeRemoteCallNullable` is only for queries where null is a valid success state; don't use it to silently swallow missing records that should exist
- Complement with `ResilientNetworkService` from `flutter-network-resilience.md` for timeout + retry before the call reaches this handler

---

## Sync Notifier<T> — Non-Async State

Use `Notifier<T>` (not `AsyncNotifier`) when state is always available synchronously — no loading or error states. Common examples: form state, UI toggle, filter selection, theme mode.

```dart
// features/products/presentation/providers/filter_provider.dart
part 'filter_provider.g.dart';

// 1. Define the state with freezed (sealed not required for sync value types)
@freezed
class ProductFilter with _$ProductFilter {
  const factory ProductFilter({
    @Default('') String query,
    @Default(SortOrder.newest) SortOrder sortOrder,
    @Default([]) List<String> selectedCategories,
  }) = _ProductFilter;
}

enum SortOrder { newest, oldest, priceAsc, priceDesc }

// 2. Sync notifier — extends _$FilterNotifier, returns T (not Future<T>)
@riverpod
class FilterNotifier extends _$FilterNotifier {
  @override
  ProductFilter build() => const ProductFilter(); // always returns synchronously

  void setQuery(String query) =>
      state = state.copyWith(query: query);

  void setSortOrder(SortOrder order) =>
      state = state.copyWith(sortOrder: order);

  void toggleCategory(String category) {
    final current = state.selectedCategories;
    state = state.copyWith(
      selectedCategories: current.contains(category)
          ? current.where((c) => c != category).toList()
          : [...current, category],
    );
  }

  void reset() => state = const ProductFilter();
}
```

**Usage in widget:**

```dart
// Read current filter state reactively
final filter = ref.watch(filterNotifierProvider);

// Call mutations in callbacks (ref.read — not ref.watch)
ElevatedButton(
  onPressed: () => ref.read(filterNotifierProvider.notifier).setQuery('shoes'),
  child: const Text('Filter: Shoes'),
);

// Drive a derived provider from sync state
@riverpod
Future<List<Product>> filteredProducts(Ref ref) async {
  final filter = ref.watch(filterNotifierProvider);
  return ref.watch(productRepositoryProvider).search(filter);
}
```

**Sync vs Async decision rule:**

| Condition | Provider type |
|-----------|--------------|
| State is always available (no network, no db) | `Notifier<T>` |
| State requires async init or remote fetch | `AsyncNotifier<T>` |
| State is a stream (Firestore, WebSocket) | `StreamNotifier<T>` |
| State is read-only derived value | `@riverpod T fn(Ref ref)` |

**Rules:**
- `build()` returns `T` directly — never `Future<T>` or `Stream<T>` in a sync Notifier
- State mutations return `void` — set `state =` directly, never async inside sync methods
- Use `state.copyWith()` from freezed — never mutate state in place
- Sync notifiers are auto-disposed by default; add `@Riverpod(keepAlive: true)` only for global UI state (e.g., theme mode, locale)

---

## Parameterized Providers — `.family` Pattern

Use parameterized providers when the same provider logic needs different inputs (e.g. fetching a specific item by ID, filtering by category).

### When to use `.family`

| Scenario | Pattern |
|----------|---------|
| Fetch single item by ID | `@riverpod` function provider with typed parameter |
| Filter/search with params | `@riverpod` function provider with data class param |
| Scoped state per item (e.g. expansion state) | `@riverpod` notifier with typed parameter |

### Read-only family — fetch item by ID

```dart
// lib/features/product/presentation/providers/product_detail_provider.dart
part 'product_detail_provider.g.dart';

@riverpod
Future<Product> productDetail(Ref ref, String productId) async {
  return ref
      .watch(productRepositoryProvider)
      .getById(productId);
}
```

Usage in widget:
```dart
// Pass the ID as the family argument
final product = ref.watch(productDetailProvider('product-123'));

product.when(
  data:    (p)     => ProductCard(product: p),
  loading: ()      => const ProductCardSkeleton(),
  error:   (e, st) => ErrorWidget(e.toString()),
);
```

### Notifier family — per-item toggle state

```dart
// lib/features/product/presentation/providers/product_selection_provider.dart
part 'product_selection_provider.g.dart';

@riverpod
class ProductSelection extends _$ProductSelection {
  @override
  bool build(String productId) => false;   // each productId gets its own instance

  void toggle() => state = !state;
}
```

Usage:
```dart
// Each product card gets its own isolated state
final isSelected = ref.watch(productSelectionProvider(product.id));
ref.read(productSelectionProvider(product.id).notifier).toggle();
```

### Complex parameter — use a data class

When you need multiple parameters, use a `@freezed` data class instead of primitives:

```dart
// lib/features/product/domain/value_objects/product_filter.dart
@freezed
class ProductFilter with _$ProductFilter {
  const factory ProductFilter({
    required String categoryId,
    @Default('') String searchQuery,
    @Default(SortOrder.newest) SortOrder sortOrder,
  }) = _ProductFilter;
}
```

```dart
// lib/features/product/presentation/providers/filtered_products_provider.dart
part 'filtered_products_provider.g.dart';

@riverpod
Future<List<Product>> filteredProducts(Ref ref, ProductFilter filter) async {
  return ref
      .watch(productRepositoryProvider)
      .search(filter);
}
```

### Rules

- Always use a typed parameter — never pass `dynamic` or `Map` to a family provider
- For 2+ parameters: use a `@freezed` data class — Riverpod equality checks require `==` to be correct
- Family providers are auto-disposed when no widget watches them — this is correct; do NOT add `keepAlive: true` unless you have a specific reason
- `ref.watch(provider(id))` in build() = reactive and auto-disposes with the widget
- `ref.read(provider(id).notifier)` in callbacks = imperative action only

---

## features/common/ — Shared Cross-Feature Logic

`lib/features/common/` holds widgets and providers that are reused across **two or more features**
but do not belong in `core/` (which is infrastructure) or `design_system/` (which is pure UI).

### What belongs here

| Type | Example | Rule |
|------|---------|------|
| Shared domain widgets | `UserAvatarWidget`, `PriceBadge` | Used in ≥ 2 feature screens |
| Cross-feature providers | `currentUserProvider`, `featureFlagsProvider` | Consumed by ≥ 2 feature providers |
| Shared use-case helpers | `FormatCurrencyUseCase` | Pure Dart, no UI |

### What does NOT belong here

| Type | Correct location |
|------|-----------------|
| Infrastructure (Dio, storage, auth) | `core/di/providers.dart` |
| Pure UI primitives (buttons, inputs) | `design_system/components/` |
| Feature-specific widgets | `features/<feature>/presentation/widgets/` |

### Structure

```
lib/features/common/
├── providers/
│   └── current_user_provider.dart   # @Riverpod(keepAlive: true) — auth state shared across features
├── widgets/
│   ├── user_avatar.dart             # Reused in profile, chat, comments
│   └── empty_state_widget.dart      # Reused in home, search, history
└── usecases/
    └── format_currency_usecase.dart # Pure Dart, used in cart and order history
```

### Usage pattern

```dart
// lib/features/common/providers/current_user_provider.dart
part 'current_user_provider.g.dart';

@Riverpod(keepAlive: true)
Stream<User?> currentUser(Ref ref) {
  return ref
      .watch(authRepositoryProvider)
      .watchCurrentUser();
}
```

```dart
// lib/features/profile/presentation/screens/profile_screen.dart
final user = ref.watch(currentUserProvider);

// lib/features/chat/presentation/screens/chat_screen.dart
final user = ref.watch(currentUserProvider); // same provider, shared state
```

### Decision rule — Rule of Three applies

| Occurrences | Action |
|-------------|--------|
| Used in 1 feature | Keep inside that feature's `presentation/widgets/` |
| Used in 2 features | Accept duplication OR move to `common/` if extraction is obvious |
| Used in 3+ features | Move to `common/` immediately |

**Never move to `common/` speculatively.** Wait until the second or third consumer exists.

---

### Deep Linking Configuration

Deep links allow users to navigate directly into the app from URLs, notifications, or other apps.

#### GoRouter deep link setup

```dart
// lib/core/router/app_router.dart
@Riverpod(keepAlive: true)
GoRouter appRouter(Ref ref) {
  return GoRouter(
    initialLocation: '/home',
    // iOS: configure in Info.plist (CFBundleURLTypes + associated domains)
    // Android: configure in AndroidManifest.xml (intent-filter with scheme/host)
    routes: $appRoutes,           // generated from @TypedGoRoute classes
    redirect: _authGuard(ref),
    errorBuilder: (context, state) => const NotFoundScreen(),
  );
}
```

#### Android — `AndroidManifest.xml`

Add inside the `<activity>` tag:
```xml
<!-- App Links (verified HTTPS — preferred) -->
<intent-filter android:autoVerify="true">
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="https" android:host="app.yourcompany.com" />
</intent-filter>

<!-- Custom scheme fallback (no verification required) -->
<intent-filter>
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="yourapp" android:host="open" />
</intent-filter>
```

#### iOS — `Info.plist`

```xml
<!-- Custom URL scheme -->
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array><string>yourapp</string></array>
  </dict>
</array>

<!-- Universal Links — also requires apple-app-site-association file on server -->
<key>com.apple.developer.associated-domains</key>
<array>
  <string>applinks:app.yourcompany.com</string>
</array>
```

#### Deep link parameter validation (security)

Always validate and sanitise deep link parameters before processing. Never trust URL parameters:

```dart
// lib/core/router/guards/deep_link_validator.dart
String? validateProductId(String? raw) {
  if (raw == null || raw.isEmpty) return null;
  // UUIDs only — reject any value that could be a path traversal or injection
  final uuidPattern = RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');
  return uuidPattern.hasMatch(raw) ? raw : null;
}
```

```dart
// In your TypedGoRoute.build()
@override
Widget build(BuildContext context, GoRouterState state) {
  final safeId = validateProductId(productId);
  if (safeId == null) return const NotFoundScreen();
  return ProductDetailScreen(productId: safeId);
}
```

#### Testing deep links

```bash
# Android
adb shell am start -W -a android.intent.action.VIEW \
  -d "https://app.yourcompany.com/products/abc-123" \
  com.yourcompany.yourapp

# iOS Simulator
xcrun simctl openurl booted "yourapp://open/products/abc-123"
```

#### Rules

- **Prefer App Links (Android) / Universal Links (iOS)** over custom schemes — they require domain verification, preventing other apps from hijacking your scheme
- **Validate every path parameter** from deep links — treat them as untrusted user input
- **Never expose sensitive routes** (admin, payment confirmation) via deep links
- **Test both schemes** in CI: verified HTTPS link + custom scheme fallback
- Cold-start vs warm links, auth ordering and iOS link forwarding: [flutter-navigation-and-auth-boot.md](flutter-navigation-and-auth-boot.md)

---

## Smart vs Dumb Widget Pattern

Every widget has a classification. Enforce it before writing any widget.

| Type | Base class | ref usage | Location | Portable? |
|------|-----------|-----------|----------|-----------|
| **Smart (Container)** | `ConsumerWidget` / `ConsumerStatefulWidget` | `ref.watch()` in build, `ref.read()` in callbacks | `screens/` | No |
| **Dumb (Presentational)** | `StatelessWidget` | NONE | `shared_ui/`, `widgets/` | Yes |

**Core rule:** If a widget lives in `packages/shared_ui/`, it MUST extend `StatelessWidget` and MUST NOT import `flutter_riverpod`.

**ref placement rule:** `ref.watch()` belongs in `build()` only. `ref.read()` belongs in callbacks and event handlers only. Never swap them.

Full pattern guide, decision tree, and Riverpod enforcement gates: `smart-dumb-widgets.md`

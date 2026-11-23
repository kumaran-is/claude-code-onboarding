# Flutter Code Templates

This file contains all code templates for Flutter development with Riverpod, Freezed, and Firebase.

## Design System Token File Structure

Tokens flow in one direction — never reference raw values in widget code.

```
lib/design_system/
├── tokens/
│   ├── color_tokens.dart       # Raw hex palette constants — NEVER used directly in widgets
│   ├── spacing_tokens.dart     # 4pt grid: xs=4, sm=8, md=12, lg=16, xl=24, xxl=32, xxxl=48
│   ├── radius_tokens.dart      # Corner radius constants
│   ├── elevation_tokens.dart   # Elevation levels
│   ├── motion_tokens.dart      # Duration + Curve constants
│   └── index.dart              # Barrel export
├── typography/
│   ├── font_families.dart      # Font name string constants only
│   ├── app_text_styles.dart    # Full M3 TextStyle map (displayLarge → labelSmall)
│   └── app_text_theme.dart     # Assembles TextTheme from app_text_styles
└── theme/
    ├── app_color_scheme.dart   # Semantic ColorScheme (maps ColorTokens → M3 roles)
    ├── app_theme_extension.dart # ThemeExtension<T> for custom fields (brandPrimary, surfaceCard…)
    ├── app_theme.dart          # AppTheme.light() / .dark() factories — import in bootstrap.dart
    └── theme_provider.dart     # @riverpod ThemeMode notifier
```

**Token layering — one direction only:**
```
color_tokens.dart  →  app_color_scheme.dart  →  app_theme_extension.dart  →  Widget
```

**Rules:**
- Widget code: `Theme.of(context).extension<AppThemeExtension>()!.brandPrimary` for custom colors
- Widget code: `Theme.of(context).colorScheme.*` for M3 semantic colors
- Widget code: `SpacingTokens.lg` or `AppSpacing.lg` for spacing — never raw `16.0`
- Widget code: `Theme.of(context).textTheme.*` for typography
- Never add `examples/` or `demo/` files under `lib/` — they ship in the production build

## pubspec.yaml Essentials

Resolved together with `flutter pub get` and analyzed clean on Flutter 3.50.1 / Dart 3.14.0. Exact pins: bump them deliberately, re-resolve, re-run codegen and tests.

```yaml
environment:
  sdk: ^3.14.0
  flutter: ">=3.50.1"

dependencies:
  flutter:
    sdk: flutter
  material_ui: 1.11.1             # replaces package:flutter/material.dart (deprecated after 3.47)

  # State management — Riverpod 3.x codegen-first
  flutter_riverpod: 3.5.0
  riverpod_annotation: 4.0.8

  # Navigation
  go_router: 18.1.4

  # Data / serialisation
  freezed_annotation: 3.1.0
  json_annotation: 4.12.0

  # Network
  dio: 5.11.1

  # Storage
  flutter_secure_storage: 11.2.0  # sensitive data (tokens, keys)
  shared_preferences: 2.5.6       # small non-sensitive preferences; cached data → drift (offline references)

  # Firebase (add only what the project uses)
  firebase_core: 5.2.0
  firebase_auth: 7.1.0
  firebase_crashlytics: 6.1.0
  firebase_app_check: 0.5.2

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: 6.0.0
  build_runner: 2.17.1
  riverpod_generator: 4.0.10
  riverpod_lint: 3.2.0            # analyzer plugin; needs Dart >= 3.13
  freezed: 4.0.3
  json_serializable: 6.15.2
  mocktail: 1.0.5

flutter:
  uses-material-design: true      # Icons still use the MaterialIcons font
```

`hive_flutter` (last release 2021) is no longer recommended. `custom_lint` is no longer needed: `riverpod_lint` 3 is an `analysis_server_plugin` enabled from `analysis_options.yaml`.

## build.yaml

Required for snake_case JSON — without it json_serializable keeps the Dart field names.

```yaml
targets:
  $default:
    builders:
      json_serializable:
        options:
          explicit_to_json: true
          field_rename: snake
```

Freezed 4 generates `when`/`map` by default, but prefer an exhaustive `switch` over the sealed union in new code. `riverpod_generator` 4 has no `riverpod_version` option; delete it from older `build.yaml` files.

## analysis_options.yaml

```yaml
include: package:flutter_lints/flutter.yaml

analyzer:
  exclude:
    - "**/*.g.dart"
    - "**/*.freezed.dart"
  errors:
    missing_required_param: error

plugins:
  riverpod_lint: 3.2.0   # top-level key, same version as the dev dependency

linter:
  rules:
    - always_use_package_imports
    - avoid_dynamic_calls
    - prefer_final_locals
```

Check that the plugin is live: a `ConsumerWidget` app without a `ProviderScope` must report `missing_provider_scope` in `flutter analyze`. With the old `analyzer: plugins: - custom_lint` block the same probe reports nothing.

## Entry Point Pattern (main / bootstrap / app)

### main.dart — one line only
```dart
void main() => bootstrap(() => const App());
```

### bootstrap.dart — all async init here
```dart
Future<void> bootstrap(FutureOr<Widget> Function() builder) async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);

  // Framework-level error hook — catches Flutter rendering errors
  FlutterError.onError = FirebaseCrashlytics.instance.recordFlutterFatalError;
  // Dart async errors not caught by Flutter
  PlatformDispatcher.instance.onError = (error, stack) {
    FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
    return true;
  };

  await FirebaseAppCheck.instance.activate(
    providerAndroid: kDebugMode
        ? const AndroidDebugProvider()
        : const AndroidPlayIntegrityProvider(),
    providerApple: kDebugMode
        ? const AppleDebugProvider()
        : const AppleAppAttestWithDeviceCheckFallbackProvider(),
  );

  runApp(
    ProviderScope(
      observers: [if (kDebugMode) const RiverpodLogger()],
      child: await builder(),
    ),
  );
}

/// Debug-only provider failure log. Riverpod 3 observers receive a context.
final class RiverpodLogger extends ProviderObserver {
  const RiverpodLogger();

  @override
  void providerDidFail(
    ProviderObserverContext context,
    Object error,
    StackTrace stackTrace,
  ) {
    debugPrint('${context.provider} failed: $error');
  }
}
```

Firebase is initialised before the Crashlytics hooks are installed (they call into an initialised app). App Check 0.5 takes provider objects (`providerAndroid`, `providerApple`); the old `androidProvider:`/`appleProvider:` enum parameters no longer compile.

### app.dart — MaterialApp.router only
```dart
import 'package:material_ui/material_ui.dart'; // not package:flutter/material.dart

class App extends ConsumerWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    return MaterialApp.router(
      routerConfig: ref.watch(appRouterProvider),
      theme:      AppTheme.light(),
      darkTheme:  AppTheme.dark(),
      themeMode:  themeMode,
    );
  }
}
```

## ThemeExtension — Custom Semantic Colors

Use `ThemeExtension<T>` for any color that is not covered by Material 3's built-in `ColorScheme`.
Widget code accesses it via `Theme.of(context).extension<AppThemeExtension>()!`.

```dart
// design_system/theme/app_theme_extension.dart
@immutable
class AppThemeExtension extends ThemeExtension<AppThemeExtension> {
  const AppThemeExtension({
    required this.brandPrimary,
    required this.surfaceCard,
    required this.success,
    required this.warning,
  });

  final Color brandPrimary;
  final Color surfaceCard;
  final Color success;
  final Color warning;

  static const light = AppThemeExtension(
    brandPrimary: ColorTokens.brandPrimary500,
    surfaceCard:  ColorTokens.neutral50,
    success:      ColorTokens.success500,
    warning:      ColorTokens.warning500,
  );

  static const dark = AppThemeExtension(
    brandPrimary: ColorTokens.brandPrimary300,
    surfaceCard:  ColorTokens.neutral800,
    success:      ColorTokens.success400,
    warning:      ColorTokens.warning400,
  );

  @override
  AppThemeExtension copyWith({Color? brandPrimary, Color? surfaceCard, Color? success, Color? warning}) =>
      AppThemeExtension(
        brandPrimary: brandPrimary ?? this.brandPrimary,
        surfaceCard:  surfaceCard  ?? this.surfaceCard,
        success:      success      ?? this.success,
        warning:      warning      ?? this.warning,
      );

  @override
  AppThemeExtension lerp(AppThemeExtension? other, double t) {
    if (other == null) return this;
    return AppThemeExtension(
      brandPrimary: Color.lerp(brandPrimary, other.brandPrimary, t)!,
      surfaceCard:  Color.lerp(surfaceCard,  other.surfaceCard,  t)!,
      success:      Color.lerp(success,      other.success,      t)!,
      warning:      Color.lerp(warning,      other.warning,      t)!,
    );
  }
}

// In widget code:
final ext = Theme.of(context).extension<AppThemeExtension>()!;
Container(color: ext.brandPrimary);
```

## Global DI Providers — core/di/providers.dart

All `@Riverpod(keepAlive: true)` singletons live here. Never scatter them across features. Generated providers take the plain `Ref` (Riverpod 3 removed the per-provider `DioRef`-style types).

```dart
part 'providers.g.dart';

@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  final dio = Dio(BaseOptions(baseUrl: Env.apiBaseUrl));
  dio.interceptors.addAll([
    AuthInterceptor(ref),
    LogInterceptor(responseBody: kDebugMode),
  ]);
  ref.onDispose(dio.close);
  return dio;
}

@Riverpod(keepAlive: true)
FlutterSecureStorage secureStorage(Ref ref) => const FlutterSecureStorage();

// Repository singletons — example
@Riverpod(keepAlive: true)
AuthRepository authRepository(Ref ref) => AuthRepositoryImpl(
  remote: ref.watch(authRemoteDataSourceProvider),
  local: ref.watch(authLocalDataSourceProvider),
);
```

## Domain Value Objects

Validate business constraints inside the domain layer — never in the UI.

```dart
// features/auth/domain/value_objects/email.dart
class Email {
  final String value;

  Email._(this.value);

  factory Email(String raw) {
    final trimmed = raw.trim().toLowerCase();
    if (!RegExp(r'^[^@]+@[^@]+\.[^@]+$').hasMatch(trimmed)) {
      throw const FormatException('Invalid email address');
    }
    return Email._(trimmed);
  }

  @override
  String toString() => value;
  @override
  bool operator ==(Object other) => other is Email && other.value == value;
  @override
  int get hashCode => value.hashCode;
}

// features/auth/domain/value_objects/password.dart
class Password {
  final String value;

  Password._(this.value);

  factory Password(String raw) {
    if (raw.length < 8) throw const FormatException('Password must be at least 8 characters');
    return Password._(raw);
  }
}
```

## Freezed Model Template

Freezed 3+ requires `abstract` (or `sealed` for unions) on the class; a plain `class` no longer compiles.

```dart
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:freezed_annotation/freezed_annotation.dart';

part 'user_model.freezed.dart';
part 'user_model.g.dart';

@freezed
abstract class UserModel with _$UserModel {
  const factory UserModel({
    @JsonKey(includeToJson: false) required String id, // the document id
    required String email,
    required String displayName,
    @Default('') String photoUrl,
    @TimestampConverter() required DateTime createdAt,
  }) = _UserModel;

  factory UserModel.fromJson(Map<String, dynamic> json) =>
      _$UserModelFromJson(json);

  factory UserModel.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data();
    if (data == null) throw StateError('users/${doc.id} does not exist');
    return UserModel.fromJson({...data, 'id': doc.id});
  }
}

/// Firestore stores dates as Timestamp, not ISO strings.
class TimestampConverter implements JsonConverter<DateTime, Timestamp> {
  const TimestampConverter();

  @override
  DateTime fromJson(Timestamp json) => json.toDate().toUtc(); // toDate() is local time

  @override
  Timestamp toJson(DateTime object) => Timestamp.fromDate(object);
}
```

## Riverpod Provider Template

```dart
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'user_provider.g.dart';

@riverpod
class UserList extends _$UserList {
  @override
  Future<List<UserModel>> build() =>
      ref.watch(userRepositoryProvider).getUsers();

  Future<void> add(UserModel user) async {
    final repo = ref.read(userRepositoryProvider);
    state = const AsyncLoading(); // keeps the previous list as `value`
    final next = await AsyncValue.guard(() async {
      await repo.createUser(user);
      return repo.getUsers();
    });
    if (!ref.mounted) return; // screen closed while saving
    state = next;
  }
}
```

## Screen Template

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

class UserListScreen extends ConsumerWidget {
  const UserListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final usersAsync = ref.watch(userListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Users')),
      body: usersAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, stack) => Center(child: Text('Error: $err')),
        data: (users) => ListView.builder(
          itemCount: users.length,
          itemBuilder: (context, index) {
            final user = users[index];
            return ListTile(
              title: Text(user.displayName),
              subtitle: Text(user.email),
              onTap: () => context.go('/users/${user.id}'),
            );
          },
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.go('/users/new'),
        child: const Icon(Icons.add),
      ),
    );
  }
}
```

## GoRouter Configuration

The router is a `keepAlive` provider, never a global reading `FirebaseAuth.instance` (a global cannot be overridden in tests and never re-runs `redirect` on sign-out). `authPhaseProvider` comes from [flutter-navigation-and-auth-boot.md](flutter-navigation-and-auth-boot.md). go_router 18 needs the `material_ui` `MaterialApp.router`; under the deprecated `flutter/material.dart` one it falls back to non-Material page transitions.

```dart
/// Built once (keepAlive); auth changes reach it through refreshListenable.
@Riverpod(keepAlive: true)
GoRouter appRouter(Ref ref) {
  final refresh = ValueNotifier(ref.read(authPhaseProvider));
  ref.listen(authPhaseProvider, (_, next) => refresh.value = next);
  ref.onDispose(refresh.dispose);

  final router = GoRouter(
    initialLocation: '/home',
    refreshListenable: refresh,
    redirect: (context, state) {
      final location = state.matchedLocation;
      switch (ref.read(authPhaseProvider)) {
        case AuthPhase.unresolved:
          return location == '/splash' ? null : '/splash';
        case AuthPhase.signedOut:
          return location == '/login' ? null : '/login';
        case AuthPhase.signedIn:
          return location == '/login' || location == '/splash' ? '/home' : null;
      }
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, _) => const SplashScreen()),
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      ShellRoute(
        builder: (_, _, child) => AppShell(child: child),
        routes: [
          GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
          GoRoute(path: '/users', builder: (_, _) => const UserListScreen()),
          GoRoute(
            path: '/users/:id',
            builder: (_, state) =>
                UserDetailScreen(userId: state.pathParameters['id']!),
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
}
```

## Widget Test Template

```dart
// A class-based provider is overridden with a notifier, not a closure.
class _FakeUserList extends UserList {
  @override
  Future<List<UserModel>> build() async => [_alice];
}

void main() {
  testWidgets('UserListScreen shows users', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [userListProvider.overrideWith(_FakeUserList.new)],
        child: const MaterialApp(home: UserListScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Alice'), findsOneWidget);
  });
}
```

## Firebase Integration Patterns

### Firestore Data Source

```dart
class UserRemoteDataSource {
  final FirebaseFirestore _firestore;

  UserRemoteDataSource(this._firestore);

  Stream<List<UserModel>> watchUsers() {
    return _firestore
        .collection('users')
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((snap) => snap.docs
            .map((doc) => UserModel.fromFirestore(doc))
            .toList());
  }

  Future<UserModel> getUser(String id) async {
    final doc = await _firestore.collection('users').doc(id).get();
    return UserModel.fromFirestore(doc); // throws StateError when missing
  }

  Future<void> createUser(UserModel user) async {
    await _firestore.collection('users').doc(user.id).set(user.toJson());
  }
}
```

### Firebase Auth Integration

```dart
@Riverpod(keepAlive: true)
FirebaseAuth firebaseAuth(Ref ref) => FirebaseAuth.instance;

/// Generates `authProvider` (the `Notifier` suffix is stripped).
@Riverpod(keepAlive: true)
class AuthNotifier extends _$AuthNotifier {
  @override
  Stream<User?> build() => ref.watch(firebaseAuthProvider).authStateChanges();

  Future<void> signInWithEmail(String email, String password) => ref
      .read(firebaseAuthProvider)
      .signInWithEmailAndPassword(email: email, password: password);

  Future<void> signOut() => ref.read(firebaseAuthProvider).signOut();
}
```

## Clean Architecture Repository Pattern

```dart
// Domain layer - abstract repository
abstract class UserRepository {
  Stream<List<User>> watchUsers();
  Future<User> getUser(String id);
  Future<void> createUser(User user);
}

// Data layer - implementation
class UserRepositoryImpl implements UserRepository {
  final UserRemoteDataSource _remoteDataSource;

  UserRepositoryImpl(this._remoteDataSource);

  @override
  Stream<List<User>> watchUsers() {
    return _remoteDataSource.watchUsers()
        .map((models) => models.map((m) => m.toEntity()).toList());
  }

  @override
  Future<User> getUser(String id) async {
    final model = await _remoteDataSource.getUser(id);
    return model.toEntity();
  }

  @override
  Future<void> createUser(User user) async {
    await _remoteDataSource.createUser(user.toModel());
  }
}

// Data layer - mappers keep the domain entity free of JSON/Firestore types
extension UserModelMapper on UserModel {
  User toEntity() => User(id: id, email: email, displayName: displayName);
}

extension UserEntityMapper on User {
  UserModel toModel() => UserModel(
    id: id,
    email: email,
    displayName: displayName,
    createdAt: DateTime.now().toUtc(),
  );
}
```

## Design System — Token Implementations

### color_tokens.dart

```dart
// design_system/tokens/color_tokens.dart
/// Raw hex palette constants. NEVER reference these directly in widget code.
/// Use AppColorScheme.* for M3 semantic roles or AppThemeExtension for custom fields.
abstract final class ColorTokens {
  // Brand
  static const brandPrimary50  = Color(0xFFEEF2FF);
  static const brandPrimary100 = Color(0xFFE0E7FF);
  static const brandPrimary300 = Color(0xFFA5B4FC);
  static const brandPrimary500 = Color(0xFF6366F1);
  static const brandPrimary700 = Color(0xFF4338CA);
  static const brandPrimary900 = Color(0xFF312E81);

  // Neutral
  static const neutral0   = Color(0xFFFFFFFF);
  static const neutral50  = Color(0xFFF9FAFB);
  static const neutral100 = Color(0xFFF3F4F6);
  static const neutral500 = Color(0xFF6B7280);
  static const neutral800 = Color(0xFF1F2937);
  static const neutral900 = Color(0xFF111827);

  // Semantic
  static const success400 = Color(0xFF4ADE80);
  static const success500 = Color(0xFF22C55E);
  static const error400   = Color(0xFFF87171);
  static const error500   = Color(0xFFEF4444);
  static const warning400 = Color(0xFFFBBF24);
  static const warning500 = Color(0xFFF59E0B);
}
```

### spacing_tokens.dart

```dart
// design_system/tokens/spacing_tokens.dart
/// 4-point grid. Use these — never raw double literals — in padding, gap, and margin.
/// Widget: EdgeInsets.all(SpacingTokens.lg)  SizedBox(height: SpacingTokens.xl)
abstract final class SpacingTokens {
  static const double xs   =  4.0;
  static const double sm   =  8.0;
  static const double md   = 12.0;
  static const double lg   = 16.0;
  static const double xl   = 24.0;
  static const double xxl  = 32.0;
  static const double xxxl = 48.0;
}
```

### radius_tokens.dart

```dart
// design_system/tokens/radius_tokens.dart
abstract final class RadiusTokens {
  static const double none = 0.0;
  static const double sm   = 4.0;
  static const double md   = 8.0;
  static const double lg   = 12.0;
  static const double xl   = 16.0;
  static const double xxl  = 24.0;
  static const double full = 999.0;
}
```

### elevation_tokens.dart

```dart
// design_system/tokens/elevation_tokens.dart
abstract final class ElevationTokens {
  static const double none    = 0.0;
  static const double low     = 1.0;
  static const double medium  = 3.0;
  static const double high    = 6.0;
  static const double highest = 12.0;
}
```

### motion_tokens.dart

```dart
// design_system/tokens/motion_tokens.dart
abstract final class MotionTokens {
  // Durations — aligned with Material 3 motion spec
  static const durationFast   = Duration(milliseconds: 150);
  static const durationNormal = Duration(milliseconds: 250);
  static const durationSlow   = Duration(milliseconds: 400);

  // Curves
  static const curveStandard = Curves.easeInOut;  // UI transitions
  static const curveEnter    = Curves.easeOut;    // elements entering the screen
  static const curveExit     = Curves.easeIn;     // elements leaving the screen
}
```

---

## Design System — Typography Implementations

### font_families.dart

```dart
// design_system/typography/font_families.dart
abstract final class FontFamilies {
  static const primary   = 'Inter';
  static const monospace = 'JetBrainsMono';
}
```

### app_text_styles.dart

```dart
// design_system/typography/app_text_styles.dart
/// Full Material 3 type scale. Never create inline TextStyle in widget code.
/// Use Theme.of(context).textTheme.* or these constants directly.
abstract final class AppTextStyles {
  static const displayLarge = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 57, fontWeight: FontWeight.w400, letterSpacing: -0.25,
  );
  static const displayMedium = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 45, fontWeight: FontWeight.w400,
  );
  static const displaySmall = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 36, fontWeight: FontWeight.w400,
  );
  static const headlineLarge = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 32, fontWeight: FontWeight.w400,
  );
  static const headlineMedium = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 28, fontWeight: FontWeight.w500,
  );
  static const headlineSmall = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 24, fontWeight: FontWeight.w500,
  );
  static const titleLarge = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 22, fontWeight: FontWeight.w500,
  );
  static const titleMedium = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 16, fontWeight: FontWeight.w500, letterSpacing: 0.15,
  );
  static const titleSmall = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 14, fontWeight: FontWeight.w500, letterSpacing: 0.1,
  );
  static const bodyLarge = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 16, fontWeight: FontWeight.w400, height: 1.5,
  );
  static const bodyMedium = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 14, fontWeight: FontWeight.w400, height: 1.5,
  );
  static const bodySmall = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 12, fontWeight: FontWeight.w400, height: 1.5,
  );
  static const labelLarge = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 14, fontWeight: FontWeight.w500, letterSpacing: 0.1,
  );
  static const labelMedium = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 12, fontWeight: FontWeight.w500, letterSpacing: 0.5,
  );
  static const labelSmall = TextStyle(
    fontFamily: FontFamilies.primary,
    fontSize: 11, fontWeight: FontWeight.w500, letterSpacing: 0.5,
  );
}
```

### app_text_theme.dart

```dart
// design_system/typography/app_text_theme.dart
/// Assembles the full M3 TextTheme from AppTextStyles constants.
/// Consumed by AppTheme.light() and AppTheme.dark() — not used directly in widgets.
final appTextTheme = const TextTheme(
  displayLarge:   AppTextStyles.displayLarge,
  displayMedium:  AppTextStyles.displayMedium,
  displaySmall:   AppTextStyles.displaySmall,
  headlineLarge:  AppTextStyles.headlineLarge,
  headlineMedium: AppTextStyles.headlineMedium,
  headlineSmall:  AppTextStyles.headlineSmall,
  titleLarge:     AppTextStyles.titleLarge,
  titleMedium:    AppTextStyles.titleMedium,
  titleSmall:     AppTextStyles.titleSmall,
  bodyLarge:      AppTextStyles.bodyLarge,
  bodyMedium:     AppTextStyles.bodyMedium,
  bodySmall:      AppTextStyles.bodySmall,
  labelLarge:     AppTextStyles.labelLarge,
  labelMedium:    AppTextStyles.labelMedium,
  labelSmall:     AppTextStyles.labelSmall,
);
```

---

## Design System — Theme Implementations

### app_color_scheme.dart

```dart
// design_system/theme/app_color_scheme.dart
/// Maps ColorTokens → Material 3 semantic ColorScheme roles.
/// Widgets use: Theme.of(context).colorScheme.primary (NOT ColorTokens directly).
abstract final class AppColorScheme {
  static const light = ColorScheme(
    brightness:           Brightness.light,
    primary:              ColorTokens.brandPrimary500,
    onPrimary:            ColorTokens.neutral0,
    primaryContainer:     ColorTokens.brandPrimary50,
    onPrimaryContainer:   ColorTokens.brandPrimary900,
    secondary:            ColorTokens.brandPrimary300,
    onSecondary:          ColorTokens.neutral0,
    surface:              ColorTokens.neutral0,
    onSurface:            ColorTokens.neutral900,
    surfaceContainerLow:  ColorTokens.neutral50,
    surfaceContainer:     ColorTokens.neutral100,
    error:                ColorTokens.error500,
    onError:              ColorTokens.neutral0,
  );

  static const dark = ColorScheme(
    brightness:           Brightness.dark,
    primary:              ColorTokens.brandPrimary300,
    onPrimary:            ColorTokens.brandPrimary900,
    primaryContainer:     ColorTokens.brandPrimary700,
    onPrimaryContainer:   ColorTokens.brandPrimary50,
    secondary:            ColorTokens.brandPrimary500,
    onSecondary:          ColorTokens.neutral0,
    surface:              ColorTokens.neutral900,
    onSurface:            ColorTokens.neutral50,
    surfaceContainerLow:  ColorTokens.neutral800,
    surfaceContainer:     ColorTokens.neutral800,
    error:                ColorTokens.error400,
    onError:              ColorTokens.neutral900,
  );
}
```

### app_theme.dart (abstract final class — corrected)

```dart
// design_system/theme/app_theme.dart
/// Single source of truth for ThemeData. Never call ThemeData() directly outside this class.
abstract final class AppTheme {
  static ThemeData light() => ThemeData(
    useMaterial3: true,
    colorScheme:  AppColorScheme.light,
    textTheme:    appTextTheme,
    extensions:   const [AppThemeExtension.light],
  );

  static ThemeData dark() => ThemeData(
    useMaterial3: true,
    colorScheme:  AppColorScheme.dark,
    textTheme:    appTextTheme,
    extensions:   const [AppThemeExtension.dark],
  );
}
```

### theme_provider.dart

```dart
// design_system/theme/theme_provider.dart
part 'theme_provider.g.dart';

@riverpod
class ThemeModeNotifier extends _$ThemeModeNotifier {
  @override
  ThemeMode build() => ThemeMode.system;

  void setLight()  => state = ThemeMode.light;
  void setDark()   => state = ThemeMode.dark;
  void setSystem() => state = ThemeMode.system;
  void toggle()    => state = state == ThemeMode.dark
      ? ThemeMode.light
      : ThemeMode.dark;
}

// In app.dart:
//   themeMode: ref.watch(themeModeProvider)   // `Notifier` suffix is stripped
```

---

## Design System — Components Barrel

```dart
// design_system/components/components.dart
/// Barrel export for all shared design system components.
/// Import this single file from feature screens — never import component files directly.
export 'buttons/app_button.dart';
export 'inputs/app_text_field.dart';
export 'cards/app_card.dart';
export 'dialogs/app_dialog.dart';
export 'loaders/app_shimmer.dart';
```

**Component file placement rule:** All shared UI primitives (buttons, inputs, cards, dialogs, loaders) live in `design_system/components/<category>/`. Feature-specific widgets that are not reused across features live in `features/<name>/presentation/widgets/`. Never put shared components inside a feature folder.

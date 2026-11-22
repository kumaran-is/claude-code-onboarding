# Flutter Testing Patterns

Complete testing reference for Flutter 3.41 + Riverpod 3.x + mocktail + Dart 3.4+.
Covers all layers: unit, widget, golden, and integration.

## 1. Testing Pyramid

| Layer | Tool | When to Use | Coverage Target |
|-------|------|-------------|-----------------|
| **Unit** | `flutter_test` + `mocktail` | Use cases, repositories, providers, pure logic | 80%+ of domain and data layers |
| **Widget** | `flutter_test` + `ProviderScope` | Screens, stateful widgets, loading/error/data states | Every screen, every major state |
| **Golden** | `flutter_test` golden API | Visual regression, design system tokens, theme variants | Shared components and key screens; baseline via `--update-goldens`, see §5 |
| **Integration** | `integration_test` (in-process, on a device) | Real router/shell with provider overrides; services working together | App boots, primary navigation, cold-start routing |
| **E2E** | Maestro (black-box on the built app) | Full user journeys on a real device/emulator | Critical flows: login, core CRUD |

Run fast layers first. Unit tests must never make network calls or touch real services. Tier responsibilities and
Maestro conventions: [flutter-e2e-maestro.md](flutter-e2e-maestro.md). Tests that pass vacuously, determinism and flake
handling: [flutter-testing-traps.md](flutter-testing-traps.md).

---

## 2. Unit Tests — Use Case with mocktail

Tests the domain layer in isolation. The use case depends on an `AuthRepository` interface;
the test provides a `FakeAuthRepository` that satisfies the interface without touching Firebase.

File: `test/unit/features/auth/usecases/sign_in_usecase_test.dart`

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:your_app/core/errors/app_exception.dart';
import 'package:your_app/core/result/result.dart';
import 'package:your_app/features/auth/domain/entities/user.dart';
import 'package:your_app/features/auth/domain/repositories/auth_repository.dart';
import 'package:your_app/features/auth/domain/usecases/sign_in_usecase.dart';

// --- Fake (in test/helpers/fakes/ — see section 6) ---
class FakeAuthRepository extends Fake implements AuthRepository {
  // Overrides declared per-test via mocktail stubs
}

// Register fallback values for any custom types used in argument matchers
class FakeUser extends Fake implements User {}

void main() {
  late FakeAuthRepository fakeRepo;
  late SignInUseCase useCase;

  setUpAll(() {
    registerFallbackValue(FakeUser());
  });

  setUp(() {
    fakeRepo = FakeAuthRepository();
    useCase = SignInUseCase(fakeRepo);
  });

  group('SignInUseCase', () {
    const email = 'alice@example.com';
    const password = 'secret123';

    group('success path', () {
      test('returns Success(User) when repository succeeds', () async {
        final expectedUser = User(
          id: 'uid-1',
          email: email,
          displayName: 'Alice',
          createdAt: DateTime(2025),
        );

        when(
          () => fakeRepo.signIn(email: email, password: password),
        ).thenAnswer((_) async => Success(expectedUser));

        final result = await useCase(email: email, password: password);

        expect(result, isA<Success<User>>());
        expect((result as Success<User>).value, equals(expectedUser));
        verify(() => fakeRepo.signIn(email: email, password: password))
            .called(1);
      });
    });

    group('failure path', () {
      test('propagates NetworkException from repository', () async {
        final exception = NetworkException('No internet');

        when(
          () => fakeRepo.signIn(email: email, password: password),
        ).thenAnswer((_) async => Failure(exception));

        final result = await useCase(email: email, password: password);

        expect(result, isA<Failure<User>>());
        expect((result as Failure<User>).error, isA<NetworkException>());
        expect((result).error.message, equals('No internet'));
      });

      test('propagates AuthException when credentials are invalid', () async {
        final exception = AuthException('Invalid credentials');

        when(
          () => fakeRepo.signIn(email: email, password: password),
        ).thenAnswer((_) async => Failure(exception));

        final result = await useCase(email: email, password: password);

        expect(result, isA<Failure<User>>());
        expect((result as Failure<User>).error, isA<AuthException>());
      });
    });
  });
}
```

**Rules for use case tests:**
- One `group()` per use case class.
- Nest `group('success path', ...)` and `group('failure path', ...)` inside.
- Always call `verify(...)` on the happy path to confirm the method was invoked.
- Never instantiate Firebase or real HTTP clients.

---

## 3. Unit Tests — AsyncNotifier with mocktail

Tests a Riverpod `AsyncNotifier` via `ProviderContainer`. No widget tree needed.

File: `test/unit/features/auth/providers/auth_provider_test.dart`

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:your_app/core/errors/app_exception.dart';
import 'package:your_app/core/result/result.dart';
import 'package:your_app/features/auth/domain/entities/user.dart';
import 'package:your_app/features/auth/domain/repositories/auth_repository.dart';
import 'package:your_app/features/auth/presentation/providers/auth_provider.dart';

class FakeAuthRepository extends Fake implements AuthRepository {}

void main() {
  late FakeAuthRepository fakeRepo;

  setUp(() {
    fakeRepo = FakeAuthRepository();
  });

  ProviderContainer makeContainer() {
    final container = ProviderContainer(
      overrides: [
        authRepositoryProvider.overrideWithValue(fakeRepo),
      ],
    );
    // Always dispose — prevents state leaking between tests
    addTearDown(container.dispose);
    return container;
  }

  group('AuthProvider', () {
    group('build()', () {
      test('initial state is unauthenticated when no session exists', () async {
        when(() => fakeRepo.currentUser()).thenReturn(null);

        final container = makeContainer();
        // Reading the provider triggers build()
        final state = container.read(authProvider);

        expect(state, const AuthState.unauthenticated());
      });

      test('initial state is authenticated when session exists', () async {
        final user = User(
          id: 'uid-1',
          email: 'alice@example.com',
          displayName: 'Alice',
          createdAt: DateTime(2025),
        );
        when(() => fakeRepo.currentUser()).thenReturn(user);

        final container = makeContainer();
        final state = container.read(authProvider);

        expect(state, AuthState.authenticated(user));
      });
    });

    group('signIn()', () {
      test('transitions loading -> authenticated on success', () async {
        when(() => fakeRepo.currentUser()).thenReturn(null);

        final user = User(
          id: 'uid-2',
          email: 'bob@example.com',
          displayName: 'Bob',
          createdAt: DateTime(2025),
        );
        when(
          () => fakeRepo.signIn(
            email: 'bob@example.com',
            password: 'pass',
          ),
        ).thenAnswer((_) async => Success(user));

        final container = makeContainer();
        final notifier = container.read(authProvider.notifier);

        // Collect state transitions
        final states = <AuthState>[];
        container.listen(authProvider, (_, next) => states.add(next));

        await notifier.signIn(email: 'bob@example.com', password: 'pass');

        expect(states, [
          const AuthState.loading(),
          AuthState.authenticated(user),
        ]);
      });

      test('transitions loading -> error on failure', () async {
        when(() => fakeRepo.currentUser()).thenReturn(null);
        when(
          () => fakeRepo.signIn(
            email: any(named: 'email'),
            password: any(named: 'password'),
          ),
        ).thenAnswer((_) async => Failure(AuthException('Bad credentials')));

        final container = makeContainer();
        final notifier = container.read(authProvider.notifier);

        final states = <AuthState>[];
        container.listen(authProvider, (_, next) => states.add(next));

        await notifier.signIn(email: 'x@x.com', password: 'wrong');

        expect(states.first, const AuthState.loading());
        // AuthState is a sealed/freezed union: read the error arm through its public API.
        // (Never reference generated private subclasses such as `_Error` from a test.)
        expect(
          states.last.maybeWhen(error: (msg) => msg, orElse: () => null),
          contains('Bad credentials'),
        );
      });
    });
  });
}
```

**Key patterns:**
- `makeContainer()` factory + `addTearDown(container.dispose)` — always tear down.
- `container.listen()` to capture state transitions in a list — more reliable than polling.
- Never call `container.read(authProvider.notifier)` before setting up the listener.

---

## 4. Widget Tests — Screen with ProviderScope

Tests the full screen widget with Riverpod providers overridden. Does not require a real device.

File: `test/widget/features/auth/screens/login_screen_test.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:your_app/features/auth/domain/entities/user.dart';
import 'package:your_app/features/auth/presentation/providers/auth_provider.dart';
import 'package:your_app/features/auth/presentation/screens/login_screen.dart';

import '../../../../helpers/pump_app.dart';
import '../../../../helpers/fakes/fake_auth_notifier.dart';

void main() {
  group('LoginScreen', () {
    testWidgets('shows CircularProgressIndicator while loading', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authProvider.overrideWith(
              () => FakeAuthNotifier(const AuthState.loading()),
            ),
          ],
          child: const MaterialApp(home: LoginScreen()),
        ),
      );

      // pump() — single frame, does NOT settle animations
      // Use pump() when you want to inspect mid-animation state
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.byType(ElevatedButton), findsNothing);
    });

    testWidgets('shows error banner when state is error', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authProvider.overrideWith(
              () => FakeAuthNotifier(
                const AuthState.error('Invalid credentials'),
              ),
            ),
          ],
          child: const MaterialApp(home: LoginScreen()),
        ),
      );

      // pumpAndSettle() — runs frames until no more scheduled, settles animations
      // Use pumpAndSettle() for normal rendering where you expect a stable frame
      await tester.pumpAndSettle();

      expect(find.text('Invalid credentials'), findsOneWidget);
      expect(find.byType(ElevatedButton), findsOneWidget);
    });

    testWidgets('shows email field and sign in button when unauthenticated',
        (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authProvider.overrideWith(
              () => FakeAuthNotifier(const AuthState.unauthenticated()),
            ),
          ],
          child: const MaterialApp(home: LoginScreen()),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.byKey(const Key('email_field')), findsOneWidget);
      expect(find.byKey(const Key('password_field')), findsOneWidget);
      expect(find.byKey(const Key('sign_in_button')), findsOneWidget);
    });

    testWidgets('calls signIn on button tap', (tester) async {
      final fakeNotifier = FakeAuthNotifier(const AuthState.unauthenticated());

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authProvider.overrideWith(() => fakeNotifier),
          ],
          child: const MaterialApp(home: LoginScreen()),
        ),
      );

      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const Key('email_field')),
        'alice@example.com',
      );
      await tester.enterText(
        find.byKey(const Key('password_field')),
        'secret123',
      );
      await tester.tap(find.byKey(const Key('sign_in_button')));
      await tester.pumpAndSettle();

      expect(fakeNotifier.signInCallCount, 1);
      expect(fakeNotifier.lastEmail, 'alice@example.com');
    });
  });
}
```

**`pump()` vs `pumpAndSettle()` guidance:**

| Method | Behavior | Use When |
|--------|----------|----------|
| `pump()` | Runs one frame | Inspecting mid-animation or loading states that will loop forever (e.g. `CircularProgressIndicator`) |
| `pump(Duration)` | Runs frames up to duration | Stepping through timed animations |
| `pumpAndSettle()` | Runs frames until idle | Normal rendering of stable UI; will timeout if animations loop |

Avoid `pumpAndSettle()` on screens with infinite animations (skeleton shimmer, spinners) — use `pump()` there.

---

## 5. Golden Tests — Visual Regression

Golden tests capture a widget as a PNG and compare it on later runs. Use them for shared components,
design tokens and theme variants, not for every screen (widget tests cover behaviour; goldens are costly to review).
Determinism rules (fonts, cross-platform tolerance, update policy) are in [flutter-testing-traps.md](flutter-testing-traps.md) §6.

File: `test/golden/features/auth/login_screen_golden_test.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:your_app/features/auth/presentation/providers/auth_provider.dart';
import 'package:your_app/features/auth/presentation/screens/login_screen.dart';

import '../../helpers/fakes/fake_auth_notifier.dart';

void main() {
  const testSize = Size(390, 844); // fixed surface: the render must not depend on the machine

  for (final (name, theme) in [('light', ThemeData.light()), ('dark', ThemeData.dark())]) {
    testWidgets('login screen, unauthenticated, $name theme', (tester) async {
      tester.view.physicalSize = testSize;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authProvider.overrideWith(
              () => FakeAuthNotifier(const AuthState.unauthenticated()),
            ),
          ],
          child: MaterialApp(theme: theme, home: const LoginScreen()),
        ),
      );
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(LoginScreen),
        matchesGoldenFile('goldens/login_screen_$name.png'),
      );
    });
  }
}
```

Each iteration is its own `testWidgets` with its own pump, so the element-reuse trap
([traps](flutter-testing-traps.md) §2) does not apply here.

**Golden workflow:**

```bash
flutter test test/golden/ --update-goldens   # first run, or after an INTENTIONAL visual change only
flutter test test/golden/                    # compare against the committed baseline
git add test/golden/goldens/ && git commit -m "test: update golden baselines after [reason]"
```

`matchesGoldenFile` ships with `flutter_test`; no extra dependency is needed. Paths are relative to the
test file. Commit the PNGs: they are the source of truth. `golden_toolkit` is **discontinued** on pub.dev
(last release 0.15.0, 2023-02): do not add it. For cross-platform tolerance or multi-scenario goldens use
`alchemist` (traps §6).

---

## 6. Repository Fake Pattern (mocktail)

All fakes live in `test/helpers/fakes/` and are imported by test files.
Never define a `Fake` inline inside a test file — it must be reusable.

File: `test/helpers/fakes/fake_auth_repository.dart`

```dart
import 'package:mocktail/mocktail.dart';
import 'package:your_app/core/result/result.dart';
import 'package:your_app/features/auth/domain/entities/user.dart';
import 'package:your_app/features/auth/domain/repositories/auth_repository.dart';

/// Fake implementation of [AuthRepository] backed by mocktail stubs.
/// Configure stubs in each test with `when(() => fake.method()).thenAnswer(...)`.
class FakeAuthRepository extends Fake implements AuthRepository {}
```

File: `test/helpers/fakes/fake_auth_notifier.dart`

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:your_app/features/auth/presentation/providers/auth_provider.dart';

/// A notifier that starts with a preset state and records method calls.
/// Use this in widget tests to drive specific UI states without real auth logic.
class FakeAuthNotifier extends AuthNotifier {
  FakeAuthNotifier(this._initial);

  final AuthState _initial;
  int signInCallCount = 0;
  String? lastEmail;

  @override
  AuthState build() => _initial;

  @override
  Future<void> signIn({required String email, required String password}) async {
    signInCallCount++;
    lastEmail = email;
    // Subclasses can override to simulate state changes
  }
}
```

**Configuring stubs in a test:**

```dart
// Success stub
when(
  () => fakeRepo.signIn(
    email: 'alice@example.com',
    password: 'secret123',
  ),
).thenAnswer((_) async => Success(testUser));

// Failure stub — throws the exception wrapped in Failure
when(
  () => fakeRepo.signIn(
    email: any(named: 'email'),
    password: any(named: 'password'),
  ),
).thenAnswer((_) async => Failure(NetworkException('No internet')));

// Stub that throws directly (for catching in try/catch paths)
when(
  () => fakeRepo.getProfile(),
).thenThrow(UnauthorizedException('Token expired'));
```

---

## 7. Test Helpers

### JSON Fixture Loader

File: `test/helpers/fixtures/fixture_reader.dart`

```dart
import 'dart:io';

/// Reads a JSON fixture file from test/helpers/fixtures/<name>.
///
/// Usage:
///   final json = fixture('user.json');
String fixture(String name) {
  return File('test/helpers/fixtures/$name').readAsStringSync();
}
```

Reading a checked-in fixture is the one allowed file access (it is local, read-only and deterministic). The path is
relative to the working directory, so run `flutter test` from the package root, not from a monorepo root.

Place fixture JSON files alongside the loader:
`test/helpers/fixtures/user.json`, `test/helpers/fixtures/workout_list.json`, etc.

### Entity Factory

File: `test/helpers/factories/user_factory.dart`

```dart
import 'package:your_app/features/auth/domain/entities/user.dart';

/// Creates a [User] with sensible defaults for tests.
/// Override only the fields your test cares about.
///
/// Usage:
///   final user = createTestUser();
///   final admin = createTestUser(id: 'admin-1', displayName: 'Admin');
User createTestUser({
  String id = 'test-uid-1',
  String email = 'alice@example.com',
  String displayName = 'Alice',
  DateTime? createdAt,
}) {
  return User(
    id: id,
    email: email,
    displayName: displayName,
    createdAt: createdAt ?? DateTime(2025, 1, 1),
  );
}
```

### `pumpApp()` Helper

Wraps a widget with `ProviderScope` + `MaterialApp` + `GoRouter` so every widget test
starts from the same baseline without repeating boilerplate.

File: `test/helpers/pump_app.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Pumps [child] inside a full app shell (ProviderScope + MaterialApp).
///
/// Pass [overrides] to replace providers with fakes.
/// Pass [theme] to test a specific theme variant.
///
/// Usage:
///   await tester.pumpApp(
///     const LoginScreen(),
///     overrides: [authProvider.overrideWith(() => FakeAuthNotifier(...))],
///   );
extension PumpApp on WidgetTester {
  Future<void> pumpApp(
    Widget child, {
    List<Override> overrides = const [],
    ThemeData? theme,
    Key? key, // pass a distinct key when pumping twice in one test (traps §2)
  }) async {
    await pumpWidget(
      ProviderScope(
        key: key,
        overrides: overrides,
        child: MaterialApp(
          theme: theme ?? ThemeData.light(),
          home: child,
        ),
      ),
    );
  }
}
```

Usage in tests:

```dart
await tester.pumpApp(
  const LoginScreen(),
  overrides: [
    authProvider.overrideWith(() => FakeAuthNotifier(const AuthState.unauthenticated())),
  ],
);
await tester.pumpAndSettle();
```

---

## 8. Rules

**Test coverage requirements:**
- Every use case MUST have a unit test covering the success path and at least one failure path.
- Every screen MUST have at least one widget test covering the primary data state.
- Screens with loading and error states MUST test each state explicitly.

**Fake placement:**
- All `Fake` and `Mock` classes go in `test/helpers/fakes/` — never inline in test files.
- All factory methods go in `test/helpers/factories/` — never inline in test files.

**No real I/O:**
- Unit and widget tests MUST NOT make real network calls, write to disk, or touch Firebase or other real services (reading checked-in fixtures is fine).
- Override every provider that touches a real service with a fake.

**Run commands:**

```bash
# Run all tests
flutter test

# Run unit tests only
flutter test test/unit/

# Run widget tests only
flutter test test/widget/

# Run golden tests (compare against baseline)
flutter test test/golden/

# Regenerate golden baselines (after intentional visual change)
flutter test test/golden/ --update-goldens

# Run a single test file
flutter test test/unit/features/auth/usecases/sign_in_usecase_test.dart

# Run with coverage report
flutter test --coverage
genhtml coverage/lcov.info -o coverage/html
open coverage/html/index.html
```

**Folder layout:**

```
test/
  unit/
    features/
      auth/
        usecases/
          sign_in_usecase_test.dart
        providers/
          auth_provider_test.dart
  widget/
    features/
      auth/
        screens/
          login_screen_test.dart
  golden/
    features/
      auth/
        login_screen_golden_test.dart
        goldens/
          login_screen_light.png
          login_screen_dark.png
  helpers/
    fakes/
      fake_auth_repository.dart
      fake_auth_notifier.dart
    factories/
      user_factory.dart
    fixtures/
      fixture_reader.dart
      user.json
    pump_app.dart
```

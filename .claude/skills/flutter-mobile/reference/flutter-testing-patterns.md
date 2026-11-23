# Flutter Testing Patterns

Testing reference for Flutter 3.50.1 / Dart 3.14.0 + Riverpod 3.5 + mocktail 1.0.5, with `material_ui` 1.11.1 as the
Material import (`package:flutter/material.dart` is deprecated since 3.47). Covers unit, widget, golden and integration.
Every snippet in §2–§7 compiles and passes on Flutter 3.50.1 (format 0, analyze 0 issues, 13/13 tests), and each test
fails when the behaviour it guards is broken (2026-11-23). The examples assume a sealed `AuthState`
(`AuthState.unauthenticated/loading/authenticated(user)/error(message)` with value equality, hand-written or freezed);
they read it with Dart patterns, never generated `when`/`maybeWhen` helpers.

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

Tests the domain layer in isolation. The use case depends on an `AuthRepository` interface; the test drives a
mocktail **`Mock`** of it. Stubbing needs `Mock`: `when()` on a class that `extends Fake` throws
`UnimplementedError` (tested), so `Fake` is only for hand-written fakes and `registerFallbackValue` arguments.

File: `test/helpers/fakes/mock_auth_repository.dart`

```dart
import 'package:mocktail/mocktail.dart';
import 'package:your_app/features/auth/domain/repositories/auth_repository.dart';

/// mocktail mock of [AuthRepository]. Stub per test with `when(() => repo.method()).thenAnswer(...)`.
/// It must extend `Mock`: `when()` on a `Fake` subclass throws UnimplementedError.
class MockAuthRepository extends Mock implements AuthRepository {}
```

File: `test/unit/features/auth/usecases/sign_in_usecase_test.dart`

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:your_app/core/errors/app_exception.dart';
import 'package:your_app/core/result/result.dart';
import 'package:your_app/features/auth/domain/entities/user.dart';
import 'package:your_app/features/auth/domain/usecases/sign_in_usecase.dart';

import '../../../../helpers/fakes/mock_auth_repository.dart';

void main() {
  late MockAuthRepository repository;
  late SignInUseCase useCase;

  setUp(() {
    repository = MockAuthRepository();
    useCase = SignInUseCase(repository);
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
        when(() => repository.signIn(email: email, password: password))
            .thenAnswer((_) async => Success(expectedUser));

        final result = await useCase(email: email, password: password);

        expect(result, isA<Success<User>>());
        expect((result as Success<User>).value, equals(expectedUser));
        verify(() => repository.signIn(email: email, password: password))
            .called(1);
      });
    });

    group('failure path', () {
      test('propagates NetworkException from repository', () async {
        when(() => repository.signIn(email: email, password: password))
            .thenAnswer(
              (_) async => const Failure(NetworkException('No internet')),
            );

        final result = await useCase(email: email, password: password);

        expect(result, isA<Failure<User>>());
        final error = (result as Failure<User>).error;
        expect(error, isA<NetworkException>());
        expect(error.message, equals('No internet'));
      });

      test('propagates AuthException when credentials are invalid', () async {
        when(() => repository.signIn(email: email, password: password))
            .thenAnswer(
              (_) async => const Failure(AuthException('Invalid credentials')),
            );

        final result = await useCase(email: email, password: password);

        expect((result as Failure<User>).error, isA<AuthException>());
      });
    });
  });
}
```

**Rules for use case tests:**
- One `group()` per use case class, with `group('success path', ...)` and `group('failure path', ...)` inside.
- Always call `verify(...)` on the happy path to confirm the method was invoked with the right arguments.
- `registerFallbackValue(...)` is needed only when `any()` matches a custom type; `any(named: ...)` on `String` needs none.
- Never instantiate Firebase or real HTTP clients.

---

## 3. Unit Tests — Notifier with mocktail

Tests a Riverpod `Notifier` through a `ProviderContainer`. No widget tree needed. `ProviderContainer.test()`
(Riverpod 3) disposes itself at the end of the test, so no manual `addTearDown(container.dispose)`.

File: `test/unit/features/auth/providers/auth_provider_test.dart`

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:your_app/core/errors/app_exception.dart';
import 'package:your_app/core/result/result.dart';
import 'package:your_app/features/auth/domain/entities/user.dart';
import 'package:your_app/features/auth/presentation/providers/auth_provider.dart';

import '../../../../helpers/fakes/mock_auth_repository.dart';

void main() {
  late MockAuthRepository repository;

  setUp(() => repository = MockAuthRepository());

  // ProviderContainer.test() registers its own dispose with addTearDown.
  ProviderContainer makeContainer() => ProviderContainer.test(
    overrides: [authRepositoryProvider.overrideWithValue(repository)],
  );

  group('AuthNotifier', () {
    group('build()', () {
      test('initial state is unauthenticated when no session exists', () {
        when(() => repository.currentUser()).thenReturn(null);

        final container = makeContainer();

        expect(container.read(authProvider), const AuthState.unauthenticated());
      });

      test('initial state is authenticated when a session exists', () {
        final user = User(
          id: 'uid-1',
          email: 'alice@example.com',
          displayName: 'Alice',
          createdAt: DateTime(2025),
        );
        when(() => repository.currentUser()).thenReturn(user);

        final container = makeContainer();

        expect(container.read(authProvider), AuthState.authenticated(user));
      });
    });

    group('signIn()', () {
      test('transitions loading -> authenticated on success', () async {
        final user = User(
          id: 'uid-2',
          email: 'bob@example.com',
          displayName: 'Bob',
          createdAt: DateTime(2025),
        );
        when(() => repository.currentUser()).thenReturn(null);
        when(
          () => repository.signIn(email: 'bob@example.com', password: 'pass'),
        ).thenAnswer((_) async => Success(user));

        final container = makeContainer();
        // Listen BEFORE acting, so the first transition is captured.
        final states = <AuthState>[];
        container.listen(authProvider, (_, next) => states.add(next));

        await container
            .read(authProvider.notifier)
            .signIn(email: 'bob@example.com', password: 'pass');

        expect(states, [
          const AuthState.loading(),
          AuthState.authenticated(user),
        ]);
      });

      test('transitions loading -> error on failure', () async {
        when(() => repository.currentUser()).thenReturn(null);
        when(
          () => repository.signIn(
            email: any(named: 'email'),
            password: any(named: 'password'),
          ),
        ).thenAnswer(
          (_) async => const Failure(AuthException('Bad credentials')),
        );

        final container = makeContainer();
        final states = <AuthState>[];
        container.listen(authProvider, (_, next) => states.add(next));

        await container
            .read(authProvider.notifier)
            .signIn(email: 'x@x.com', password: 'wrong');

        expect(states.first, const AuthState.loading());
        // Read the error arm with a pattern on the sealed state, never a generated private subclass.
        expect(
          states.last,
          isA<AuthError>().having(
            (e) => e.message,
            'message',
            'Bad credentials',
          ),
        );
      });
    });
  });
}
```

**Key patterns:**
- `ProviderContainer.test(overrides: ...)` per test: no state leaks between tests.
- `container.listen()` collects state transitions in a list; set it up **before** calling the notifier method, or the
  first transition (`loading`) is missed.
- Assert the error arm with `isA<AuthError>().having(...)` (or a `switch` pattern), not generated private classes.

---

## 4. Widget Tests — Screen with ProviderScope

Tests the full screen widget with Riverpod providers overridden. Does not require a real device.
`find.byType(ElevatedButton)` matches the `material_ui` class, so the screen and the test must import the same library.

File: `test/widget/features/auth/screens/login_screen_test.dart`

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:your_app/core/keys/widget_keys.dart';
import 'package:your_app/features/auth/presentation/providers/auth_provider.dart';
import 'package:your_app/features/auth/presentation/screens/login_screen.dart';

import '../../../../helpers/fakes/fake_auth_notifier.dart';
import '../../../../helpers/pump_app.dart';

void main() {
  group('LoginScreen', () {
    testWidgets('shows CircularProgressIndicator while loading', (
      tester,
    ) async {
      await tester.pumpApp(
        const LoginScreen(),
        overrides: [
          authProvider.overrideWith(
            () => FakeAuthNotifier(const AuthState.loading()),
          ),
        ],
      );
      // pump(): one frame. A spinner never settles, so pumpAndSettle() would time out here.
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.byType(ElevatedButton), findsNothing);
    });

    testWidgets('shows the error message when state is error', (tester) async {
      await tester.pumpApp(
        const LoginScreen(),
        overrides: [
          authProvider.overrideWith(
            () =>
                FakeAuthNotifier(const AuthState.error('Invalid credentials')),
          ),
        ],
      );
      await tester.pumpAndSettle();

      expect(find.text('Invalid credentials'), findsOneWidget);
      expect(find.byType(ElevatedButton), findsOneWidget);
    });

    testWidgets('calls signIn with the entered email on tap', (tester) async {
      final notifier = FakeAuthNotifier(const AuthState.unauthenticated());
      await tester.pumpApp(
        const LoginScreen(),
        overrides: [authProvider.overrideWith(() => notifier)],
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(WidgetKeys.emailField),
        'alice@example.com',
      );
      await tester.enterText(find.byKey(WidgetKeys.passwordField), 'secret123');
      await tester.tap(find.byKey(WidgetKeys.signInButton));
      await tester.pumpAndSettle();

      expect(notifier.signInCallCount, 1);
      expect(notifier.lastEmail, 'alice@example.com');
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
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:your_app/features/auth/presentation/providers/auth_provider.dart';
import 'package:your_app/features/auth/presentation/screens/login_screen.dart';

import '../../../helpers/fakes/fake_auth_notifier.dart';
import '../../../helpers/pump_app.dart';

void main() {
  const testSize = Size(
    390,
    844,
  ); // fixed surface: the render must not depend on the machine

  for (final (name, theme) in [
    ('light', ThemeData.light()),
    ('dark', ThemeData.dark()),
  ]) {
    testWidgets('login screen, unauthenticated, $name theme', (tester) async {
      tester.view.physicalSize = testSize;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpApp(
        const LoginScreen(),
        theme: theme,
        overrides: [
          authProvider.overrideWith(
            () => FakeAuthNotifier(const AuthState.unauthenticated()),
          ),
        ],
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
([traps](flutter-testing-traps.md) §2) does not apply here. Changing one padding value by 1 px fails both
goldens (`Pixel test failed, 1.04%`).

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

## 6. Mocks and Fakes (mocktail)

All mocks and fakes live in `test/helpers/fakes/` and are imported by test files; never define one inline in a test
file. Use a `Mock` (§2) when the test stubs or verifies calls; use a hand-written subclass when a widget test needs a
preset state and a call record:

File: `test/helpers/fakes/fake_auth_notifier.dart`

```dart
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
  }
}
```

mockito 5.8.1 with `@GenerateNiceMocks([MockSpec<T>()])` also works on 3.50.1, but its codegen needs
`build_runner` 2.16.2 (2.17.1 requires `build` 5, which mockito 5.8.1 does not allow). Prefer mocktail: no codegen.

**Configuring stubs in a test:**

```dart
// Success stub
when(
  () => repository.signIn(email: 'alice@example.com', password: 'secret123'),
).thenAnswer((_) async => Success(testUser));

// Failure stub: the error travels inside Failure
when(
  () => repository.signIn(
    email: any(named: 'email'),
    password: any(named: 'password'),
  ),
).thenAnswer((_) async => const Failure(NetworkException('No internet')));

// Stub that throws directly (for try/catch paths)
when(() => repository.getProfile()).thenThrow(const UnauthorizedException('Token expired'));
```

---

## 7. Test Helpers

### JSON Fixture Loader

File: `test/helpers/fixtures/fixture_reader.dart`

```dart
import 'dart:io';

/// Reads a JSON fixture file from `test/helpers/fixtures/<name>`.
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

Wraps a widget with `ProviderScope` + `MaterialApp` so every widget test
starts from the same baseline without repeating boilerplate.

File: `test/helpers/pump_app.dart`

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

/// Pumps [child] inside a full app shell (ProviderScope + MaterialApp).
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
        child: MaterialApp(theme: theme ?? ThemeData.light(), home: child),
      ),
    );
  }
}
```

`Override` is exported from `package:flutter_riverpod/misc.dart` in Riverpod 3, not from the main library.

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


### Robot pattern (page objects) for screen widget tests

A Robot keeps every finder, tap and assertion for one screen in one class, so test bodies read as intent (`robot.enterEmail(...)`, `robot.tapSignIn()`). When a widget moves or a key changes, you fix one Robot instead of every test.

| Test type | Use a Robot? |
|---|---|
| Screen widget tests with several interactions | Yes |
| Single shared-component (atom) tests | No: `find.byType` / `find.text` is enough |
| Use-case and notifier unit tests | No: there is no widget tree |

**Placement.** Robots import `package:flutter_test`, so they are test code: `test/helpers/robots/`, never a package's `lib/` (that would ship the test framework in the app). Dart cannot import another package's `test/` directory, so helpers shared by 3+ packages (`pumpApp`, base Robot, fakes) go in a dev-only `test_support` package used as a `dev_dependency`. Widget `Key` constants contain no test imports, so they can live in `lib/` (for example `lib/core/keys/widget_keys.dart`, or the shared UI package for shared screens).

**Finder priority:**

1. `find.bySemanticsLabel(...)` / `find.byTooltip(...)`: they reuse the accessibility labels the screen must have anyway, so the test also fails when accessibility regresses. Maestro matches on the same labels.
2. `find.byKey(WidgetKeys.x)` from a central keys class: for unlabelled or repeated widgets where `byType` is ambiguous (two text fields, several primary buttons). Never inline `Key('...')` strings.
3. `find.text(...)`: only to assert visible copy, never to tap a control whose label is localised.

Never tap via `find.byType(SomeButton)` when the screen has more than one. It is the most common source of flaky Robot tests.

File: `test/helpers/robots/login_robot.dart` (keys from `lib/core/keys/widget_keys.dart`)

```dart
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:your_app/core/keys/widget_keys.dart';
import 'package:your_app/features/auth/presentation/screens/login_screen.dart';

import '../pump_app.dart';

class LoginRobot {
  LoginRobot(this.tester);
  final WidgetTester tester;

  Future<LoginRobot> pump({List<Override> overrides = const []}) async {
    await tester.pumpApp(const LoginScreen(), overrides: overrides);
    await tester.pumpAndSettle();
    return this;
  }

  Future<void> enterEmail(String v) =>
      tester.enterText(find.byKey(WidgetKeys.emailField), v);
  Future<void> enterPassword(String v) =>
      tester.enterText(find.byKey(WidgetKeys.passwordField), v);
  Future<void> tapSignIn() async {
    await tester.tap(find.bySemanticsLabel('Sign in'));
    await tester.pumpAndSettle();
  }

  // Symmetry rule: every "visible" assertion has a "not visible" twin.
  void expectError(String msg) => expect(find.text(msg), findsOneWidget);
  void expectNoError(String msg) => expect(find.text(msg), findsNothing);
}
```

File: `test/widget/features/auth/screens/login_robot_test.dart`

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:your_app/core/errors/app_exception.dart';
import 'package:your_app/core/result/result.dart';
import 'package:your_app/features/auth/presentation/providers/auth_provider.dart';
import 'package:mocktail/mocktail.dart';

import '../../../../helpers/fakes/mock_auth_repository.dart';
import '../../../../helpers/robots/login_robot.dart';

void main() {
  testWidgets('should show an error when sign in fails', (tester) async {
    final repository = MockAuthRepository();
    when(() => repository.currentUser()).thenReturn(null);
    when(
      () => repository.signIn(
        email: any(named: 'email'),
        password: any(named: 'password'),
      ),
    ).thenAnswer(
      (_) async => const Failure(AuthException('Invalid credentials')),
    );

    final robot = await LoginRobot(
      tester,
    ).pump(overrides: [authRepositoryProvider.overrideWithValue(repository)]);
    robot.expectNoError('Invalid credentials'); // before
    await robot.enterEmail('a@example.com');
    await robot.enterPassword('wrong');
    await robot.tapSignIn();
    robot.expectError('Invalid credentials'); // after
  });
}
```

**Symmetry rule (mandatory).** Every `expectXVisible` has an `expectXNotVisible`, and a flow test asserts the state **before** and **after** the action. This catches an assertion that passed because the widget was already there, or never changed.

Conventions: name tests `should <behaviour> when <condition>`; lay each body out as Arrange → Act → Assert; one Robot per screen, never copied between apps; stub both `state` and `stream` on fakes so `pumpAndSettle()` cannot hang. Device UI/E2E flows are Maestro, not `integration_test` Robots: see [flutter-e2e-maestro.md](flutter-e2e-maestro.md).
---

## 8. Rules

**Test coverage requirements:**
- Every use case MUST have a unit test covering the success path and at least one failure path.
- Every screen MUST have at least one widget test covering the primary data state.
- Screens with loading and error states MUST test each state explicitly.

**Fake placement:**
- All `Fake` and `Mock` classes go in `test/helpers/fakes/` — never inline in test files. Stubbed classes extend `Mock`.
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
      mock_auth_repository.dart
      fake_auth_notifier.dart
    robots/
      login_robot.dart
    factories/
      user_factory.dart
    fixtures/
      fixture_reader.dart
      user.json
    pump_app.dart
```

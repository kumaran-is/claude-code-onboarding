# TDD Patterns — Flutter / Dart (flutter_test + mocktail)

Flutter 3.50.1 / Dart 3.14.0, Riverpod 3.5, mocktail 1.0.5, fake_async 1.3.3, Material from `material_ui` 1.11.1.
Each test below compiles and passes on 3.50.1 against a small `user` feature (`UserApi`, `UserRepository`,
`UserFormScreen`, an `AsyncNotifier` family, `startRetrying`), and fails when that behaviour is broken (2026-11-23).
Full layer-by-layer reference: `flutter-mobile/reference/flutter-testing-patterns.md`.

## Test Structure (Unit — Repository/Service)

```dart
// test/features/user/data/user_repository_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:your_app/features/user/user.dart';

class MockUserApi extends Mock implements UserApi {}

class FakeCreateUserDto extends Fake implements CreateUserDto {}

void main() {
  late UserRepository repository;
  late MockUserApi mockApi;

  setUpAll(
    () => registerFallbackValue(FakeCreateUserDto()),
  ); // any() on a custom type

  setUp(() {
    mockApi = MockUserApi();
    repository = UserRepository(api: mockApi);
  });

  group('UserRepository.createUser', () {
    test('throws ConflictException when email already exists', () async {
      // ARRANGE
      // A Future-returning API fails asynchronously: thenAnswer + throw. thenThrow would throw
      // synchronously, before expectLater ever receives a Future.
      when(() => mockApi.createUser(any())).thenAnswer(
        (_) async => throw const ConflictException('Email already exists'),
      );

      // ACT + ASSERT: await the Future matcher so the test cannot finish first
      await expectLater(
        repository.createUser(const CreateUserDto(email: 'taken@example.com')),
        throwsA(isA<ConflictException>()),
      );
      verify(() => mockApi.createUser(any())).called(1);
    });
  });
}
```

`thenThrow` on a `Future`-returning method throws **synchronously**: `expectLater(repository.createUser(...), throwsA(...))`
then fails even when the code is right, because the call throws before `expectLater` receives a Future (tested). Stub
async failures with `thenAnswer((_) async => throw ...)`, or pass a closure: `expectLater(() => repository.createUser(...), throwsA(...))`.

## Widget Test

```dart
// test/features/user/presentation/user_form_test.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:your_app/features/user/user.dart';

void main() {
  testWidgets('UserForm shows error when email is empty', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: UserFormScreen())),
    );
    expect(find.text('Email is required'), findsNothing); // before

    // ACT — tap submit without filling email
    await tester.tap(find.byType(ElevatedButton));
    await tester.pump(); // trigger rebuild

    // ASSERT
    expect(find.text('Email is required'), findsOneWidget);
  });
}
```

## AsyncNotifier Test (Riverpod 3)

```dart
// test/features/user/presentation/user_notifier_test.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:your_app/features/user/user.dart';

class MockUserRepository extends Mock implements UserRepository {}

void main() {
  late MockUserRepository mockRepository;

  setUp(() => mockRepository = MockUserRepository());

  test('build emits AsyncData on success', () async {
    when(
      () => mockRepository.findById('user-1'),
    ).thenAnswer((_) async => const User(id: 'user-1', email: 'a@example.com'));
    final container = ProviderContainer.test(
      overrides: [userRepositoryProvider.overrideWithValue(mockRepository)],
    );

    await container.read(userProvider('user-1').future);

    expect(container.read(userProvider('user-1')), isA<AsyncData<User>>());
  });
}
```

`ProviderContainer.test()` disposes itself after the test; no `tearDown(container.dispose)`.

## Mocking with mocktail

```dart
// Register fallback values once per file for custom types matched with any()
setUpAll(() => registerFallbackValue(FakeCreateUserDto()));

// Stub return values
when(() => mockRepo.findById('id-1')).thenAnswer((_) async => user);

// Stub an async failure (see the thenThrow trap above)
when(() => mockRepo.createUser(any()))
    .thenAnswer((_) async => throw const ConflictException('Duplicate'));

// Verify calls
verify(() => mockRepo.findById('id-1')).called(1);
verifyNever(() => mockRepo.deleteUser(any()));
```

Only a class that `extends Mock` can be stubbed; `when()` on an `extends Fake` class throws `UnimplementedError`.

## pumpAndSettle vs pump

```dart
await tester.pump();              // single frame — use after synchronous state changes
await tester.pump(Duration.zero); // process timers without advancing real time
await tester.pumpAndSettle();     // run until no pending frames — use for animations/async
```

## Timers and clocks: use `fakeAsync`

```dart
// test/core/retry_fake_async_test.dart
import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:your_app/features/user/user.dart';

void main() {
  test('retries after the backoff elapses', () {
    fakeAsync((async) {
      final calls = <int>[];
      startRetrying(onAttempt: calls.add, backoff: const Duration(seconds: 5));
      async.elapse(const Duration(seconds: 4));
      expect(calls, [1]);
      async.elapse(const Duration(seconds: 1));
      expect(calls, [1, 2]); // virtual time: no real waiting, no CPU-load flake
    });
  });
}
```

`fake_async: 1.3.3` must be a direct `dev_dependency` to import it. Injecting a clock while still waiting on a real
`Timer`/`Future.delayed` makes the test pass idle and fail under load. More traps (vacuous assertions, controls,
goldens): `flutter-mobile/reference/flutter-testing-traps.md`.

## RED-GREEN Example

```bash
# RED
flutter test test/features/user/data/user_repository_test.dart --name "throws ConflictException"
# Expected: FAILED (exit 1)

# GREEN — implement logic
flutter test test/features/user/data/user_repository_test.dart --name "throws ConflictException"
# Expected: PASSED (exit 0)

# Full suite
flutter test
```

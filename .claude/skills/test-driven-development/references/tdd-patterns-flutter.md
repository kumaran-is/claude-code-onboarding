# TDD Patterns — Flutter / Dart (flutter_test + mocktail)

## Test Structure (Unit — Repository/Service)

```dart
// test/features/user/data/user_repository_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class MockUserApi extends Mock implements UserApi {}

void main() {
  late UserRepository repository;
  late MockUserApi mockApi;

  setUp(() {
    mockApi = MockUserApi();
    repository = UserRepository(api: mockApi);
  });

  group('UserRepository.createUser', () {
    test(
      'throws ConflictException when email already exists',
      () async {
        // ARRANGE
        when(() => mockApi.createUser(any()))
            .thenThrow(const ConflictException('Email already exists'));

        // ACT + ASSERT
        expect(
          () => repository.createUser(newUserDto()),
          throwsA(isA<ConflictException>()),
        );
      },
    );
  });
}
```

## Widget Test

```dart
// test/features/user/presentation/user_form_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mocktail/mocktail.dart';

void main() {
  testWidgets('UserForm shows error when email is empty', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(home: UserFormScreen()),
      ),
    );

    // ACT — tap submit without filling email
    await tester.tap(find.byType(ElevatedButton));
    await tester.pump(); // trigger rebuild

    // ASSERT
    expect(find.text('Email is required'), findsOneWidget);
  });
}
```

## AsyncNotifier Test (Riverpod)

```dart
// test/features/user/presentation/user_notifier_test.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class MockUserRepository extends Mock implements UserRepository {}

void main() {
  late ProviderContainer container;
  late MockUserRepository mockRepository;

  setUp(() {
    mockRepository = MockUserRepository();
    container = ProviderContainer(
      overrides: [
        userRepositoryProvider.overrideWithValue(mockRepository),
      ],
    );
  });

  tearDown(() => container.dispose());

  test('fetchUser emits AsyncData on success', () async {
    when(() => mockRepository.findById('user-1'))
        .thenAnswer((_) async => mockUser());

    await container.read(userNotifierProvider('user-1').future);

    expect(
      container.read(userNotifierProvider('user-1')),
      isA<AsyncData<User>>(),
    );
  });
}
```

## Mocking with mocktail

```dart
// Register fallback values for custom types (required by mocktail)
setUpAll(() {
  registerFallbackValue(FakeCreateUserDto());
});

// Stub return values
when(() => mockRepo.findById('id-1'))
    .thenAnswer((_) async => mockUser());

// Stub to throw
when(() => mockRepo.createUser(any()))
    .thenThrow(ConflictException('Duplicate'));

// Verify calls
verify(() => mockRepo.findById('id-1')).called(1);
verifyNever(() => mockRepo.deleteUser(any()));
```

## pumpAndSettle vs pump

```dart
await tester.pump();              // single frame — use after synchronous state changes
await tester.pump(Duration.zero); // process timers without advancing real time
await tester.pumpAndSettle();     // run until no pending frames — use for animations/async
```

## Timers and clocks: use `fakeAsync`

```dart
// dev_dependencies: fake_async: 1.3.3
test('retries after the backoff elapses', () {
  fakeAsync((async) {
    final calls = <int>[];
    startRetrying(onAttempt: calls.add, backoff: const Duration(seconds: 5));
    async.elapse(const Duration(seconds: 5));
    expect(calls, [1, 2]); // virtual time: no real waiting, no CPU-load flake
  });
});
```

Injecting a clock while still waiting on a real `Timer`/`Future.delayed` makes the test pass idle and fail under load.
More traps (vacuous assertions, controls, goldens): `flutter-mobile/reference/flutter-testing-traps.md`.

## RED-GREEN Example

```bash
# RED
flutter test test/features/user/data/user_repository_test.dart --name "throws ConflictException"
# Expected: FAILED

# GREEN — implement logic
flutter test test/features/user/data/user_repository_test.dart --name "throws ConflictException"
# Expected: PASSED

# Full suite
flutter test
```

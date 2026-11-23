# Riverpod Core Patterns

## AsyncNotifier Pattern
```dart
@riverpod
class TodoList extends _$TodoList {
  @override
  FutureOr<List<Todo>> build() async {
    return _fetchTodos();
  }

  Future<void> addTodo(String title) async {
    state = const AsyncLoading();
    final next = await AsyncValue.guard(() async {
      await ref.read(todoRepositoryProvider).add(title);
      return _fetchTodos();
    });
    if (!ref.mounted) return; // the notifier may be disposed while awaiting
    state = next;
  }
}
```

`class TodoList` generates `todoListProvider`; a class named `TodoListNotifier` would generate the same name (`Notifier` suffix is stripped).

## Proper AsyncValue.when
```dart
@override
Widget build(BuildContext context, WidgetRef ref) {
  final todosAsync = ref.watch(todoListProvider);

  return todosAsync.when(
    data: (todos) => ListView.builder(
      itemCount: todos.length,
      itemBuilder: (_, i) => TodoTile(todos[i]),
    ),
    loading: () => const Center(child: CircularProgressIndicator()),
    error: (error, stack) => ErrorView(error: error), // app widget, not Flutter's ErrorWidget
  );
}
```

## Correct ref.watch vs ref.read
```dart
class MyWidget extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // CORRECT: watch in build for reactivity
    final count = ref.watch(counterProvider);

    return ElevatedButton(
      onPressed: () {
        // CORRECT: read in callback for one-time access
        ref.read(counterProvider.notifier).increment();
      },
      child: Text('Count: $count'),
    );
  }
}
```

**Rules:**
- `ref.watch` — use in `build()` for reactive rebuilds
- `ref.read` — use in callbacks, event handlers, one-time reads
- `ref.listen` — use for side effects (navigation, snackbars)
- NEVER use `ref.watch` outside `build()` — causes unexpected rebuilds
- NEVER use `ref.read` in `build()` — widget won't rebuild on changes

## Family Provider Pattern
```dart
@riverpod
Future<User> user(Ref ref, String userId) async {
  return ref.watch(userRepositoryProvider).getUser(userId);
}

// Usage
final user = ref.watch(userProvider(userId));
```

Family arguments are cache keys: use values with `==`/`hashCode` (primitives, records, Freezed classes). A Freezed filter passed twice with equal fields reuses one provider instance.

## Testing providers
```dart
final container = ProviderContainer.test( // disposed at test end
  retry: (_, _) => null,                  // no auto-retry in error-path tests
  overrides: [
    userRepositoryProvider.overrideWithValue(FakeUserRepository()),
    userProvider('a').overrideWith((ref) async => alice),       // one family member
    userDetailProvider.overrideWith2((userId) => StubUserDetail()), // whole notifier family
  ],
);
final sub = container.listen(userDetailProvider('a'), (_, _) {}); // listen, don't just read
await container.read(userDetailProvider('a').future);
expect(sub.read().value?.id, 'a');
```

## Provider Lifecycle

- **autoDispose** (default in codegen): Provider disposed when no longer listened to
- **keepAlive**: `@Riverpod(keepAlive: true)` for app-lifetime state. Use `ref.keepAlive()` only for conditional caching (e.g. after a successful fetch); calling it first thing in the body is flagged by `riverpod_lint` (`prefer_keep_alive_annotation`)
- **invalidate**: Use `ref.invalidate(provider)` to force refresh
- **onDispose**: Use `ref.onDispose(() => ...)` for cleanup (cancel timers, close streams)
- **mounted**: after every `await`, check `ref.mounted` before touching `state` (reads included)
- **exists**: `ref.read(p.exists)` checks whether `p` is mounted without creating it (`ref.exists(p)` is deprecated since 3.5)

## Common Anti-Patterns

```dart
// BAD: Watching in callback
onPressed: () {
  final value = ref.watch(provider); // Will not work correctly
}

// BAD: Reading in build
Widget build(BuildContext context, WidgetRef ref) {
  final value = ref.read(provider); // Won't rebuild
}

// BAD: Not handling all AsyncValue states
todosAsync.when(
  data: (todos) => TodoList(todos),
  loading: () => Container(), // Silent empty container
  error: (e, s) => Container(), // Swallowed error
);

// GOOD: Handle all states visibly
todosAsync.when(
  data: (todos) => TodoList(todos),
  loading: () => const CircularProgressIndicator(),
  error: (e, s) => ErrorDisplay(error: e),
);

// BAD: Reading a provider inside initState() of a regular StatefulWidget
// ref does not exist in StatefulWidget — this will not compile
class _MyScreenState extends State<MyScreen> {
  @override
  void initState() {
    super.initState();
    final value = ref.read(someProvider); // COMPILE ERROR: ref undefined
  }
}

// GOOD: Use ConsumerStatefulWidget + ConsumerState to access ref in initState
// Only ref.read() is allowed in initState — ref.watch() requires the build phase
class MyScreen extends ConsumerStatefulWidget {
  const MyScreen({super.key});
  @override
  ConsumerState<MyScreen> createState() => _MyScreenState();
}

class _MyScreenState extends ConsumerState<MyScreen> {
  @override
  void initState() {
    super.initState();
    // ref.read() is safe here — one-time access, no subscription
    final initialValue = ref.read(someProvider);
    // ref.watch() is FORBIDDEN here — subscriptions require the build phase
  }

  @override
  Widget build(BuildContext context) {
    // ref.watch() is correct here for reactive rebuilds
    final value = ref.watch(someProvider);
    return Text(value.toString());
  }
}
```

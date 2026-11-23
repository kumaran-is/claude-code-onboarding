---
name: riverpod-patterns
description: "This skill provides Riverpod state management patterns and best practices for Flutter applications. Use when reviewing or writing Riverpod providers, AsyncValue handling, ref usage, or provider lifecycle management."
allowed-tools: Read
metadata:
  triggers: Riverpod, Flutter state management, Riverpod provider, AsyncValue, StateNotifier, ConsumerWidget, AsyncNotifier
  related-skills: flutter-mobile, ui-standards-tokens
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-21"
---

## Iron Law

Always use the correct Riverpod provider type for the use case; never use StateProvider for async data or FutureProvider for mutable state.

# Riverpod Patterns

Correct Riverpod patterns for Flutter state management with code_generation style.

**Version:** Riverpod 3.x (`flutter_riverpod`, `riverpod_annotation`, `riverpod_generator`; pin exact versions from pub.dev). Riverpod 3 changes that affect code in this skill:

- Generated providers take a plain `Ref` (`Future<X> foo(Ref ref)`); the generated `FooRef` types are gone.
- `AsyncValue.valueOrNull` was renamed to `value`; the old `value` getter was removed. Use `.value` (nullable).
- `StateProvider`, `StateNotifierProvider`, `ChangeNotifierProvider` moved to `package:flutter_riverpod/legacy.dart`. They still exist but are discouraged — use `Notifier` / `AsyncNotifier` (`@riverpod class`) in new code.
- Using a `Ref` after its provider was disposed throws; guard post-`await` work with `ref.mounted` (see Provider lifecycle).
- Failing providers are retried automatically (default: up to 10 attempts, 200 ms → 6.4 s backoff; `Error`s and `ProviderException`s are not retried). Opt out per provider with `retry`.

**When to use:** Writing or reviewing Riverpod providers, AsyncNotifier, AsyncValue.when, ref.watch vs ref.read, family providers, or provider lifecycle.

**Process:**

1. **Identify pattern needed** from user request
2. **Load reference:** Read `reference/riverpod-core-patterns.md` for code examples and rules
3. **Apply patterns** using loaded reference
4. **Verify:** Confirm ref.watch is only in build(), ref.read only in callbacks, all AsyncValue states handled visibly, and every post-await state write is `ref.mounted`-guarded

## Quick Reference — Most Common Patterns

### Provider Type Selection

```dart
// ✅ Read-only async data (API call, DB read)
@riverpod
Future<List<User>> userList(Ref ref) async {
  return ref.watch(userRepositoryProvider).getAll();
}

// ✅ Mutable state with async operations
@riverpod
class UserNotifier extends _$UserNotifier {
  @override
  Future<User> build(String userId) async {
    return ref.watch(userRepositoryProvider).getById(userId);
  }

  Future<void> update(UserUpdateDto dto) async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() =>
      ref.read(userRepositoryProvider).update(dto));
  }
}

// ❌ WRONG — never model async data with StateProvider (in Riverpod 3 it moved to
// package:flutter_riverpod/legacy.dart and is no longer exported by the main library)
final userProvider = StateProvider<User?>((ref) => null); // no loading/error states
```

### AsyncValue.when — All 3 states required

```dart
// ✅ All 3 states handled visibly
ref.watch(userListProvider).when(
  data: (users) => UserListWidget(users: users),
  loading: () => const CircularProgressIndicator(),
  error: (err, stack) => ErrorWidget(message: err.toString()), // never swallow
);

// ❌ WRONG — skipLoadingOnReload hides loading state from user
ref.watch(userListProvider).when(
  skipLoadingOnReload: true, // only acceptable after explicit UX decision
  data: (users) => UserListWidget(users: users),
  loading: () => const SizedBox.shrink(), // invisible loading = silent failure
  error: (err, stack) => const SizedBox.shrink(), // swallowed error
);
```

### ref.watch vs ref.read

```dart
// ✅ ref.watch — only inside build()
@override
Widget build(BuildContext context, WidgetRef ref) {
  final users = ref.watch(userListProvider); // rebuilds on change
  return UserListWidget(users: users.value ?? []); // Riverpod 3: `.value` (was valueOrNull)
}

// ✅ ref.read — only inside callbacks/event handlers
void onButtonPressed(WidgetRef ref) {
  ref.read(userNotifierProvider.notifier).refresh(); // one-time action
}

// ❌ WRONG — ref.watch in a callback (causes infinite rebuild)
onPressed: () => ref.watch(userNotifierProvider.notifier).refresh(),
```

### Reading AsyncValue without losing data

- Read the payload with `.value` / `.hasValue`, not `asData?.value`: `asData` is null for any state that is not `AsyncData`, including an `AsyncLoading`/`AsyncError` that still carries the previous value.
- During provider auto-retry the state is an `AsyncLoading` that carries the error and no value. A hand-written `pending = isLoading && !hasValue` treats that as "still loading"; add `&& !hasError` and treat `hasError` as terminal for UI.
- A provider whose UI degrades to a fallback on `error:` (or offers "Try again") should disable auto-retry, otherwise a later retry swaps the UI under the user:

```dart
Duration? noRetry(int retryCount, Object error) => null;

@Riverpod(retry: noRetry)
Future<Profile> profile(Ref ref) => ref.watch(profileRepositoryProvider).load();
```

### Provider lifecycle — disposal mid-await is a normal path

A screen-scoped (autoDispose) notifier is disposed when its last listener goes away (route popped, tab replaced, conditional UI). Treat "disposed while awaiting" as expected:

```dart
// ✅ Every post-await write — including catch/finally — is guarded
void _set(UploadState next) {
  if (!ref.mounted) return;
  state = next;
}

Future<void> upload(File file) async {
  try {
    _set(UploadState.done(await ref.read(uploadRepositoryProvider).send(file)));
  } on Object catch (e, st) {
    ref.read(appLoggerProvider).error('upload failed', error: e, stackTrace: st);
    _set(UploadState.failed(e));
  } finally {
    _set(state.copyWith(busy: false));
  }
}
// ❌ unguarded `finally { state = ...; }` throws on a disposed notifier
```

- Put mutations on a `keepAlive` notifier method, or `await` them and check `mounted` before navigating. Never fire-and-forget a bare autoDispose `Future<void>` provider (`ref.read(p.future); context.go(...)`): the future and its error are discarded.
- A provider whose factory closure re-enters its own `Ref` after an `await` (e.g. a service that calls `ref.read(...)` later) must be `keepAlive: true`.
- A documented "never throws, falls back to X" contract must catch `Object`, not one app error type — a client may rethrow a `TypeError` or `FormatException` unchanged.
- Multi-step async controller (record → stream → finalize): key every continuation to an attempt object, `_isCurrent(a) => ref.mounted && identical(a, _attempt)`, and drop results from superseded attempts.

### Activating providers outside the widget tree

In `main()`/bootstrap before `runApp`, or in a test with a bare `ProviderContainer`, activate with `container.listen(provider, (_, _) {})`, not `container.read(provider)`. A one-off read builds the provider once and nothing listens to it, so listeners inside it (auth change → refetch, connectivity → drain) may never fire while every test still passes. In tests drive the real stream (a `StreamController`), not a pinned value. Comment each pre-`runApp` activation with why running it before auth settles is safe (see [flutter-navigation-and-auth-boot.md](../flutter-mobile/reference/flutter-navigation-and-auth-boot.md)).

For `ref.invalidate` on a provider backed by a local database: it re-subscribes and re-emits cached rows, it does not hit the network. A pull-to-refresh callback must `await` the repository's refresh, not just invalidate.

## Reference Files

| File | Contents | Load When |
|------|----------|-----------|
| `reference/riverpod-core-patterns.md` | Code examples, provider types, ref usage rules | Writing providers, ref.watch/read, AsyncValue handling |
| `reference/riverpod-review-checklist.md` | Review checklist for Riverpod code audits (used by `riverpod-reviewer` agent) | Reviewing Riverpod code, running riverpod-reviewer agent |

## Error Handling

**Provider not found**: Ensure `ProviderScope` wraps the widget tree. Check that generated `.g.dart` files are up to date (`dart run build_runner build`).

**AsyncValue stuck loading**: Verify the repository method returns data. Use `AsyncValue.guard()` to catch and surface errors instead of silent failures.

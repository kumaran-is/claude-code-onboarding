# Riverpod Review Checklist

## 1. Provider Type Selection

Verify correct provider types:
- [ ] `@riverpod` for computed/derived values
- [ ] `@Riverpod(keepAlive: true)` for app-lifetime state
- [ ] `AsyncNotifier` for async state with mutations
- [ ] `Notifier` for sync state with mutations
- [ ] `StreamNotifier` for real-time data
- [ ] No `StateProvider` / `StateNotifierProvider` / `ChangeNotifierProvider` in new code (Riverpod 3 moved them to `legacy.dart`)
- [ ] Generated providers take `Ref` (not `FooRef`); no `valueOrNull` (renamed `value` in Riverpod 3)
- [ ] Generated names account for the stripped `Notifier` suffix (`class FooNotifier` → `fooProvider`); no class/function pair that collides on one name

## 2. Ref Usage Patterns

Check:
- [ ] `ref.watch()` in `build()` for reactive updates
- [ ] `ref.read()` for one-time reads (callbacks, events)
- [ ] `ref.listen()` for side effects
- [ ] `ref.invalidate()` for manual refresh
- [ ] No `ref.watch()` in event handlers

## 3. AsyncValue Handling

Verify:
- [ ] Always handle loading, error, and data states
- [ ] Use `AsyncValue.when()` for exhaustive matching
- [ ] Provide meaningful loading indicators
- [ ] Display user-friendly error messages
- [ ] Consider `AsyncValue.guard()` for error handling
- [ ] Payload read with `.value`/`.hasValue`, not `asData?.value` (null for loading/error states that still carry a value)
- [ ] A hand-written "pending" flag includes `&& !hasError` (auto-retry yields `AsyncLoading` + error) — HIGH if it hides content or keeps a spinner on a failed read
- [ ] A provider whose UI degrades to a fallback or offers "Try again" disables auto-retry (`@Riverpod(retry: noRetry)` with a top-level `Duration? noRetry(int, Object) => null`; annotation arguments cannot be closures)
- [ ] Empty and error states are distinct; an empty branch never shows error copy

## 4. Provider Lifecycle

Check:
- [ ] AutoDispose for screen-scoped state
- [ ] `keepAlive: true` only when necessary
- [ ] Proper family parameters for parameterized providers
- [ ] No providers created inside widgets
- [ ] Dispose of resources in `ref.onDispose()`
- [ ] Every post-`await` state write (including `catch`/`finally`) is `ref.mounted`-guarded, and the guard runs before `state` is read (`_set(state.copyWith(...))` reads first and throws) — HIGH when missing in an autoDispose notifier
- [ ] A provider whose closure re-enters its own `Ref` after an `await` is `keepAlive`
- [ ] Mutations are keepAlive notifier methods or awaited with a `mounted` check — not a bare autoDispose `Future<void>` provider read fire-and-forget
- [ ] A "never throws / falls back" contract catches `Object`, not one app error type
- [ ] Activation outside the widget tree (bootstrap, tests) uses `container.listen`, not `container.read`
- [ ] No `ref.watch` inside a router `redirect` (use `ref.read` + `refreshListenable`)
- [ ] No deprecated 3.x APIs: `ref.exists(p)`/`container.exists(p)` (use `p.exists`), `family.overrideWith` for notifier families (use `overrideWith2`), `ref.keepAlive()` as the first body statement (use `@Riverpod(keepAlive: true)`)
- [ ] Code awaiting another provider's `.future` that can be disposed handles `ProviderDisposedException` (3.5) instead of matching `StateError`

## 5. State Mutations

Review:
- [ ] Mutations through notifier methods, not direct state changes
- [ ] Optimistic updates with rollback
- [ ] Loading states during mutations
- [ ] Error handling for failed mutations

## 6. Code Generation

Verify:
- [ ] Using `@riverpod` annotation (not manual providers)
- [ ] Build runner generates `.g.dart` files
- [ ] Part directives present for generated code
- [ ] Notifier classes extend generated base classes
- [ ] Tests use `ProviderContainer.test(...)`, not a bare `ProviderContainer()` without `addTearDown(container.dispose)`
- [ ] `riverpod_lint` enabled through `analysis_options.yaml` `plugins:` (not the removed `custom_lint` setup)

## Common Anti-Patterns

1. **watch() in Callbacks** — Using ref.watch inside button onPressed
2. **Missing AsyncValue Handling** — Not handling loading/error states
3. **Provider in Widget** — Creating providers inside build methods
4. **Wrong Provider Type** — Using StateProvider when Notifier needed
5. **Missing keepAlive** — App-level state disposed unexpectedly
6. **Over-watching** — Watching entire state when select would suffice
7. **Circular Dependencies** — Providers watching each other
8. **Missing Dispose** — Resources not cleaned up on dispose
9. **Unguarded post-await write** — `state = …` after an `await` without `ref.mounted`
10. **Retry masked as loading** — spinner shown while a failing provider auto-retries

## Output Format

For each finding:

```markdown
### [Riverpod Issue Title]

**Severity:** P1 CRITICAL / P2 IMPORTANT / P3 IMPROVEMENT
**Category:** Provider Type / Ref Usage / AsyncValue / Lifecycle / Mutation
**Location:** `file_path:line_number`

**Issue:**
[Description of the Riverpod pattern issue]

**Problem:**
[What goes wrong with current approach]

**Solution:**
[Correct Riverpod pattern to use]

**Before:**
```dart
// Incorrect pattern
```

**After:**
```dart
// Correct Riverpod pattern
```
```

## Severity Levels

- P1 (report as CRITICAL or HIGH): Riverpod misuse causing bugs or crashes
- Map for the agent verdict: P1 → CRITICAL/HIGH, P2 → MEDIUM, P3 → LOW
- P2: Patterns that will cause issues at scale
- P3: Best practice improvements

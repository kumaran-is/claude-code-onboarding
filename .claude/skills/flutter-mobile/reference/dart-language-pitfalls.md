# Dart Language Pitfalls

Common Dart mistakes and the correct patterns — specific to Dart 3.10.9+ / Flutter 3.41.x+.
These are language-level issues distinct from Flutter widget, architecture, or test patterns.

---

## 1. `late` Keyword Overuse

### Anti-pattern
```dart
// BAD: late used to defer work that could be done in the constructor
class ProfileController {
  late UserProfile profile;   // Will throw LateInitializationError if accessed early
  late String displayName;    // Nothing enforces initialization order
}
```

`late` **skips null-safety guarantees**. The compiler trusts you, but the runtime will throw
`LateInitializationError` if the variable is accessed before it is assigned.

### Rule
Use `late` ONLY for:
1. Top-level or static variables initialized once before any use (e.g., service locator setup)
2. `@override` fields that must be initialized in `initState` or `setUp`
3. Variables where you can provably guarantee initialization before first read

In every other case, prefer one of:
```dart
// GOOD: nullable + explicit null check
String? displayName;
void render() {
  if (displayName == null) return;
  // ...
}

// GOOD: constructor initialization (always safe)
class ProfileController {
  final UserProfile profile;
  ProfileController({required this.profile});
}

// ACCEPTABLE: late only when lifecycle guarantees it
class _MyWidgetState extends State<MyWidget> {
  late AnimationController _controller;   // initialized in initState before build

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 300));
  }
}
```

---

## 2. Ignoring Future Return Values (Silent Swallow)

### Anti-pattern
```dart
// BAD: fire and forget — exceptions are silently lost
void onButtonTap() {
  saveToDatabase(record);         // Future<void> returned and discarded
  sendAnalyticsEvent('tapped');   // Same problem
}
```

When a `Future` is discarded without `await` or `.catchError()`, any exception it throws
disappears with no log, no error state, and no user feedback.

### Rule
Always handle the Future explicitly:

```dart
// GOOD: await and handle errors
Future<void> onButtonTap() async {
  try {
    await saveToDatabase(record);
  } catch (e, stack) {
    _logger.error('saveToDatabase failed', error: e, stackTrace: stack);
    state = AsyncError(e, stack);  // surface to UI
  }
}

// GOOD: chain error handler
void onButtonTap() {
  saveToDatabase(record)
    .then((_) => _logger.info('saved'))
    .catchError((e, stack) {
      _logger.error('saveToDatabase failed', error: e, stackTrace: stack);
    });
}

// ACCEPTABLE: intentional fire-and-forget — use unawaited() to make it explicit
import 'dart:async';

void onButtonTap() {
  unawaited(sendAnalyticsEvent('tapped'));   // explicit: we don't care about the result
}
```

`unawaited()` (from `dart:async`) tells the reader AND the linter that discarding is deliberate.
Without it, the linter flags the discard as a warning.

---

## 3. Dart 3 Records for Multiple Return Values

### Anti-pattern (pre-Dart 3)
```dart
// BAD: creating a one-off Map or throwaway data class
Map<String, dynamic> getCoordinates() => {'lat': 37.7, 'lng': -122.4};

// BAD: caller must use string keys and cast
final coords = getCoordinates();
final lat = coords['lat'] as double;
```

### Rule — use Dart 3 records (Dart 3.10.9+ / Flutter 3.41.x+)

```dart
// GOOD: positional record
(double lat, double lng) getCoordinates() => (37.7, -122.4);

// Destructure at call site
final (lat, lng) = getCoordinates();

// GOOD: named fields when caller needs clarity
({double lat, double lng}) getCoordinates() => (lat: 37.7, lng: -122.4);

// Destructure named fields
final (:lat, :lng) = getCoordinates();
print('$lat, $lng');
```

Use records when:
- Returning 2–4 related values from a function
- The grouping is ad-hoc and doesn't warrant a named class
- The values are used immediately at the call site and not stored long-term

Use a named class/data class when the structure is stored, passed widely, or serialized.

---

## 4. `var` Where `final` Works

### Anti-pattern
```dart
// BAD: var used for a value that is never reassigned
var user = await fetchUser(id);
var displayName = user.fullName.toUpperCase();
```

### Rule
Default to `final` for all local variables that are not explicitly reassigned after initialization.
Use `var` only when reassignment is required (e.g., loop accumulator, conditional update).

```dart
// GOOD
final user = await fetchUser(id);
final displayName = user.fullName.toUpperCase();

// CORRECT use of var (reassigned in loop)
var total = 0.0;
for (final item in cart.items) {
  total += item.price;
}
```

This communicates intent, prevents accidental reassignment, and enables additional compiler
analysis. It also matches the Dart linter's `prefer_final_locals` rule.

---

## 5. `as` Cast Without Prior Type Check

### Anti-pattern
```dart
// BAD: throws CastError at runtime if the type is wrong
void process(Object event) {
  final tap = event as TapEvent;   // crashes if event is a SwipeEvent
  handleTap(tap);
}
```

### Rule
Use `is` for type checks — the Dart compiler promotes the type inside the `if` block automatically
(smart cast), so no explicit cast is needed.

```dart
// GOOD: smart cast via is check
void process(Object event) {
  if (event is TapEvent) {
    handleTap(event);    // event is TapEvent here — no cast needed
  } else if (event is SwipeEvent) {
    handleSwipe(event);
  }
}
```

`as` is appropriate ONLY when you are 100% certain of the type and the certainty comes from
an invariant that the type system cannot express — for example, after `jsonDecode()` for a
known, validated schema.

```dart
// ACCEPTABLE: known schema after validation
final json = jsonDecode(responseBody) as Map<String, dynamic>;
```

---

## 6. String Concatenation Instead of Interpolation

### Anti-pattern
```dart
// BAD: creates intermediate String objects; harder to read
final message = "Hello " + user.firstName + " " + user.lastName + "!";
```

### Rule
Use string interpolation. It is more efficient (single allocation) and more readable.

```dart
// GOOD
final message = "Hello ${user.firstName} ${user.lastName}!";

// Simple variable — no braces needed
final greeting = "Hello $name!";

// Expressions inside braces
final summary = "Cart total: \$${cart.total.toStringAsFixed(2)}";
```

---

## 7. Collection Constructors Instead of Literals

### Anti-pattern
```dart
// BAD: verbose, outdated syntax
final names = new List<String>();
final lookup = new Map<String, int>();
final ids = new Set<String>();
```

### Rule
Use collection literals. They are idiomatic Dart, require less typing, and the analyzer
enforces this via `prefer_collection_literals`.

```dart
// GOOD
final names = <String>[];
final lookup = <String, int>{};
final ids = <String>{};

// With initial values
final colors = <String>['red', 'green', 'blue'];
final scores = <String, int>{'alice': 10, 'bob': 8};
```

The `new` keyword is also unnecessary in Dart 2+ — never use it.

---

## 8. Splitting a Large State Class (`part` + `mixin on`)

Dart privacy is **library**-scoped: moving a `_privateMember` to another file makes it invisible to the original. That decides the shape of every split.

| Goal | Tool |
|------|------|
| Move whole widgets/helpers whose callers move too | Ordinary file + `import`; publish only what is genuinely shared |
| Split ONE class across files, keeping `_private` access | `part` / `part of` + `mixin … on State<T>` (or `ConsumerState<T>`) |

`part` is not banned — it is just unused outside codegen. Mixin rules:

- A mixin body resolves only against its own members and its `on` types. When two mixins split one class, the later one names the earlier: `mixin _View on State<Screen>, _Wizard`.
- Members the class still owns are declared `abstract` on the mixin; the class members then need `@override`.
- `static const` members are invisible to a mixin — lift them to top level (still library-private).
- This is a file split only. Moving `setState` state into a notifier means converting in-place mutation to immutable state — a behaviour change; do it in a separate step.

Move checklist: a newly public widget needs `super.key`; carry every comment line above a moved declaration (`// ignore:` markers apply to the next line); prune imports only after all moves finish; renaming a `StatefulWidget` must reach `State<T>` and `createState`.

---

## 9. Reading Analyzer Output Honestly

- `dart analyze` / `flutter analyze` exit non-zero on `info` issues too (`--fatal-infos` makes this explicit). `grep -c "error •"` returning 0 means "no errors", not "clean" — read the final verdict or count `error`, `warning` and `info` together.
- `| head -N` caps the view, not the count. Claim a count only from a count (`grep -c`).
- A wrapper's exit code is not the command's: a pipe's `$?` is the last element's and a trailing `echo` reports its own. Verify from the artifact (the log, the written file).
- Useful write-time lints for leak/dynamic-call classes (documented on dart.dev): `cancel_subscriptions`, `close_sinks`, `avoid_dynamic_calls`, `only_throw_errors`. Enable them in `analysis_options.yaml` under `linter: rules:` and fix, don't suppress.
- Scripted multi-file edits: assert each anchor exists before replacing (a drifted anchor must fail loudly) and never rely on a brace-depth counter over Dart — named-parameter `({` breaks it.

---

## Quick Reference

| Pitfall | Bad Signal | Fix |
|---------|-----------|-----|
| `late` overuse | `late SomeType x;` without lifecycle guarantee | Constructor init or nullable |
| Ignored Future | `someAsync();` (no await, no store) | `await` or `unawaited()` explicitly |
| Multiple returns | `Map<String, dynamic>` or one-off class | Dart 3 record `(T a, T b)` |
| `var` for constants | `var x = computeOnce();` | `final x = computeOnce();` |
| Unsafe cast | `obj as SomeType` without check | `if (obj is SomeType)` smart cast |
| String concat | `"a" + b + "c"` | `"a${b}c"` interpolation |
| Collection ctor | `List<T>()` / `Map<K,V>()` | `<T>[]` / `<K,V>{}` |
| Giant State class | One 1500-line `State` | `part` + `mixin on` split, behaviour unchanged |
| False "clean" analyze | `head -5` or `grep -c error` | Count all severities; exit code is the verdict |

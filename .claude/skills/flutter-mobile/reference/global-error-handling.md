# Global Error Handling — Flutter 3.50.x / Dart 3.14.0

## Why global error handling is required

Flutter routes uncaught errors through **3 hooks**. Missing one means some errors reach users silently.
Production apps MUST configure all 3 before calling `runApp()`. This matches the current
Flutter "Handling errors" guide, which no longer wraps `main` in `runZonedGuarded`.

| Hook | What it catches |
|---|---|
| `FlutterError.onError` | Widget build errors, layout/paint errors, framework-internal errors |
| `PlatformDispatcher.instance.onError` | Errors with no Flutter callback on the stack: uncaught async errors (timers, Futures, Streams), platform-channel errors |
| `ErrorWidget.builder` | Replaces the red error screen shown when a widget fails to build |

`runZonedGuarded` is optional and no longer needed to catch async errors. If a project keeps a
custom zone, call `WidgetsFlutterBinding.ensureInitialized()` **and** `runApp()` inside that same
zone: initialising the binding in one zone and calling `runApp` in another triggers Flutter's
"Zone mismatch" check.

---

## Section 1 — The 3 hooks (complete setup)

Keep the reporter behind an interface so the hooks can be unit-tested without Firebase:

```dart
// lib/core/errors/error_handlers.dart
import 'package:flutter/foundation.dart'; // FlutterError, kReleaseMode, PlatformDispatcher
import 'package:material_ui/material_ui.dart'; // ErrorWidget, Material, Icons

abstract interface class CrashReporter {
  void recordFlutterError(FlutterErrorDetails details);
  void recordError(Object error, StackTrace stack);
}

/// Installs the global error hooks. Call before runApp.
void installErrorHandlers(CrashReporter reporter) {
  FlutterError.onError = (details) {
    FlutterError.presentError(details); // keep console/IDE output in every mode
    reporter.recordFlutterError(details);
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    reporter.recordError(error, stack);
    return true; // handled: logged and reported
  };
  if (kReleaseMode) {
    ErrorWidget.builder = (details) => const ErrorFallbackWidget();
  }
}
```

```dart
// lib/main.dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  installErrorHandlers(CrashlyticsReporter(FirebaseCrashlytics.instance));
  runApp(const ProviderScope(child: App()));
}
```

`CrashlyticsReporter` forwards to `recordFlutterFatalError(details)` and
`recordError(error, stack, fatal: true)`; see the `bootstrap.dart` template in
[flutter-templates.md](flutter-templates.md).

Unit test (no device, no Firebase) — proves both hooks forward and report "handled":

```dart
test('global hooks forward framework and platform errors', () {
  final savedFlutter = FlutterError.onError;
  final savedPlatform = PlatformDispatcher.instance.onError;
  final savedPresent = FlutterError.presentError;
  addTearDown(() {
    FlutterError.onError = savedFlutter;
    PlatformDispatcher.instance.onError = savedPlatform;
    FlutterError.presentError = savedPresent;
  });
  FlutterError.presentError = (_) {}; // keep the test output quiet
  final reporter = RecordingReporter();
  installErrorHandlers(reporter);

  FlutterError.reportError(FlutterErrorDetails(exception: StateError('build')));
  final handled = PlatformDispatcher.instance.onError!(
    StateError('async'),
    StackTrace.current,
  );

  expect(reporter.flutterErrors, hasLength(1));
  expect(reporter.errors, hasLength(1));
  expect(handled, isTrue);
});
```

---

## Section 2 — ErrorFallbackWidget

Replace the default red error widget in release builds with a user-friendly screen.

```dart
class ErrorFallbackWidget extends StatelessWidget {
  const ErrorFallbackWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Material(
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48),
            const SizedBox(height: 16),
            const Text('Something went wrong.'),
            TextButton(
              onPressed: () {
                // Option: use GoRouter to navigate home
                // GoRouter.of(context).go('/');
              },
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}
```

`ErrorWidget.builder` receives only the error details, no `BuildContext`, so its copy cannot come
from `AppLocalizations.of(context)` at that point; keep it short and generic, or build it with the
`MaterialApp.builder` pattern from the Flutter errors guide.

---

## Section 3 — Required imports

```dart
import 'package:flutter/foundation.dart'; // FlutterError, kReleaseMode, kDebugMode
import 'package:material_ui/material_ui.dart'; // not package:flutter/material.dart (deprecated after 3.47)
```

`PlatformDispatcher` comes from `dart:ui` and is re-exported by `package:flutter/foundation.dart`;
a separate `import 'dart:ui'` is flagged as `unnecessary_import`.

---

## Section 4 — Common mistakes

| Mistake | Why it breaks |
|---|---|
| Only setting `FlutterError.onError` | Misses uncaught async and platform errors (`PlatformDispatcher.instance.onError`) |
| `ensureInitialized()` outside a custom zone and `runApp()` inside it | Flutter reports "Zone mismatch"; keep both in one zone or drop the custom zone |
| `return false` from `PlatformDispatcher.instance.onError` | `false` = error is NOT handled — it propagates to the OS crash handler. If you logged it, return `true`. |
| Showing the red error widget in release | Leaks implementation details and stack traces to users |
| Silencing debug errors | Debug mode should use `FlutterError.presentError(details)` — never suppress errors in debug |
| Using bare `try/catch` at `main()` top level | Does not catch async errors thrown after `await`s complete |

---

## Section 5 — Integration checklist

- [ ] No custom zone, or binding init and `runApp()` in the same zone
- [ ] `FlutterError.onError` set **before** `runApp()`
- [ ] `PlatformDispatcher.instance.onError` set **before** `runApp()`
- [ ] `ErrorWidget.builder` overridden for release mode
- [ ] Debug mode uses `FlutterError.presentError(details)` — debug errors are visible
- [ ] Errors reach the crash reporting SDK through a `CrashReporter` the hooks receive; a unit test proves both hooks forward
- [ ] `PlatformDispatcher.instance.onError` returns `true` after handling

---

## Section 6 — Error taxonomy: never map one failure class onto another

- **Network failure ≠ domain error.** Connection errors and timeouts must stay distinguishable from validation/business failures all the way to the UI. A broad `on AppException` that always emits "invalid code" turns "you are offline" into a confident lie about the user's input. Branch on the error code/type (`e.code == ErrorCode.network ? offline : …`).
- **The `default` arm of an error-key switch must be the vaguest true statement** ("Something went wrong"), never the most specific domain verdict.
- **Timeout ≠ offline.** A timeout is its own terminal result (retryable, with copy such as "took too long"); only a connection error means offline.
- **A catch that only logs is still a silent failure for the user.** Non-fatal is a reason not to rethrow, never a reason not to tell. If the catch comment admits a user-visible consequence ("the badge never clears"), that is a bug. Capture `ScaffoldMessenger`/localizations **before** the `await`, then show the failure.
- **Log the error object through the logger's `error:` channel; never interpolate it into the message** (`FormatException.toString()` can embed a snippet of user input).
- A "never throws, falls back" contract catches `Object` — clients may rethrow `TypeError`/`FormatException` as-is. Request-level timeouts and client-vs-server contract rules: [flutter-api-contract-parity.md](flutter-api-contract-parity.md).

---

## Stack version

Applies to: Flutter 3.50.x / Dart 3.14.0 (this workspace's stack); hooks unit-tested on Flutter 3.50.1.
Do not use the older `FlutterError.onError`-only or `runZonedGuarded`-first patterns from older guides.

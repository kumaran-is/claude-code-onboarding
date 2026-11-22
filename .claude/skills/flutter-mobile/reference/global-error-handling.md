# Global Error Handling — Flutter 3.41.x+ / Dart 3.10.9+

## Why global error handling is required

Flutter has **4 error entry points**. Missing any one means some errors reach users silently.
Production apps MUST configure all 4 before calling `runApp()`.

| Entry Point | What it catches |
|---|---|
| `runZonedGuarded` | Async errors that escape the Flutter framework (timers, Futures, Streams) |
| `FlutterError.onError` | Widget build errors, rendering errors, framework-internal errors |
| `PlatformDispatcher.instance.onError` | Platform channel errors, isolate errors, errors not caught by the zone |
| `ErrorWidget.builder` | Replaces the red error screen shown when a widget fails to build |

---

## Section 1 — The 4 Error Entry Points (complete setup)

```dart
void main() {
  // Entry Point 1: runZonedGuarded catches async errors not handled by Flutter framework
  runZonedGuarded(
    () async {
      WidgetsFlutterBinding.ensureInitialized();

      // Entry Point 2: FlutterError.onError catches widget/rendering errors
      FlutterError.onError = (FlutterErrorDetails details) {
        if (kReleaseMode) {
          // Forward to crash reporting (e.g., Firebase Crashlytics)
          // FirebaseCrashlytics.instance.recordFlutterFatalError(details);
          Zone.current.handleUncaughtError(details.exception, details.stack!);
        } else {
          // Debug: use default Flutter handler (prints red screen + console output)
          FlutterError.presentError(details);
        }
      };

      // Entry Point 3: PlatformDispatcher catches platform/isolate errors
      PlatformDispatcher.instance.onError = (error, stack) {
        if (kReleaseMode) {
          // FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
        }
        // return true = error is handled (suppressed from OS crash handler)
        // return false = error is NOT handled (will propagate and may crash)
        return true;
      };

      // Entry Point 4 (ErrorWidget): replace red error screen in release mode
      if (kReleaseMode) {
        ErrorWidget.builder = (FlutterErrorDetails details) {
          return const ErrorFallbackWidget();
        };
      }

      runApp(const MyApp());
    },
    // Entry Point 1 handler: errors thrown inside the zone
    (error, stack) {
      if (kReleaseMode) {
        // FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
      }
      debugPrint('Unhandled zone error: $error\n$stack');
    },
  );
}
```

> **Relationship to `flutter-templates.md` bootstrap pattern:** The `bootstrap.dart` template
> shows the Firebase Crashlytics wiring for `FlutterError.onError` and
> `PlatformDispatcher.instance.onError`. This file covers all 4 entry points, the
> debug/release branching, and the `ErrorWidget.builder` — which the bootstrap template omits.

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

---

## Section 3 — Required imports

```dart
import 'dart:async';
import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/foundation.dart'; // kReleaseMode, kDebugMode
import 'package:flutter/material.dart';
```

`PlatformDispatcher` lives in `dart:ui`. The `flutter/services.dart` import does NOT expose it.

---

## Section 4 — Common mistakes

| Mistake | Why it breaks |
|---|---|
| Only setting `FlutterError.onError` | Misses platform errors (Entry Point 3) and zone async errors (Entry Point 1) |
| Wrapping just `runApp()` in `runZonedGuarded` instead of the full body | Async errors triggered before `runApp()` (e.g., init logic) escape the zone |
| `return false` from `PlatformDispatcher.instance.onError` | `false` = error is NOT handled — it propagates to the OS crash handler. If you logged it, return `true`. |
| Showing the red error widget in release | Leaks implementation details and stack traces to users |
| Silencing debug errors | Debug mode should use `FlutterError.presentError(details)` — never suppress errors in debug |
| Using bare `try/catch` at `main()` top level | Does not catch async errors thrown after `await`s complete |

---

## Section 5 — Integration checklist

- [ ] `runZonedGuarded` wraps the **entire** `main()` body (not just `runApp()`)
- [ ] `FlutterError.onError` set **before** `runApp()`
- [ ] `PlatformDispatcher.instance.onError` set **before** `runApp()`
- [ ] `ErrorWidget.builder` overridden for release mode
- [ ] Debug mode uses `FlutterError.presentError(details)` — debug errors are visible
- [ ] Release mode sends errors to crash reporting SDK (replace `debugPrint` stubs)
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

Applies to: Flutter 3.41.x+ / Dart 3.10.9+ (this workspace's stack).
`PlatformDispatcher.instance.onError` was stabilised in Flutter 3.x — do not use the older
`FlutterError.onError`-only pattern from pre-3.x guides.

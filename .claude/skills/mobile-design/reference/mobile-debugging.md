# Mobile Debugging Guide

Flutter-specific debugging strategies using Flutter DevTools, Dart Observatory, and the xcodebuild MCP. Stop guessing with `print()` — use the right tool for the layer that is broken.

---

## Mobile Debugging Mindset

```
Web Debugging:          Flutter Debugging:
+--------------+        +--------------+
|  Browser     |        |  Dart VM     |
|  DevTools    |        |  Flutter UI  |
|  Network Tab |        |  GPU/Memory  |
+--------------+        |  Native iOS  |
                        |  Native Droid|
                        +--------------+
```

**Key Differences:**

1. **Native Layer:** Dart code works, but app crashes? It may be native (Swift/Obj-C on iOS, Kotlin/Java on Android).
2. **Deployment:** You cannot just "hot reload" a native crash. Some state gets lost.
3. **Network:** SSL Pinning and proxy settings are harder to inspect.
4. **Device Logs:** `adb logcat` and Xcode console / xcodebuild MCP logs are your truth.

---

## AI Debugging Anti-Patterns

| AI Default | Flutter-Correct |
|------------|-----------------|
| "Add print() statements" | Use Flutter DevTools debugger or logger |
| "Check the terminal output" | Use DevTools Network tab or proxy tool |
| "It works on simulator" | Test on real device (hardware-specific bugs are real) |
| "Run flutter clean" first | Check the actual error first; flutter clean is last resort |
| Ignore native logs | Read xcodebuild MCP logs or adb logcat |

---

## 1. The Flutter Debugging Toolset

### Flutter DevTools (Primary Tool)

```
Launch: flutter pub global run devtools
Or: Open automatically when running flutter run

Tabs:
+-- Flutter Inspector: Widget tree, layout issues
+-- Performance: Frame timing, jank detection
+-- CPU Profiler: Dart VM CPU usage
+-- Memory: Object allocations, leak detection
+-- Network: HTTP requests and responses
+-- Logging: Structured log output
+-- Debugger: Breakpoints, step through Dart code
```

### xcodebuild MCP (iOS-Specific)

For iOS builds, crashes, and LLDB debugging, use the xcodebuild MCP tools instead of raw Bash:

| MCP Tool | Purpose |
|----------|---------|
| `build_run_sim` | Build, install, and launch on iOS simulator |
| `start_sim_log_cap` | Start capturing simulator logs |
| `stop_sim_log_cap` | Get captured logs |
| `debug_attach_sim` | Attach LLDB debugger |
| `debug_breakpoint_add` | Set breakpoint at file:line |
| `debug_variables` | Inspect variables at breakpoint |
| `debug_stack` | View call stack |
| `screenshot` | Capture current simulator screen |

### Android Debug Tools

```
adb logcat: View all device logs
adb logcat *:E: Filter for errors only
adb logcat | grep flutter: Filter Flutter output

Android Studio:
+-- Logcat tab: Real-time device logs
+-- Layout Inspector: UI hierarchy (like Flutter Inspector)
+-- Profiler: CPU, memory, network
```

---

## 2. Common Debugging Workflows

### "The App Just Crashed" (Identify Layer First)

**Scenario A: Dart Exception (Red Screen)**
- **Cause:** Null dereference, type error, unhandled exception
- **Read:** The stack trace on the red screen or in the terminal
- **Fix:** The error message is usually self-explanatory; read it fully

**Scenario B: Crash to Home Screen (Native Crash)**
- **Cause:** Native plugin failure, memory OOM, missing permission declaration
- **iOS:**
  - Use xcodebuild MCP: `start_sim_log_cap` -> reproduce -> `stop_sim_log_cap`
  - Or: Xcode -> Window -> Devices -> View Device Logs
- **Android:** `adb logcat *:E` — filter for FATAL and AndroidRuntime

If the app crashes immediately on launch, it is almost always a native configuration issue: `Info.plist` (iOS) or `AndroidManifest.xml` (Android) — missing permission, wrong bundle ID, or misconfigured Firebase.

### "A Widget Is Rendering Wrong" (Layout Issues)

```
1. Open Flutter Inspector in DevTools
2. Select the widget that looks wrong
3. Check: size constraints, padding, overflow
4. Enable "Debug Paint" to see widget boundaries
5. Enable "Repaint Rainbow" to see which widgets are rebuilding

Common causes:
+-- Unbounded height/width in a Column/Row
+-- Missing Expanded or Flexible around a child
+-- Padding going to wrong edge (safe area)
+-- Theme color resolved differently in dark mode
```

### "The API Request Failed" (Network)

```
Flutter DevTools Network tab:
+-- Open DevTools -> Network tab
+-- See all HTTP requests, status codes, response bodies
+-- Works for dio and http package requests

For deeper inspection (including native SDK traffic):
+-- iOS: Use Proxyman or Charles Proxy with SSL cert installed
+-- Android: Use Proxyman or Charles Proxy with SSL cert installed

Common causes:
+-- Wrong base URL (localhost vs 10.0.2.2 on Android emulator)
+-- Missing Authorization header
+-- SSL pinning blocking the request
+-- Firebase Security Rules blocking the query
```

**Android emulator note:** `localhost` inside an Android emulator is `10.0.2.2`, not `127.0.0.1`. This is a very common cause of "connection refused" on emulator.

### "The UI Is Laggy" (Performance)

Do not guess. Measure first.

```
1. Run in profile mode: flutter run --profile
2. Open DevTools Performance tab
3. Record while reproducing the jank
4. Look for:
   +-- Frames over 16.67ms (red bars)
   +-- Long build() methods
   +-- Excessive widget rebuilds (check with Repaint Rainbow)

5. Fix the actual bottleneck:
   +-- Excessive rebuilds -> add const, use ref.select()
   +-- Expensive build() -> move computation out of build
   +-- Large list without ListView.builder -> fix immediately
   +-- Heavy images -> add CachedNetworkImage with size limits
```

### "State Is Inconsistent" (Riverpod Issues)

```
Common Riverpod bugs:
+-- Provider reading stale data: use ref.watch not ref.read in build
+-- Provider not rebuilding: check if you selected too narrowly with .select()
+-- Provider disposing too early: check scoping (ProviderScope vs nested scope)
+-- Async provider not loading: check AsyncValue.when() includes loading case

Debug with DevTools:
+-- DevTools -> Provider (Riverpod DevTools extension)
+-- Inspect current state of each provider
+-- See which widgets are listening to which providers
```

---

## 3. Platform-Specific Nightmares

### iOS

**Pod Issues:** If Flutter plugin native code is not linking:
```bash
cd ios
pod deintegrate
pod install
```

**Signing Errors:**
- Use xcodebuild MCP `show_build_settings` to see current signing config
- Check Team ID and Bundle Identifier match your Apple Developer account
- Use xcodebuild MCP `list_schemes` to verify scheme name

**Build Cache:**
- Product -> Clean Build Folder in Xcode
- Or delete `ios/build/` directory
- `flutter clean && flutter pub get` then rebuild

**First iOS build:** Always run `flutter build ios` once before using xcodebuild MCP. This generates the Xcode project and installs CocoaPods.

### Android

**Gradle Sync Fail:**
- Usually Java version mismatch or duplicate classes in dependencies
- Check `android/build.gradle` for conflicting versions
- Run `./gradlew clean` in `android/` directory

**Emulator Network:**
- `localhost` inside emulator is `10.0.2.2` — not `127.0.0.1`
- Update your API base URL for emulator builds

**Cached Builds:**
- `cd android && ./gradlew clean`
- Or delete `android/build/` directory

---

## 4. iOS Debug Workflow (xcodebuild MCP)

Full workflow for debugging an iOS issue:

```
1. discover_projs -> find ios/Runner.xcworkspace
2. list_schemes -> confirm "Runner" scheme exists
3. build_run_sim -> build, install, launch on simulator
4. start_sim_log_cap -> begin capturing logs
5. [Reproduce the issue in the app]
6. debug_attach_sim -> attach LLDB debugger
7. debug_breakpoint_add -> set breakpoint at suspect file:line
8. [Trigger the code path]
9. debug_variables -> inspect variable state
10. debug_stack -> view call stack
11. stop_sim_log_cap -> retrieve captured log output
```

---

## 5. Logging Best Practices in Flutter

```dart
// WRONG: print() blocks the UI thread in debug mode
// and has no log level or context
print('User data: $user'); // Never do this

// CORRECT: Use a structured logger
// Add to pubspec.yaml: logger: 2.8.0
import 'package:logger/logger.dart';

final _log = Logger();

// Usage with levels and context:
_log.d('Fetching user data', error: null, stackTrace: null);
_log.i('User logged in', error: null);
_log.w('Token refresh required');
_log.e('Payment failed', error: error, stackTrace: stackTrace);

// NEVER log:
// +-- Passwords or tokens
// +-- Full PII (name, email, phone) in production
// +-- Credit card numbers
```

---

## Debugging Checklist

- [ ] Is it a Dart crash (red screen) or native crash (home screen)? Identify the layer first.
- [ ] Did you read the full error message and stack trace?
- [ ] Are you testing on a real device (not just simulator)?
- [ ] Did you check Flutter DevTools (not just terminal output)?
- [ ] For iOS: did you check xcodebuild MCP logs or Xcode console?
- [ ] For Android: did you check `adb logcat *:E`?
- [ ] Did you run in profile mode before assuming a performance issue?
- [ ] Did you check Firebase Security Rules if Firestore reads/writes fail?

---

> **Remember:** If Dart looks perfect but the app fails, look at the native layer. If the native layer looks fine, look at the framework bridge. Read the actual logs — they almost always tell you exactly what is wrong.

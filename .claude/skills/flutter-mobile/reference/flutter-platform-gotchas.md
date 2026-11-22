# Flutter Platform Gotchas — Emulator, DevicePreview, Monorepo

Non-obvious rules for Flutter iOS/Android native config, device_preview automation gates,
and Melos monorepo invocation. These are earned lessons from production incidents — not
obvious from Flutter official docs.

---

## 1. Running Flutter in a Melos Monorepo

**Iron Law:** Never `flutter run -t apps/<app>/lib/main.dart` from the monorepo root.

Flutter walks up the directory tree looking for the nearest `pubspec.yaml`. In a Melos
workspace, it finds the **root** `pubspec.yaml` first — which has no `android/`, no `ios/`,
and no Flutter app structure. The result is cryptic failures like
"AndroidManifest.xml could not be found" or "v1 embedding not supported."

### Correct Invocation

```bash
# Preferred — make targets that regenerate dart_define.json and cd into the app dir
make run-<app>     # or equivalent project-specific make target

# Fallback (only if make unavailable) — cd into the app dir FIRST
cd apps/<app>
flutter run --device-id emulator-5554 \
  --dart-define-from-file=/absolute/path/to/project/dart_define.json
```

### Hard Rules

- Never `flutter run -t apps/<app>/lib/main.dart` from the monorepo root — Flutter
  resolves the project root to the Melos workspace `pubspec.yaml`.
- Never run `flutter pub get` inside an individual app directory — the workspace shares one
  lockfile and package config at the root. Always `melos bootstrap` from the repo root
  (workspace setup, overrides, run targets: [flutter-build-and-workspace.md](flutter-build-and-workspace.md)).
- Always use an **absolute** path for `--dart-define-from-file` — relative paths resolve
  against CWD, which is ambiguous in monorepos.
- If your project uses dart-define or a `.env`-backed `dart_define.json`, regenerate it
  before each run or you'll get stale config (wrong emulator hostnames, wrong API keys).

### Diagnostic Signals (failure = wrong working directory or stale dart-define)

- `AndroidManifest.xml could not be found`
- `Your app isn't using AndroidX. To avoid potential build failures...`
- `v1 embedding has been deprecated`
- Firebase/backend traffic goes to production hostnames instead of `10.0.2.2` or `localhost`

---

## 2. DevicePreview Android Gate

**Iron Law:** `DevicePreview(enabled: kDebugMode, ...)` silently breaks `adb shell input tap`
and Maestro `tapOn` on Android.

DevicePreview's `InteractiveViewer` wraps the entire app and intercepts all pointer events
before they reach the Flutter widget tree. Screenshots look correct, but no taps register.
Android emulators already provide the correct device frame — DevicePreview adds zero value
and actively blocks automation.

### Required Pattern

```dart
import 'dart:io' show Platform;

import 'package:device_preview/device_preview.dart';
import 'package:flutter/foundation.dart';

const bool _devicePreviewRequested = bool.fromEnvironment(
  'DEVICE_PREVIEW',
  defaultValue: false,
);

bool _shouldEnableDevicePreview() {
  if (!kDebugMode) return false;
  if (!_devicePreviewRequested) return false;
  if (kIsWeb) return true;
  return !Platform.isAndroid;
}

void main() => runApp(
  DevicePreview(
    enabled: _shouldEnableDevicePreview(),
    builder: (_) => const MyApp(),
  ),
);
```

### Hard Rules

- Never `DevicePreview(enabled: kDebugMode, ...)` — breaks Android automation
- Never `DevicePreview(enabled: !kReleaseMode, ...)` — same failure mode
- Always require explicit `--dart-define=DEVICE_PREVIEW=true` opt-in (default OFF)
- When the preview wrapper feeds the same `MaterialApp` property as a user preference (locale,
  theme), precedence must be `test override > user preference > preview > system`; a
  `DevicePreview.locale(context) ?? userPref` chain swallows the preference whenever the chrome is on
- Keep one shared gate helper, not per-app copies
- Always exclude Android (`!Platform.isAndroid`) — even when explicitly requested
- Web is exempt (`kIsWeb` returns true) — safe for responsive design exploration
- iOS is eligible but still requires the `DEVICE_PREVIEW=true` opt-in

### Diagnostic Signal

If `adb shell input tap` or Maestro `tapOn` silently no-op on an Android emulator while
visual screenshots look correct → check `main.dart`. Grep:

```bash
grep -rn "DevicePreview(" apps/*/lib/main.dart
# Every hit must call _shouldEnableDevicePreview() — no exceptions
grep -rn "DevicePreview(enabled: kDebugMode" apps/  # must return 0
grep -rn "DevicePreview(enabled: !kReleaseMode" apps/  # must return 0
```

---

## 3. Android Firebase Emulator — Debug-Only Cleartext Config

**Iron Law:** Android API 28+ blocks cleartext HTTP by default. The Firebase Auth emulator
runs on `10.0.2.2:9099` (the Android emulator's host loopback) over plain HTTP. Without an
explicit allowlist in debug builds only, Firebase calls fail with:

```
[firebase_auth/unknown] An internal error has occurred.
[ Cleartext HTTP traffic to 10.0.2.2 not permitted ]
```

The Firebase Auth Flutter plugin wraps this under the generic `[firebase_auth/unknown]` error
code — making the real cause invisible without digging into logcat.

### Required Files per Android App

**`android/app/src/debug/res/xml/network_security_config.xml`:**

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">10.0.2.2</domain>
        <domain includeSubdomains="true">localhost</domain>
        <domain includeSubdomains="true">127.0.0.1</domain>
    </domain-config>
</network-security-config>
```

**`android/app/src/debug/AndroidManifest.xml`** (manifest-merger overlay, debug only):

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
          xmlns:tools="http://schemas.android.com/tools">
    <uses-permission android:name="android.permission.INTERNET"/>
    <application
        android:networkSecurityConfig="@xml/network_security_config"
        tools:replace="android:networkSecurityConfig" />
</manifest>
```

### Variants and Additions

- Android's `network_security_config` has no CIDR or wildcard support. To reach a developer's LAN IP from a
  debug build, a single debug-only `<base-config cleartextTrafficPermitted="true"/>` is the correct tool;
  committing one machine's IP into `<domain>` entries is the anti-pattern (and never commit machine-specific
  values in tracked files).
- iOS equivalent for local-network development: `NSAllowsLocalNetworking`, never `NSAllowsArbitraryLoads`.
- Pre-commit greps: no private-IP literal in the debug xml; no `networkSecurityConfig` in `src/main`;
  no `cleartextTrafficPermitted="true"` in `src/release`.

### Hard Rules

- Never put `networkSecurityConfig` in `src/main/AndroidManifest.xml` — this leaks
  cleartext tolerance into release builds.
- In the debug overlay allowlist only `10.0.2.2`, `localhost`, `127.0.0.1` per-domain; for a physical device on a LAN use the debug-only `base-config` above instead of a machine IP. Never allowlist a production host.
- `xmlns:tools` MUST be on the root `<manifest>` element, not on `<application>` —
  putting it on `<application>` causes manifest-merger to silently drop the override.
- `tools:replace="android:networkSecurityConfig"` is required — without it, the
  merger complains about an attribute collision.
- Release builds MUST NOT have a `src/release/` counterpart — absence means Android
  falls back to the HTTPS-only default (correct production behavior).
- **Relaunch `flutter run` after creating these files** — the manifest merger runs at
  build time; hot-reload does not pick up native AndroidManifest changes.

### Diagnostic Signal

If logcat shows `W/LocalRequestInterceptor ... Cleartext HTTP traffic ... not permitted`:

1. `android/app/src/debug/AndroidManifest.xml` exists with `tools:replace`?
2. `android/app/src/debug/res/xml/network_security_config.xml` exists?
3. `xmlns:tools` is on root `<manifest>`, not `<application>`?
4. Did you restart `flutter run` (not hot-reload) after file creation?

---

## 4. iOS UIScene Lifecycle

Verified against Flutter's UIScene migration guide (docs.flutter.dev, `release/breaking-changes/uiscenedelegate`): beginning with Xcode 27 (iOS 27 SDK) Apple mandates the UIScene lifecycle for UIKit apps, and Flutter apps built with Xcode 27 that do not adopt it **fail to launch**. Flutter 3.41+ migrates an unmodified `AppDelegate` automatically; a customised `AppDelegate`, or an older Flutter, needs the manual steps. Re-read the guide for your Flutter version before editing — the native files change between releases.

**Iron Law:** Prefer Flutter's own UIScene migration. Do not hand-roll an engine unless you have reproduced a specific failure that the official path cannot solve.

### Default path (recommended)

```swift
// SceneDelegate.swift — subclass Flutter's delegate
import Flutter
import UIKit

class SceneDelegate: FlutterSceneDelegate {}
```

```swift
// AppDelegate.swift — register plugins when the implicit engine exists
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
  }
}
```

- `Info.plist` needs a `UIApplicationSceneManifest` whose `UISceneDelegateClassName` is the scene delegate class (the guide's sample uses `FlutterSceneDelegate`; use `$(PRODUCT_MODULE_NAME).SceneDelegate` for your own subclass).
- If you cannot subclass `FlutterSceneDelegate`, conform your `SceneDelegate` to `FlutterSceneLifeCycleProvider`, hold a `FlutterPluginSceneLifeCycleDelegate`, and forward **every** scene callback to it (`willConnectTo`, `sceneDidDisconnect`, `sceneWillEnterForeground`, `sceneDidBecomeActive`, `sceneWillResignActive`, `sceneDidEnterBackground`, `openURLContexts`, `continue userActivity`, shortcut items). A missed forward silently breaks plugins that listen to that callback (deep links, push, OAuth).
- Add `CFBundleURLTypes` entries for any OAuth/Firebase Auth reversed-client-id URL scheme.

### Fallback only: explicit engine owned by a custom scene delegate

An earlier investigation of a black screen led to a rule that forbade subclassing `FlutterSceneDelegate`. The investigation had several stacked causes (a plugin platform-interface version mismatch fixed with a root pin was one), so that "never" is not supported by the current docs. If — and only if — you reproduce a failure on the default path, document it in the PR and use this pattern:

```swift
class SceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?
  private var engine: FlutterEngine?

  func scene(_ scene: UIScene, willConnectTo session: UISceneSession,
             options connectionOptions: UIScene.ConnectionOptions) {
    guard let windowScene = scene as? UIWindowScene else { return }
    let flutterEngine = FlutterEngine(name: "main")
    flutterEngine.run()                                   // BEFORE plugin registration
    GeneratedPluginRegistrant.register(with: flutterEngine)
    engine = flutterEngine
    let controller = FlutterViewController(engine: flutterEngine, nibName: nil, bundle: nil)
    window = UIWindow(windowScene: windowScene)
    window?.rootViewController = controller
    window?.makeKeyAndVisible()
  }
}
```

When you own the engine, **nothing else delivers URLs, links or lifecycle to Flutter**, so you must forward them yourself:

| Concern | Rule |
|---------|------|
| `AppDelegate` | Still call `super.application(...)` (initialises the plugin lifecycle delegate) |
| OAuth callbacks (Firebase Auth) | In `scene(_:openURLContexts:)` call `Auth.auth().canHandle(url)` first; `continue` to the next context when handled. Forwarding through `UIApplication.shared.delegate` drops URLs |
| Cold-launch deep link | Arrives in `scene(_:willConnectTo:options:)` via `connectionOptions.urlContexts`, **not** `openURLContexts`. Pass it as the engine's `initialRoute` |
| Route validation | Map only your own scheme/host to a route; reject paths with encoded separators (`%2F %5C %3F %23 %2E`), `%25`, or dot segments |
| Warm link while no router is listening (before `runApp`, or behind a splash until auth resolves) | `pushRouteInformation` answers `false` and a fire-and-forget push is lost. Read the result and retry on a timer; newest link wins |
| `Info.plist` | Remove `UIMainStoryboardFile` and `UISceneStoryboardFile` to avoid a second engine |

Cold-link and warm-link flows both need a device test; a build with the splash disabled hides the dropped-link case.

## Pre-Commit Checklist (Platform/Emulator)

```
Monorepo flutter run
  □ Used make target or cd apps/<app> — never flutter run -t from monorepo root
  □ dart-define file regenerated from .env before the run
  □ Absolute path used for --dart-define-from-file

DevicePreview
  □ grep -rn "DevicePreview(" apps/*/lib/main.dart → every hit calls _shouldEnableDevicePreview()
  □ grep -rn "DevicePreview(enabled: kDebugMode" apps/ → must return 0
  □ grep -rn "DevicePreview(enabled: !kReleaseMode" apps/ → must return 0

Android Cleartext Config (Firebase emulator)
  □ android/app/src/debug/AndroidManifest.xml has networkSecurityConfig + tools:replace
  □ debug network_security_config.xml allowlists only loopback hosts (or a debug-only base-config); no machine IP committed
  □ grep -r "networkSecurityConfig" android/app/src/main/ → must return 0
  □ grep -r "cleartextTrafficPermitted.*true" android/app/src/release/ → must return 0
  □ xmlns:tools on root <manifest>, not <application>

iOS UIScene
  □ Followed the current Flutter UIScene migration guide (FlutterSceneDelegate or FlutterSceneLifeCycleProvider)
  □ Plugins registered in didInitializeImplicitFlutterEngine; AppDelegate calls super
  □ Custom-engine fallback used only with a documented reproduced failure; then URLs/links forwarded manually
  □ Info.plist has UIApplicationSceneManifest; no UIMainStoryboardFile/UISceneStoryboardFile if you own the engine
  □ dependency_overrides only in the workspace root pubspec (see flutter-build-and-workspace.md)
```

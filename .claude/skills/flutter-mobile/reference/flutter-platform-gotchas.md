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

**Iron Law:** Device Preview never runs under device automation. Turn it on only by explicit
opt-in, never on Android, never in release.

`device_preview` 3.0.0 (requires Flutter >= 3.47) is a rebuild: a custom `WidgetsBinding`
simulates screen metrics, safe areas, locale, text scale and the target platform below the
widget layer, and its UI moved to a Flutter DevTools tab. The 2.x widget wrapper
(`DevicePreview(enabled:, builder:)`, `DevicePreview.appBuilder`, `DevicePreview.locale(context)`)
no longer exists and fails to compile against 3.0.0 (tested). In 2.x the wrapper's
`InteractiveViewer` swallowed `adb shell input tap` and Maestro `tapOn` on Android. In 3.0 the
binding rescales the simulated screen and rewrites pointer input (mouse reported as a finger),
so coordinates sent by a device tool no longer map one-to-one either; whether taps still land on
an Android emulator under 3.0 is UNVERIFIED. Either way, an emulator or simulator already is the
device: simulation adds nothing there.

### Required Pattern

```dart
import 'dart:io' show Platform;

import 'package:device_preview/device_preview.dart';
import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';

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

void main() {
  // Install the simulation binding only when gated on; otherwise the normal
  // binding runs and the package does nothing.
  if (_shouldEnableDevicePreview()) DevicePreview.enable();
  runApp(const MyApp());
}
```

### Hard Rules

- Never call `DevicePreview.enable()` unconditionally — it defaults to `!kReleaseMode`, i.e. on in
  debug **and profile** builds, including on an emulator under Maestro
- Always require explicit `--dart-define=DEVICE_PREVIEW=true` opt-in (default OFF)
- Delete 2.x glue when upgrading: the `DevicePreview(builder:)` wrapper and the `MaterialApp`
  `useInheritedMediaQuery`, `locale: DevicePreview.locale(context)` and `builder: DevicePreview.appBuilder` lines
- Locale and theme precedence stays `test override > user preference > system`; Device Preview 3
  simulates the system locale below the widget tree, so it no longer competes with an app setting
- Keep one shared gate helper, not per-app copies
- Always exclude Android (`!Platform.isAndroid`) — even when explicitly requested
- Web is exempt (`kIsWeb` returns true) — safe for responsive design exploration
- iOS is eligible but still requires the `DEVICE_PREVIEW=true` opt-in

### Diagnostic Signal

If `adb shell input tap` or Maestro `tapOn` silently no-op or hit the wrong widget on an
Android emulator while screenshots look correct → check `main.dart`. Grep:

```bash
grep -rn "DevicePreview" apps/*/lib/main.dart
# Every DevicePreview.enable( call must sit behind _shouldEnableDevicePreview() — no exceptions
grep -rn "DevicePreview(enabled:" apps/  # 2.x wrapper: must return 0 on device_preview 3
grep -rn "DevicePreview.appBuilder\|DevicePreview.locale(" apps/  # 2.x glue: must return 0
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

## 5. Native Toolchain Floors (Flutter 3.50)

Read from the Flutter 3.50.1 tool templates (`gradle_utils.dart`, iOS project template) and confirmed by a debug APK and an iOS simulator build of a template app on these values (both exit 0). Move an older project to the same set; the tool's compatibility table pairs each AGP line with a minimum Gradle (AGP 9.3.x needs Gradle 9.5.0, AGP 9.1.x needs 9.3.1).

| Setting | Flutter 3.50 template | Where |
|---------|-----------------------|-------|
| Gradle | 9.5.0 (the minimum for AGP 9.3.x) | `android/gradle/wrapper/gradle-wrapper.properties` |
| Android Gradle Plugin | 9.3.1 | `android/settings.gradle.kts` (`com.android.application`) |
| Kotlin Gradle plugin | 2.4.20 | `android/settings.gradle.kts` (`org.jetbrains.kotlin.android`) |
| Java source/target, `jvmTarget` | 17 | `android/app/build.gradle.kts` |
| `minSdk` / `compileSdk` / `targetSdk` | `flutter.minSdkVersion` 24 / `flutter.compileSdkVersion` 36 / `flutter.targetSdkVersion` 36 | `android/app/build.gradle.kts` — keep the `flutter.*` values unless a plugin needs more (`compileSdk = 37` for `permission_handler` 13.0.2 via `permission_handler_android` 14.1.1, and for `flutter_local_notifications` 23.0.4, which also needs core library desugaring: `isCoreLibraryDesugaringEnabled = true` plus `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")`; build fails on 36 without them) |
| iOS deployment target | 15.0 (the tool raises 13.0 automatically on first build) | Xcode project; several plugins (e.g. `image_picker_ios`, `google_maps_flutter_ios`) require 15.0 |
| iOS dependency manager | Swift Package Manager, on by default on stable | Plugins without a `Package.swift` (e.g. `google_maps_flutter_ios`) still use CocoaPods: the project runs in mixed mode |

- Under Swift Package Manager, `permission_handler` enables a permission only when its `Info.plist` usage key is present; the old `Podfile` `GCC_PREPROCESSOR_DEFINITIONS` macros no longer apply.
- Native assets (build hooks that compile or bundle native code, e.g. `sqlite3` 3.x) are enabled by default on stable; do not add the end-of-life `sqlite3_flutter_libs` / `sqlcipher_flutter_libs` packages (see the offline-sync reference).
- Upgrade path for an existing app: set the wrapper, AGP and Kotlin versions above, then run `flutter build apk --debug` and `flutter build ios --simulator --debug`, each with its own exit code.

## 6. Feature Preflights (answer before writing the screen)

Three questions that, left implicit, cause rework after the screen is built.

**Refresh strategy.** For every list or detail screen, state in the plan which one applies and why: a live stream (Firestore snapshots, WebSocket: no refresh control, but show a reconnecting state), pull-to-refresh on a fetched list (`RefreshIndicator`, the future completes only when new data is in state), refetch on app resume or route re-entry (a lifecycle listener), or none (static content). Also say what the user sees while stale data is shown, and how a failed refresh is reported (it keeps the old data and shows an error, never an empty list). See `flutter-offline-cache-and-reads.md` for cache-first reads.

**Media input.** Before adding camera or gallery input, decide: the source (camera, gallery or both); iOS usage strings in `Info.plist` (`NSCameraUsageDescription`, `NSPhotoLibraryUsageDescription`), which are required or the app is killed on first access; on Android, prefer the system photo picker, which needs no storage permission; the user cancelling (a `null` result is not an error); a size cap and downscale before upload; stripping EXIF location before upload; and the upload path (signed URL, see `database-schema-designer/reference/firestore-storage-security.md`). Maestro flows cover the permission-denied path on a device, never a browser.

**Widget preview.** The Flutter Widget Previewer is stable since Flutter 3.47 (`flutter widget-preview start`, or the IDE "Flutter Widget Preview" tab; `@Preview` from `package:flutter/widget_previews.dart` on top-level functions, static methods or no-argument public constructors). Add previews for dumb widgets in loading, empty, error and long-text states, light and dark. Limits from the docs: it runs on Flutter Web, so native plugins and `dart:io` / `dart:ffi` calls throw; asset paths must be package-based. A preview is design feedback, never test evidence (widget tests and Maestro are). Source: docs.flutter.dev/tools/widget-previewer (checked 2026-11-24, "reflects Flutter 3.50").

## Pre-Commit Checklist (Platform/Emulator)

```
Monorepo flutter run
  □ Used make target or cd apps/<app> — never flutter run -t from monorepo root
  □ dart-define file regenerated from .env before the run
  □ Absolute path used for --dart-define-from-file

DevicePreview
  □ device_preview 3.x: DevicePreview.enable() only behind _shouldEnableDevicePreview()
  □ grep -rn "DevicePreview(enabled:" apps/ → must return 0 (2.x wrapper)
  □ grep -rn "DevicePreview.appBuilder\|DevicePreview.locale(" apps/ → must return 0 (2.x glue)

Android Cleartext Config (Firebase emulator)
  □ android/app/src/debug/AndroidManifest.xml has networkSecurityConfig + tools:replace
  □ debug network_security_config.xml allowlists only loopback hosts (or a debug-only base-config); no machine IP committed
  □ grep -r "networkSecurityConfig" android/app/src/main/ → must return 0
  □ grep -r "cleartextTrafficPermitted.*true" android/app/src/release/ → must return 0
  □ xmlns:tools on root <manifest>, not <application>

Toolchain floors
  □ Gradle 9.5.0, AGP 9.3.1, Kotlin 2.4.20, Java 17; minSdk/compileSdk/targetSdk from flutter.*
  □ iOS deployment target 15.0; SwiftPM on; usage-description keys present for every requested permission
  □ flutter build apk --debug and flutter build ios --simulator --debug exit 0

iOS UIScene
  □ Followed the current Flutter UIScene migration guide (FlutterSceneDelegate or FlutterSceneLifeCycleProvider)
  □ Plugins registered in didInitializeImplicitFlutterEngine; AppDelegate calls super
  □ Custom-engine fallback used only with a documented reproduced failure; then URLs/links forwarded manually
  □ Info.plist has UIApplicationSceneManifest; no UIMainStoryboardFile/UISceneStoryboardFile if you own the engine
  □ dependency_overrides only in the workspace root pubspec (see flutter-build-and-workspace.md)
```

# Flutter Build, Workspace and Run-Target Traps

Read this when setting up or debugging a multi-package workspace, running the app against a local backend (simulator, emulator, physical device), tuning Gradle memory, handling server-signed upload URLs, moving CPU-heavy work off the UI isolate, or touching media-encoder settings. Platform-native config (cleartext overlay, DevicePreview, UIScene) lives in [flutter-platform-gotchas.md](flutter-platform-gotchas.md); security rules live in [flutter-security-hardening.md](flutter-security-hardening.md).

---

## 1. Pub Workspaces and Melos 7+

Verified against the Melos migration guide and dart.dev pub workspaces docs. Applies **if the project uses Melos ≥ 7** (Dart SDK 3.9+; the 7.x and 8.x workspace shape is the same). Older Melos used `melos.yaml` and generated `pubspec_overrides.yaml`; that shape is obsolete.

```yaml
# ROOT pubspec.yaml
name: my_workspace
publish_to: none
environment:
  sdk: ^3.9.0
workspace:
  - apps/my_app
  - packages/shared_ui
  - packages/core
dev_dependencies:
  melos: 8.10.1     # current stable on pub.dev when written; re-check. Commit the root pubspec.lock

melos:
  # scripts / command config (what used to be in melos.yaml, minus name + packages)
```

```yaml
# EVERY member pubspec.yaml
name: shared_ui
environment:
  sdk: ^3.9.0
resolution: workspace
```

| Rule | Why |
|------|-----|
| No `melos.yaml`; list members under root `workspace:` | Melos 7 does not read `melos.yaml`; `melos.packages` was removed |
| Every member has `resolution: workspace` | Without it the member resolves on its own and drifts from the shared lockfile |
| Run `melos bootstrap` at the root after any workspace change | It runs `pub get` once for the whole workspace |
| Install from the workspace root | One shared `pubspec.lock` + `.dart_tool/package_config.json` live at the root. `flutter pub get` inside a member resolves the same workspace and also works (verified on Flutter 3.44.2), but CI and scripts should run from the root so every package sees one resolution |
| Do not hand-write `pubspec_overrides.yaml` to link local packages | The workspace links them: depend on a member by name with a version constraint (e.g. `shared_ui: ^0.1.0`); the local copy is used and must satisfy it. No `path:` needed |
| Globs in `workspace:` need Dart 3.11+ | On older SDKs list each path explicitly |
| Keep application code out of the root | Root is the workspace host; use `useRootAsPackage: true` only if the root must be a package |

`dependency_overrides`: pub allows them in any member, but **a package can be overridden only once across the workspace**, so duplicates fail resolution. Keep every override in the root pubspec, with a comment saying why and when to remove it.

Packages shared by several apps follow the "shared-first" rule: a package that only an app's shared layer needs (HTTP client, local DB, key-value store, font loader) is declared in the shared package, not re-declared in each app. Every dependency a shared package declares must be imported by it. After changing a shared barrel file, run `flutter analyze` for **every** app: a new top-level symbol can cause an `ambiguous_import` in an app that is not in your diff.

> Rule of Three applies within one app. Two separately shipped apps carrying the same file is already the trigger to hoist it into a shared package.

---

## 2. Running Against a Local Backend

The same code needs a different host per run target:

| Target | Host that reaches the dev machine |
|--------|-----------------------------------|
| iOS simulator, desktop, web | `localhost` |
| Android emulator | `10.0.2.2` (emulator alias for the host loopback) |
| Physical device (either OS) | The dev machine's LAN IP — neither of the above works |

Rules:

- Resolve the host in **one** config class. The physical-device LAN IP is injected at build time (`--dart-define` / `--dart-define-from-file`), never typed into feature code.
- An explicit HTTPS base-URL define for deployed builds short-circuits the local-host logic. In release mode, throw at startup if a base URL is not HTTPS (`assertHttpsInRelease()`), so a mis-set URL fails fast instead of sending a bearer token in cleartext.
- Emulator-host overrides for local Firebase emulators must follow the same address. Symptom of a mismatch: the device reaches your API but sign-in fails — an auth-shaped symptom with a networking cause.
- A LAN IP stored in an env file goes stale when the machine's IP changes. Before any automated run in physical-device mode, compare it with the current interface address.
- Test the host-resolution branch both ways (plain `flutter test` and with `--dart-define=BACKEND_HOST=10.1.2.3`). Because a define is compile-time, an "adaptive" test can pass vacuously: include a control that proves the branch actually differed.
- Resolve the target device id before `flutter run`: `emulator-5554` is a **slot**, not an identity (a different AVD can answer on it), and an unqualified `adb` command fails once a second device is attached. Pass `-s <serial>` to `adb`; resolve an iOS device/simulator UDID with `flutter devices` instead of typing it.

---

## 3. Server-Signed URLs Are Minted, Never Rewritten

Applies to any upload/download through presigned or signed URLs.

- Never rewrite any part of a URL the server signed (host, path, scheme, or a per-platform branch on `kIsWeb` / `defaultTargetPlatform`). Signature schemes of the V4 family bind the host; a rewritten URL fails verification, and the failure usually surfaces far from the cause (a queued upload goes dead with a "not found"-style rejection).
- Reachability is the **signer's** job. If the device cannot reach the host in the signed URL, fix it where the URL is minted (a public-host setting on the signer), not at the call site.
- Never put an emulator hostname (`10.0.2.2`) in shared or app code to "fix" a signed URL. Never use `NSAllowsArbitraryLoads` to work around it.
- Pin the rule with a test: the signed URL passed to the HTTP client equals the one returned by the API, byte for byte.
- Size the send timeout per payload (bytes ÷ minimum throughput), clamped to the URL's remaining lifetime; a plain default client timeout is wrong for large transfers. See [flutter-network-resilience.md](flutter-network-resilience.md) for the retry/timeout layers.

---

## 4. Gradle Daemon Memory

`org.gradle.jvmargs` in `android/gradle.properties` is roughly the daemon's steady-state cost: the daemon persists between builds and keeps its heap. Size it for the **developer machine**, not CI.

```properties
# android/gradle.properties — example for a 16 GB laptop (measure your own)
org.gradle.jvmargs=-Xmx2G -XX:MaxMetaspaceSize=1G -XX:+HeapDumpOnOutOfMemoryError -Dfile.encoding=UTF-8
```

- Do not set a ceiling a single daemon cannot coexist with Docker, an emulator, a simulator and an editor (for example `-Xmx8G -XX:MaxMetaspaceSize=4G` on 16 GB).
- Keep `-XX:+HeapDumpOnOutOfMemoryError`. `-Xmx` caps the heap, not resident memory: a 2 GB heap shows up around 2.4 GB in the process list.
- The Kotlin compile daemon is separate: tune it with `kotlin.daemon.jvmargs`.
- `./gradlew --stop` (from `android/`) reclaims idle daemons.
- After changing the cap, build every app in the workspace; a too-low cap fails with `OutOfMemoryError` only on the biggest app.
- On macOS, processes started from an editor's terminal are attributed to the editor in Activity Monitor; walk the process tree before calling it an editor leak.
- The numbers above are an example, not a rule. Verify with `ps`/Activity Monitor across a full sequential build of all apps.

---

## 5. CPU Work: `Isolate.run`

`async`/`await` yields for I/O; it never fixes CPU blocking. Any synchronous work longer than a frame budget (about 16 ms at 60 Hz, 8 ms at 120 Hz) on the UI isolate drops frames (large JSON decode, image/PDF processing, encryption, sorting big lists).

```dart
import 'dart:convert';
import 'dart:isolate';

Future<List<Order>> parseOrders(String body) =>
    Isolate.run(() => (jsonDecode(body) as List<Object?>)
        .map((e) => Order.fromJson(e! as Map<String, Object?>))
        .toList());
```

| Need | Use |
|------|-----|
| One-off heavy computation | `Isolate.run(() => ...)` (Dart 2.19+; the recommended API) |
| Repeated jobs / streaming results | Long-lived worker via `Isolate.spawn` + ports; close `ReceivePort`s on dispose or the isolate lives forever |
| Large byte buffers | Send as `TransferableTypedData` to avoid copies |

Rules: the closure must not capture `BuildContext`, a Riverpod `Ref`, or anything from a UI-isolate plugin (platform channels are not available in a background isolate unless initialized for it); captured and returned data is copied or transferred, so keep payloads small; hide the call behind a provider/repository so screens stay dumb. Measure first (DevTools timeline) — do not isolate work that fits in a frame.

---

## 6. Media Encoders: Never Trust Plugin Defaults

A plugin's default bit rate / sample rate can be accepted on Android and rejected on iOS (Apple's AAC encoder limits which bit-rate/sample-rate/channel combinations are valid). Failure mode: the recorder "starts" and "stops" successfully but produces a header-only file that uploads fine and fails server-side.

- Set every encoder parameter explicitly (codec, sample rate, channels, bit rate).
- Validate the output with a platform tool (`afconvert` / `afinfo` on macOS for iOS audio) and pin the configuration in a unit test.
- When a media feature works on Android but fails on iPhone with a server-side "invalid argument", log the uploaded **byte count** first.

---

## 7. iOS Facts for Verifying a Signed-Out Launch

- Deleting an iOS app does **not** clear its keychain. Firebase Auth (and any keychain-backed token) restores the session on next launch, so a "fresh install" measures a signed-in boot.
- On the **simulator only**: `xcrun simctl keychain booted reset` clears it. Never run it against a physical device.
- Confirm which shape you measured: a signed-in launch sends `Authorization` on every read.
- When counting requests from device logs, positive-control the matcher (widen the time window) so "zero" means no requests rather than a wrong grep.
- The ordering rule that makes a signed-out boot send no authenticated requests is covered in [flutter-navigation-and-auth-boot.md](flutter-navigation-and-auth-boot.md).

---

## 8. Android Predictive Back — Platform Side

Opt in at the application level (verified, Flutter predictive-back docs):

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<application
    android:enableOnBackInvokedCallback="true"
    ... >
```

- Use `PopScope(canPop:, onPopInvokedWithResult:)`; `WillPopScope` is deprecated.
- `canPop` is evaluated **before** the gesture, so it must reflect current state (rebuild when it changes), not be decided inside the callback.
- Router-level back handling (nested navigators, overlays above a shell) is a navigation concern: see [flutter-navigation-and-auth-boot.md](flutter-navigation-and-auth-boot.md).
- Test predictive back on a real Android 13+ device or emulator; widget tests that call `pop` cannot observe the platform's pre-gesture query.

---

## Pre-Commit Checklist

```
Workspace
  □ No melos.yaml; root pubspec has workspace: list and melos config
  □ Every member pubspec has resolution: workspace
  □ dependency_overrides only in the root pubspec, each with a reason
  □ flutter analyze run for every app after any shared-package change
Run targets
  □ Backend host resolved in one config class; LAN IP injected via define
  □ Release builds assert HTTPS base URL
Signed URLs
  □ No code rewrites a signed URL; a test pins "used verbatim"
Gradle
  □ jvmargs sized for dev machines; HeapDumpOnOutOfMemoryError kept
CPU work
  □ Work >1 frame budget goes through Isolate.run / worker, no captured UI objects
Media
  □ Encoder rate/channels set explicitly and covered by a test
```

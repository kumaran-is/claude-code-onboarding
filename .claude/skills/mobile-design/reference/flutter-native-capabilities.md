# Flutter Native Capabilities — Plugins, Floors and Permissions

Device features (camera, gallery, location, maps, files, PDF, audio, speech, contacts, sharing, links) on
**Flutter 3.50.1 / Dart 3.14.0**. Every pin below was resolved together in one app (`flutter pub get` exit 0) with
`material_ui: 1.11.1`; the app analyzes with zero issues and its tests pass. Floors come from each plugin's own
`build.gradle`, `Package.swift` and podspec in the pub cache, not from memory. Re-verify before raising a pin.

Read with: `platform-android.md`, `platform-ios.md` (HIG/Material behaviour), `mobile-backend.md` (uploads),
`.claude/skills/flutter-mobile/` (architecture). Device UI tests: Maestro only.

## 1. App-level floors (Flutter 3.50.1 templates)

| Setting | Value | Why |
|---|---|---|
| Android `minSdk` | 24 | template default; google_maps_flutter_android, image_picker_android, permission_handler_android, record_android, gal, flutter_contacts all declare 24 |
| Android `compileSdk` | **37** when `permission_handler` is used, else 36 | permission_handler_android 14.1.1 compiles against 37; Flutter warns and asks for 37 |
| Android `targetSdk` | 36 | template default |
| Gradle / AGP / Kotlin Gradle plugin | 9.5.0 / 9.3.1 / 2.4.20 | template defaults; Gradle below 9.3.1 fails `flutter build apk` |
| iOS deployment target | **15.0** (Podfile and Runner target) | image_picker_ios 0.8.13+16 and google_maps_flutter_ios need 15.0; file_picker needs 14.0 |
| iOS dependency manager | Swift Package Manager (default) | google_maps_flutter_ios is still CocoaPods-only, so a Maps app builds in mixed mode (`pod install` runs) |

Build warnings seen on 3.50.1 that are not errors yet: plugins that still apply the Kotlin Gradle plugin
(`flutter_image_compress_common`, `rive_native`) are flagged "Future versions of Flutter will fail to build". Track
upstream releases; do not fork or patch them.

## 2. Verified plugin set

| Capability | Package (pin) | Android floor | iOS floor | Permission declarations |
|---|---|---|---|---|
| Camera / gallery pick | `image_picker: 1.2.4` | minSdk 24 | 15.0 | iOS `NSCameraUsageDescription`, `NSPhotoLibraryUsageDescription`. Android: none for the system photo picker; add `CAMERA` only if the app itself declares it |
| Compress before upload | `flutter_image_compress: 2.5.1` | minSdk 21 | 9.0 | none |
| Save to gallery | `gal: 3.0.1` | minSdk 24 | 13.0 | iOS `NSPhotoLibraryAddUsageDescription` |
| Barcode / QR | `mobile_scanner: 7.5.0` | minSdk 23 | 12.0 | `CAMERA`; iOS `NSCameraUsageDescription` |
| Location | `geolocator: 14.1.2` (+ `geolocator_android 5.2.1`, `geolocator_apple 2.4.3`) | template | 11.0 | `ACCESS_FINE_LOCATION`/`ACCESS_COARSE_LOCATION`; iOS `NSLocationWhenInUseUsageDescription` |
| Maps | `google_maps_flutter: 2.19.0` (Flutter >= 3.47) | minSdk 24 | 15.0, CocoaPods | API key via manifest meta-data / `AppDelegate` from build config, never in Dart source |
| Pick files | `file_picker: 13.4.1` | template | 14.0 | none (system picker) |
| Paths | `path_provider: 2.1.6` | template | template | none |
| Generate PDF | `pdf: 3.13.1` (pure Dart) | — | — | none |
| Print / share PDF | `printing: 5.15.1` | minSdk 21 | 13.0 | none |
| View PDF | `pdfrx: 3.1.0` (needs Flutter >= 3.50, Dart ^3.14) | template | template | none |
| Record audio | `record: 7.2.0` | minSdk 24 | 12.0 | `RECORD_AUDIO`; iOS `NSMicrophoneUsageDescription` |
| Speech to text | `speech_to_text: 7.5.0` | minSdk 21 | 13.0 | `RECORD_AUDIO`; iOS `NSMicrophoneUsageDescription` + `NSSpeechRecognitionUsageDescription` |
| Contacts | `flutter_contacts: 2.6.0` | minSdk 24, compileSdk 36 | 13.0 | `READ_CONTACTS` (`WRITE_CONTACTS` only if writing); iOS `NSContactsUsageDescription` |
| Share | `share_plus: 13.3.1` | minSdk 21 | 13.0 | none |
| Open links | `url_launcher: 6.3.3` | minSdk 24 | 13.0 | Android 11+ `<queries>` for the schemes you check with `canLaunchUrl` |
| App version | `package_info_plus: 10.2.2` | minSdk 19 | 13.0 | none |
| Runtime permissions | `permission_handler: 13.0.2` | minSdk 24, **compileSdk 37** | 12.0 | see §4 |

Media display used with these: `cached_network_image: 4.0.7`, `flutter_svg: 2.5.0`, `lottie: 3.8.2`,
`rive: 0.14.11` (see `flutter-animations`). Icons: Material `Icons` (font from `uses-material-design: true`) or
`material_symbols_icons: 4.2960.0`; `phosphor_flutter` 2.1.0 has had no release since 2024-05 — prefer the Material
sets for new code.

## 3. One service, explicit outcomes

Wrap plugins behind a small service that returns every outcome, including "the user said no". The UI renders each
case; nothing fails silently. Verified: analyze 0; 5 unit tests pass with a fake `ImagePicker` (granted, cancelled,
access denied, unexpected platform error reported, non-https URL refused).

```dart
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

/// Outcome of a device-capability call. The UI shows every non-success case.
sealed class CapabilityResult<T> {
  const CapabilityResult();
}

final class Granted<T> extends CapabilityResult<T> {
  const Granted(this.value);
  final T value;
}

final class Cancelled<T> extends CapabilityResult<T> {
  const Cancelled();
}

final class Denied<T> extends CapabilityResult<T> {
  const Denied({required this.permanently});

  /// True when only the system Settings app can re-enable it.
  final bool permanently;
}

final class Failed<T> extends CapabilityResult<T> {
  const Failed(this.error, this.stackTrace);
  final Object error;
  final StackTrace stackTrace;
}

typedef ErrorReporter = void Function(
  Object error,
  StackTrace stack,
  String operation,
);

class DeviceCapabilities {
  DeviceCapabilities({required this.report, ImagePicker? picker})
    : _picker = picker ?? ImagePicker();

  final ErrorReporter report;
  final ImagePicker _picker;

  /// Photo from camera or gallery, downscaled on device before upload.
  Future<CapabilityResult<XFile>> pickPhoto(ImageSource source) async {
    try {
      final file = await _picker.pickImage(
        source: source,
        maxWidth: 2048,
        imageQuality: 85,
      );
      return file == null ? const Cancelled() : Granted(file);
    } on PlatformException catch (e, st) {
      // e.g. camera_access_denied / photo_access_denied
      if (e.code.contains('access_denied')) {
        return const Denied(permanently: false);
      }
      report(e, st, 'pickPhoto');
      return Failed(e, st);
    }
  }

  /// Current position with the permission flow geolocator expects.
  Future<CapabilityResult<Position>> currentPosition() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        return const Denied(permanently: false);
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.deniedForever) {
        return const Denied(permanently: true);
      }
      if (permission == LocationPermission.denied) {
        return const Denied(permanently: false);
      }
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 15),
        ),
      );
      return Granted(position);
    } on Exception catch (e, st) {
      report(e, st, 'currentPosition');
      return Failed(e, st);
    }
  }

  /// Opens an https URL outside the app; anything else is refused.
  Future<bool> openExternal(Uri uri) async {
    if (uri.scheme != 'https') return false;
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened) {
      report(
        StateError('launchUrl returned false'),
        StackTrace.current,
        'openExternal',
      );
    }
    return opened;
  }

  Future<ShareResult> shareFile(XFile file, {String? text}) =>
      SharePlus.instance.share(ShareParams(files: [file], text: text));

  /// Sends the user to this app's page in system Settings.
  Future<bool> openSettings() => Geolocator.openAppSettings();
}
```

Rules:
- Ask for a permission **at the moment of use**, after a sentence in your UI explaining why. Never on app start.
- `Denied(permanently: true)` → show an explanation with a button that calls `openSettings()`. Do not loop prompts.
- Downscale on device (`maxWidth`, `imageQuality`, or `flutter_image_compress`) before uploading.
- Treat picked files as untrusted: check MIME type and size before upload (see `security-reviewer` file-upload rules).
- Only open `https` URLs (or an explicit allow-list of schemes); never pass user text straight to `launchUrl`.

## 4. Permission keys and how they fail

- **iOS: a missing usage-description key is not a build error.** Verified on 3.50.1: removing
  `NSMicrophoneUsageDescription` still produced `✓ Built Runner.app` (exit 0); iOS terminates the app the first time
  the microphone is requested. Guard it in CI with a check that reads `pubspec.lock` and `Info.plist`:

```bash
# Fails when a plugin in pubspec.lock needs an iOS usage key that Info.plist lacks (macOS, plutil).
set -u
lock=pubspec.lock; plist=ios/Runner/Info.plist
need() {
  case "$1" in
    image_picker) echo NSPhotoLibraryUsageDescription NSCameraUsageDescription ;;
    mobile_scanner) echo NSCameraUsageDescription ;;
    record) echo NSMicrophoneUsageDescription ;;
    speech_to_text) echo NSMicrophoneUsageDescription NSSpeechRecognitionUsageDescription ;;
    geolocator) echo NSLocationWhenInUseUsageDescription ;;
    flutter_contacts) echo NSContactsUsageDescription ;;
    gal) echo NSPhotoLibraryAddUsageDescription ;;
  esac
}
fail=0
for pkg in image_picker mobile_scanner record speech_to_text geolocator flutter_contacts gal; do
  grep -qE "^  $pkg:$" "$lock" || continue
  for key in $(need "$pkg"); do
    [ -n "$(plutil -extract "$key" raw -o - "$plist" 2>/dev/null)" ] || { echo "FAIL $pkg needs $key" >&2; fail=1; }
  done
done
exit "$fail"
```
  Verified: exit 0 with all keys; exit 1 naming the key when one is removed.
- **iOS + permission_handler under Swift Package Manager:** a permission group is compiled in only when its
  `Info.plist` key exists. The old Podfile `GCC_PREPROCESSOR_DEFINITIONS` macros (`PERMISSION_CAMERA=1`) no longer
  apply under SwiftPM; keep them only for CocoaPods builds.
- **Usage strings are user-facing copy:** say what the app does with the data ("Scan receipts to fill in expenses"),
  localise them (`InfoPlist.strings`), and never promise more than the code does.
- **Android:** declare only permissions you use; Play review rejects unused sensitive permissions. Location in the
  background needs `ACCESS_BACKGROUND_LOCATION` and a separate, later request; foreground-only apps must not declare it.
  Android 13+ photo picker needs no storage permission; do not add `READ_EXTERNAL_STORAGE` for it.

## 5. Verification checklist

- [ ] All capability pins resolved together on the project's Flutter version (`flutter pub get` exit 0), no `dependency_overrides`
- [ ] `flutter analyze` 0 issues; unit tests cover granted, cancelled, denied and failed outcomes
- [ ] `flutter build apk --debug` and `flutter build ios --simulator --no-codesign` exit 0 (record exit codes)
- [ ] Usage-key check exits 0, and exits 1 on a copy with one key removed
- [ ] Permission prompts and denial paths exercised on an Android emulator and an iOS simulator with Maestro;
      no device → BLOCKED, never a browser substitute
- [ ] Denied-forever path shows a Settings button; no silent empty state

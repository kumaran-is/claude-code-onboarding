# Flutter Security — Client Trust, Debug Gates, Fail-Closed Settings

Read this when deciding what may live in the app binary (keys, secrets, privileged calls), adding a debug/test affordance, encrypting a local database, implementing an app-lock or other security preference, auditing logs for sensitive data, or handling push messages. Companion to [flutter-security-hardening.md](flutter-security-hardening.md) (storage, pinning, biometrics, token refresh, privacy) — this file does not repeat those.

---

## 1. A Shipped App Is an Untrusted Client

Anything in the binary is extractable (obfuscation only slows that down). Therefore:

- The app sends **only the signed-in user's identity token** (for example a Firebase ID token).
- Service, HMAC, "internal" and private-key secrets live on a server. If the app needs a privileged call, add a backend endpoint that verifies the user token and makes that call.
- Never read a secret through `String.fromEnvironment`, and never add one to the `--dart-define` key list: defines are compiled into the binary.
- Public client keys are fine (Firebase API key, a payment provider's publishable key).
- Keys that are **billed per request** or restricted by server IP (maps/routing/LLM keys) are not public even though their names contain no "SECRET". A name-based scanner is blind to them: list them explicitly.
- Never call an internal-only (secret-guarded) endpoint directly from the app, even "just for testing".

### Gate check (describe-and-implement in your CI; no script ships with this toolkit)

Run over app and shared `lib/` (skip generated files and tests):

| Check | Fails when |
|-------|-----------|
| Header/key literals | A quoted map key such as `'X-Internal-Secret':` or an identifier like `internalSecret` / `INTERNAL_API_SECRET` appears (match the quoted-key form so a comment naming the header is not a false hit) |
| Compile-time secrets | `String.fromEnvironment('…SECRET|HMAC|PRIVATE_KEY|INTERNAL…')`, or such a key in the dart-define generator's key list |
| Explicit names | Any per-request-billed key name you list in the config |
| Dormant exceptions | An allowlist file may exist, but it may only shrink |

Self-test every run: a known-bad sample **must** match, and a normal `Authorization: Bearer <jwt>` sample **must not**. A gate that returns zero hits proves nothing unless the positive control fires. Pair it with a reviewer pass — a grep cannot judge design ("is this call privileged?").

---

## 2. Debug and Test Affordances: Compile-Time Gate, Verified on the Artifact

A debug bypass (skip-auth, fake-user, test-only route) is release-safe only if its gate is a compile-time `const`, so release builds tree-shake the branches:

```dart
const bool _e2eRequested = bool.fromEnvironment('E2E_MODE');
// kDebugMode is const; !kReleaseMode alone is NOT enough (true in a --profile build).
const bool debugAffordancesEnabled = kDebugMode || (!kReleaseMode && _e2eRequested);
```

- Put the check in the **one function** every consumer routes through, as its first statement, before reading any attacker-controllable input (a URL query parameter, a deep-link payload).
- Verify against the **artifact**, not the source: build release and grep the output for the bypass's symbols/strings (`strings` on the binary, or the obfuscation symbol map).
- A green end-to-end run that uses an auth bypass proves nothing about the real sign-in/sign-out path; keep a separate real-auth check.

---

## 3. Server-Withheld vs Client-Hidden

For any permission-gated field ask: does the server **withhold** it, or send it and trust the client to hide it? Client-hidden is presentation, not authorization (any proxy can read the response).

- Permissions default to **false** (fail closed) and resolve from server-side relationships, never from caller-supplied input.
- Deep-link ids and push payload fields are attacker-controlled: ownership is checked in the service (404 missing, 403 unauthorized). Never `context.go(payload['path'])`; map payload values to routes through an allowlist.
- Rate-limit the unauthenticated half of an invite/activation flow; require a token on the mutating half.
- Firestore: the security rule is the enforcement, not the client query.

---

## 4. Log Hygiene When Dart Has No PII Gate

Backends often have a log-PII scanner; Dart usually does not, and the app logger typically forwards to Crashlytics in release.

- Log a static message; the exception travels in the sanctioned `error:` channel.
- Interpolating a count or an opaque id is fine. Interpolating anything a user typed or that locates a person is not.
- Never interpolate the exception itself: `FormatException.toString()` embeds a snippet of its source (possibly the user's text). For telemetry log `e.runtimeType`.

```dart
// package:logging 1.3.0 (error and stack trace are positional)
// wrong: user text can leak through the message
_log.warning('parse failed for note: $note, $e');
// right
_log.warning('note parse failed', e.runtimeType, st);
```

Add a redactor in the one log sink (the `Logger.root.onRecord` listener that forwards to the console or Crashlytics) as a second line of defence. Tested on Flutter 3.50.1 (`redact_test.dart`, with a positive control that the leak detector fires on the raw line; deleting the JWT rule fails the suite):

```dart
// lib/core/logging/redact.dart
final _patterns = <RegExp, String>{
  RegExp(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', caseSensitive: false):
      'Bearer [REDACTED]',
  // JWT: three base64url segments, the first starting with eyJ ({"...).
  RegExp(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*'): '[JWT]',
  RegExp(
    r'("?(?:access_token|refresh_token|id_token|password|client_secret)"?\s*[:=]\s*)"?[^",&\s}]+"?',
    caseSensitive: false,
  ): r'$1"[REDACTED]"',
  RegExp(r'[\w.+-]+@[\w-]+\.[\w.-]+'): '[EMAIL]',
  RegExp(r'\+?\d[\d\s().-]{8,}\d'): '[PHONE]',
};

String redact(String input) {
  var out = input;
  _patterns.forEach((pattern, replacement) {
    out = out.replaceAllMapped(pattern, (m) {
      // Re-insert capture group 1 when the replacement references it.
      return replacement.contains(r'$1')
          ? replacement.replaceFirst(r'$1', m.group(1) ?? '')
          : replacement;
    });
  });
  return out;
}
```

A redactor is a net, not the policy: it cannot recognise a name or an address, so the static-message rule above still applies.

---

## 5. Local Database Encryption: Check the Key, Not the Flag

"Encryption is enabled" says nothing; audit the key:

| Property | Requirement |
|----------|-------------|
| Generation | Cryptographically secure RNG (`Random.secure()`), 256-bit, per install |
| Storage | Keychain / Keystore only (iOS accessibility class `first_unlock_this_device` or stricter); never hardcoded, never derived from a device id, never in `SharedPreferences` |
| Lifecycle | Destroyed on sign-out so a second user on the same device cannot open the first user's data |
| Wipe | One coordinator (`signOutAndWipe()`) clears DB, key, caches and media; only a real sign-out may call it (see the token-refresh rules in the hardening file) |

---

## 6. A Security Preference That Cannot Be Read Fails Closed

For an app-lock or similar preference stored in secure storage:

- Read returns `null` → "never enabled" → **off**. Read **throws** → nobody knows → **on** (locked).
- Before flipping this, walk every recovery route (biometric, OS passcode fallback, sign-out escape hatch) with the same storage broken, so a locked user is never trapped.
- Consumer trap: `value ?? isLoading` returns the **previous** value during a rebuild when a keep-alive notifier retains the old value inside `AsyncLoading`. Write `isLoading || (value ?? true)` style logic deliberately, and treat `AsyncError` as a third state.
- Pin it at two tiers: a unit test on the resolved value, and a widget test over the **real** notifier with a throwing storage double asserting the lock screen appears and that ordinary unlock gets the user back in.

---

## 7. Untrusted Payloads on a "Read-Only" Status Bus

A feed the app only reads is still untrusted input if anyone else can write to it.

- Allowlist enum-like fields (channel, severity); never render payload text as a control.
- Navigate only through an allowlisted id→route map.
- Opening a hub must not mark everything read; a failed mark-all-read shows a visible error (capture the messenger/localizations **before** the `await`).
- See [firestore-status-bus.md](firestore-status-bus.md) for the data model.

---

## 8. Push Messages (firebase_messaging 17.1.0, flutter_local_notifications 23.0.4)

A push payload is attacker-influenced input that can arrive while the app is terminated. Compiled on Flutter 3.50.1; the allowlist and the top-level-handler check are unit-tested (`firebase_test.dart`), delivery on a device is NOT RUN (needs a real Firebase project and APNs/FCM credentials).

```dart
// lib/core/messaging/background_handler.dart
/// Runs in a separate isolate when a message arrives while the app is in the
/// background or terminated. Must be a top-level (or static) function, and the
/// pragma keeps it from being tree-shaken in release (AOT) builds.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // New isolate: nothing from main() exists here.
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  // Log the id only: data payloads can carry personal data.
  Logger('fcm.background').info('background message ${message.messageId}');
}

// main(), BEFORE runApp, so the handler is registered on a cold start:
// FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

/// Push payloads are attacker-controllable: map them through an allowlist.
const _routeAllowlist = {'order': '/orders', 'inbox': '/inbox'};

String? routeForMessage(RemoteMessage message) {
  final type = message.data['type'];
  final id = message.data['id'];
  final base = _routeAllowlist[type];
  if (base == null ||
      id is! String ||
      !RegExp(r'^[A-Za-z0-9_-]{1,64}$').hasMatch(id)) {
    return null;
  }
  return '$base/$id';
}
```

```dart
// After sign-in, at a moment where asking makes sense (not at launch):
final settings = await FirebaseMessaging.instance.requestPermission();
if (settings.authorizationStatus == AuthorizationStatus.denied) return; // show the denied state in settings
// Foreground messages are not displayed by FCM: show them locally.
FirebaseMessaging.onMessage.listen((m) {
  final n = m.notification;
  if (n != null) showForeground(id: m.hashCode, title: n.title, body: n.body);
});
// Taps from background (stream) and terminated (initial message) both go
// through routeForMessage; a null route opens nothing.
void open(RemoteMessage m) {
  final route = routeForMessage(m);
  if (route != null) navigate(route);
}

FirebaseMessaging.onMessageOpenedApp.listen(open);
final initial = await FirebaseMessaging.instance.getInitialMessage();
if (initial != null) open(initial);
```

flutter_local_notifications 23 takes named arguments: `initialize(settings: InitializationSettings(...), onDidReceiveNotificationResponse: ...)` and `show(id: ..., title: ..., body: ..., notificationDetails: ...)`. Set the Darwin `request*Permission` flags to `false` so the plugin does not prompt at launch.

Android build requirements (proved with `flutter build apk --debug` on 3.50.1: fails without them, passes with them): `compileSdk = 37` (flutter_local_notifications 23.0.4 and androidx.core 1.19 require it; the 3.50.1 template default is 36), and core library desugaring:

```kotlin
// android/app/build.gradle.kts
android {
    compileSdk = 37
    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}
```

Badges (`app_badge_plus` 1.4.0): set the count from server state (`if (await AppBadgePlus.isSupported()) await AppBadgePlus.updateBadge(unread);`), never by counting received pushes; clear it on sign-out.

Rules:
- The background handler is top-level with `@pragma('vm:entry-point')`, initialises Firebase itself, and does no UI work
- Never navigate to a path, URL or screen name taken from the payload; only allowlisted types plus a validated id
- Never put personal data or secrets in the notification payload: it is shown on the lock screen and stored by the OS
- Log message ids, not payloads
- A push registration is a device address, not a credential. Registration lifecycle (firebase.google.com/docs/cloud-messaging/flutter/client and /manage-tokens, read 2026-11-24):
  - Register with Firebase Installation IDs (`register()` + `onRegistered`); `getToken()` / `onTokenRefresh` are the deprecated registration-token API, and the two must not be mixed in one app
  - iOS: the APNs token must exist before any FCM API request (iOS SDK 10.4.0+) and is not guaranteed at launch. Await `getAPNSToken()` with a bounded retry (a few seconds), proceed only on non-null, otherwise report push as not registered; never block startup on it
  - Send the ID to the backend after sign-in with a timestamp, again on every `onRegistered` and on app resume (an idempotent upsert keyed by user and ID)
  - Sign-out coordinator: `unregister()` and delete the server row while the session can still authenticate, then clear auth state
- Server: delete a registration when a send returns `UNREGISTERED` (404), or `INVALID_ARGUMENT` (400) for a payload known to be valid
- Tap routing: the payload names the recipient user; a tap for a different user than the signed-in one (shared device, account switch) opens nothing
- **Channel retry (server):** never resend a push whose provider acceptance is unknown (`ACCEPTANCE_UNCERTAIN`). Re-derive the recipient before any retry. One pipeline per product event. Producer coverage: `python-dev/reference/notification-producer-and-channel.md`. `xcrun simctl push` never proves FCM/APNs transport (`flutter-e2e-maestro.md` §8).

---

## Security Review Checklist (client trust)

```
□ No service/HMAC/private-key secret reachable from Dart, fromEnvironment or the define list
□ Per-request-billed / IP-restricted keys named explicitly in the scanner
□ Secret scanner has a positive and a negative control
□ Debug/test affordances gated by a compile-time const, checked once, verified in a release build
□ Permission-gated data withheld server-side, not just hidden in UI
□ Push/deep-link payloads mapped through allowlists; background handler top-level with @pragma('vm:entry-point')
□ Log sink runs a redactor; no token values in logs
□ No user-typed text or exception.toString() interpolated into logs
□ DB key: secure RNG, keychain/keystore, destroyed on sign-out, single wipe coordinator
□ Unreadable security preference resolves fail-closed, with two-tier tests
```

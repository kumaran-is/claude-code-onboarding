# Flutter Security Hardening & Privacy Compliance

For general code security (OWASP Top 10, injection, auth, secrets) use the `security-reviewer` agent instead. This reference focuses on **Flutter-specific** security and **mobile privacy compliance**.

## Flutter Client-Side Security

### Secure Storage

- Use `flutter_secure_storage` for sensitive data — never `SharedPreferences` for secrets
- No hardcoded API keys, secrets, or credentials in Dart code
- A shipped app is an untrusted client: send only the user's identity token; service/HMAC/private-key secrets stay on a server behind a user-authenticated proxy (rules and gate check: [flutter-security-client-trust.md](flutter-security-client-trust.md))
- Obfuscate release builds (`--obfuscate --split-debug-info`) — obfuscation slows reverse engineering, it does not protect secrets

### Network Security

- Certificate pinning for API connections
- No HTTP traffic in production (enforce HTTPS)
- Privileged API calls go through a backend proxy that verifies the user token, not an embedded key

### Build Security

- Obfuscate release builds: `flutter build apk --obfuscate --split-debug-info=build/symbols`
- ProGuard/R8 enabled for Android
- Strip debug symbols in release

### Deep Link Security

- Validate deep link parameters before processing
- Don't expose sensitive routes via deep links
- Use App Links (Android) / Universal Links (iOS) over custom schemes

## Biometric Authentication

Use `local_auth` to gate sensitive screens (payment confirmation, viewing secrets) behind biometric verification. This is a **second factor** — it does NOT replace your Firebase Auth session.

### pubspec.yaml

```yaml
dependencies:
  local_auth: 3.0.2   # v3: LocalAuthException + LocalAuthExceptionCode; AuthenticationOptions/stickyAuth removed
```

### Pattern: gate a sensitive action on an explicit outcome

A boolean hides the difference between "cancelled", "locked out" and "no hardware". Return an outcome, and let only `verified` unlock the action. Compiled and tested on Flutter 3.50.1 (`biometric_test.dart`: success, lockout/cancel/error never map to verified, unsupported device is unavailable; a mutation mapping `userCanceled` to verified fails the suite).

```dart
// lib/core/security/biometric_service.dart
import 'package:local_auth/local_auth.dart';
import 'package:logging/logging.dart';

final _log = Logger('BiometricService');

/// Outcome of a local re-authentication. Only [verified] may unlock an action.
enum BiometricOutcome { verified, failed, unavailable, lockedOut, error }

class BiometricService {
  BiometricService([LocalAuthentication? auth])
    : _auth = auth ?? LocalAuthentication();

  final LocalAuthentication _auth;

  Future<BiometricOutcome> authenticate({required String reason}) async {
    try {
      if (!await _auth.isDeviceSupported()) {
        return BiometricOutcome.unavailable;
      }
      final ok = await _auth.authenticate(
        localizedReason: reason,
        persistAcrossBackgrounding: true, // retry after the app returns
      );
      return ok ? BiometricOutcome.verified : BiometricOutcome.failed;
    } on LocalAuthException catch (e) {
      _log.warning('local auth failed (${e.code.name})');
      return switch (e.code) {
        LocalAuthExceptionCode.userCanceled ||
        LocalAuthExceptionCode.systemCanceled ||
        LocalAuthExceptionCode.timeout => BiometricOutcome.failed,
        LocalAuthExceptionCode.temporaryLockout ||
        LocalAuthExceptionCode.biometricLockout => BiometricOutcome.lockedOut,
        LocalAuthExceptionCode.noBiometricHardware ||
        LocalAuthExceptionCode.noCredentialsSet => BiometricOutcome.unavailable,
        _ => BiometricOutcome.error,
      };
    }
  }
}
```

The caller decides per action what `unavailable` means (for example: fall back to re-entering the password, never "skip the check"), and shows a visible message for `failed`, `lockedOut` and `error`.

### Platform setup

- iOS `Info.plist`: `NSFaceIDUsageDescription` (Face ID devices reject the prompt without it).
- Android: `MainActivity` extends `FlutterFragmentActivity` (local_auth needs a `FragmentActivity`; flutter_stripe needs the same), and `<uses-permission android:name="android.permission.USE_BIOMETRIC" />`.

### Rules

- **Only `verified` unlocks** — cancelled, locked out, unavailable and error are distinct, visible states
- **Never block the entire app** behind biometrics — only gate specific sensitive actions
- **`biometricOnly: false`** (the default in `local_auth` 3.x) — allow the device PIN/passcode so users with damaged sensors are not locked out
- **Biometrics are a local second factor** — they never replace the server session or a server-side authorization check
- **Do not store biometric templates yourself** — `local_auth` delegates to the OS; the app never sees biometric data

---

## Token Refresh & Expiry Handling

Access tokens expire. Refresh them transparently using a Dio interceptor so the user is never interrupted mid-session.

### Pattern: single-flight refresh interceptor (dio 5.11.1)

A plain `Interceptor` plus one shared refresh `Future`: concurrent 401s wait for the same refresh, and each failed request is replayed once on a separate client that has no auth interceptor (no recursion, no deadlock). `QueuedInterceptor` (dio README) also avoids duplicate refreshes, by running its handlers one task at a time; this pattern keeps requests concurrent and pins the single-flight behaviour with a test instead.

Compiled and tested on Flutter 3.50.1 / Dart 3.14.0 with a fake `HttpClientAdapter` (`network_test.dart`). Negative controls, each a planted defect that makes the suite fail: removing the shared future (concurrent 401s trigger two refreshes), wiping on a connection drop, and logging the token value.

```dart
// lib/core/network/auth_interceptor.dart
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:logging/logging.dart';

import '../security/token_store.dart';

final _log = Logger('AuthInterceptor');

/// Calls the refresh endpoint and returns the new token pair. Must use a Dio
/// instance WITHOUT this interceptor (no recursion) and with its own timeouts.
typedef RefreshTokens = Future<TokenPair> Function(String refreshToken);

/// Adds the bearer token, and on a 401 refreshes once for all concurrent
/// callers (single flight), then replays each failed request once.
class AuthInterceptor extends Interceptor {
  // Dart 3.12+ private named parameters: callers still write `tokens:` etc.
  AuthInterceptor({
    required this._tokens,
    required this._retryClient,
    required this._refresh,
    required this._onSessionExpired,
  });

  final TokenStore _tokens;
  final Dio _retryClient;
  final RefreshTokens _refresh;
  final Future<void> Function() _onSessionExpired;

  static const _retriedFlag = 'auth_retried';
  Future<String>? _inFlightRefresh;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    try {
      final token = await _tokens.readAccessToken();
      if (token != null) options.headers['Authorization'] = 'Bearer $token';
      handler.next(options);
    } on SecureStorageFailure catch (e) {
      // Keystore broken: fail the request, never send it unauthenticated.
      handler.reject(DioException(requestOptions: options, error: e));
    }
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final request = err.requestOptions;
    final sentAuth = request.headers['Authorization'] != null;
    if (err.response?.statusCode != 401 ||
        !sentAuth || // 401 before any credentials existed: not a dead session
        request.extra[_retriedFlag] == true) {
      handler.next(err);
      return;
    }
    try {
      // A request that left with an older token than the stored one raced a
      // refresh that already finished: replay it, do not refresh again.
      final current = await _tokens.readAccessToken();
      final sentToken = request.headers['Authorization'];
      final token = (current != null && sentToken != 'Bearer $current')
          ? current
          : await (_inFlightRefresh ??= _refreshOnce());
      request
        ..headers['Authorization'] = 'Bearer $token'
        ..extra[_retriedFlag] = true;
      handler.resolve(await _retryClient.fetch<dynamic>(request));
    } on DioException catch (e) {
      handler.next(e);
    } on SecureStorageFailure catch (e) {
      handler.next(DioException(requestOptions: request, error: e));
    }
  }

  Future<String> _refreshOnce() async {
    try {
      final refreshToken = await _tokens.readRefreshToken();
      if (refreshToken == null) {
        await _onSessionExpired();
        throw DioException(
          requestOptions: RequestOptions(path: 'auth/refresh'),
          type: DioExceptionType.badResponse,
          response: Response(
            requestOptions: RequestOptions(path: 'auth/refresh'),
            statusCode: 401,
          ),
        );
      }
      final pair = await _refresh(refreshToken);
      await _tokens.save(pair);
      _log.info('token refreshed'); // never the token value
      return pair.accessToken;
    } on DioException catch (e) {
      // Only a definitive rejection of the refresh token ends the session.
      // Timeouts, connection errors and 5xx keep credentials.
      final status = e.response?.statusCode;
      if (status == 400 || status == 401 || status == 403) {
        _log.warning('refresh rejected ($status); signing out');
        await _onSessionExpired();
      } else {
        _log.warning('refresh failed transiently (${e.type.name})');
      }
      rethrow;
    } finally {
      _inFlightRefresh = null;
    }
  }
}
```

`TokenStore` wraps `flutter_secure_storage` 11.2.0 and turns a `PlatformException` into a typed `SecureStorageFailure` ("unknown", never "signed out"):

```dart
// lib/core/security/token_store.dart (excerpt)
class TokenStore {
  TokenStore([FlutterSecureStorage? storage])
    : _storage =
          storage ??
          const FlutterSecureStorage(
            iOptions: IOSOptions(
              accessibility: KeychainAccessibility.first_unlock_this_device,
            ),
          );

  final FlutterSecureStorage _storage;

  Future<String?> readAccessToken() =>
      _guard('read', () => _storage.read(key: 'access_token'));

  Future<T> _guard<T>(String operation, Future<T> Function() body) async {
    try {
      return await body();
    } on PlatformException catch (e, st) {
      // Log the code only: the message can contain key names or values.
      _log.severe(
        'secure storage $operation failed (${e.code})',
        e.runtimeType,
        st,
      );
      throw SecureStorageFailure(operation);
    }
  }
  // readRefreshToken, save(TokenPair) and clear() follow the same _guard pattern.
}
```

Wire both clients in one factory (full version with timeouts and the HTTPS assert: [flutter-api-contract-parity.md](flutter-api-contract-parity.md) §3–4):

```dart
final plain = Dio(_options(baseUrl)); // refresh call + replay: no auth interceptor
final api = Dio(_options(baseUrl))
  ..interceptors.add(
    AuthInterceptor(
      tokens: tokens,
      retryClient: plain,
      onSessionExpired: onSessionExpired, // the ONE sign-out coordinator
      refresh: (refreshToken) async {
        final res = await plain.post<Map<String, dynamic>>(
          '/auth/refresh',
          data: {'refresh_token': refreshToken},
        );
        final body = res.data!;
        return TokenPair(
          accessToken: body['access_token'] as String,
          refreshToken: body['refresh_token'] as String,
        );
      },
    ),
  );
```

Firebase Auth apps do not need this interceptor for Firebase services: send `await user.getIdToken()` to your backend instead (the SDK refreshes it) and treat a `null` user as signed out with no anonymous fallback.

### Rules

- **Single flight** — one shared refresh `Future` for all concurrent 401s; each request is replayed at most once (`extra` flag), so a still-401 replay cannot loop
- **Separate replay/refresh client** — the refresh call and the replay go through a `Dio` without the auth interceptor
- **Store tokens in `flutter_secure_storage` only** — never in `SharedPreferences` or in-memory globals; a keystore read failure fails the request instead of sending it unauthenticated
- **Wipe only on credential rejection, never on a transient failure** — only a 400/401/403 from the refresh endpoint (or a user sign-out) reaches the sign-out coordinator. A connection error, timeout or 5xx during refresh keeps credentials and reports the failure; wiping there deletes queued work for a user who merely lost signal
- **Classify by error type/status, never message text** — a substring match on "network" can skip a needed sign-out
- **One sign-out coordinator** — all wipes (tokens, local DB, keys, caches, purchase identity) go through one function; only a real sign-out reaches it
- **A 401 on a request made before any credentials existed is not a dead session** — pass it through; do not wipe
- **Cache last verified claims/roles per user** for transient-error reuse; clear them on sign-out and on a null auth-state emission. No TTL on the cache (a TTL would sign the user out while offline)
- **Never log token values** — log `'token refreshed'`, never the token; run log lines through a redactor ([flutter-security-client-trust.md](flutter-security-client-trust.md) §4)

---

## Firebase App Check

App Check verifies that requests to your Firebase backend come from a legitimate build of your app — not an emulator, a forged client, or a script. It protects **all** Firebase services (Auth, Storage, Cloud Functions, Realtime Database) regardless of which database you use.

### Setup in `main.dart`

```dart
import 'package:firebase_app_check/firebase_app_check.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);

  // Activate App Check before any other Firebase service
  await FirebaseAppCheck.instance.activate(
    // Android: Play Integrity in production; iOS: App Attest with DeviceCheck fallback.
    // Debug providers ONLY in debug builds. The `providerAndroid` / `providerApple` provider
    // objects replace the older `androidProvider` / `appleProvider` enum parameters.
    providerAndroid: kDebugMode
        ? const AndroidDebugProvider()
        : const AndroidPlayIntegrityProvider(),
    providerApple: kDebugMode
        ? const AppleDebugProvider()
        : const AppleAppAttestWithDeviceCheckFallbackProvider(),
  );

  runApp(const ProviderScope(child: App()));
}
```

### `pubspec.yaml`
```yaml
dependencies:
  firebase_core: 5.2.0
  firebase_app_check: 0.5.2   # FlutterFire family below resolves together on Flutter 3.50.1
```

The FlutterFire family pinned together and resolved on Flutter 3.50.1 / Dart 3.14.0: `firebase_core 5.2.0`, `firebase_auth 7.1.0`, `cloud_firestore 7.2.0`, `firebase_messaging 17.1.0`, `firebase_crashlytics 6.1.0`, `firebase_app_check 0.5.2` (Firebase native SDK 35.2.0). Floors from the plugin sources: Flutter >= 3.44, Dart ^3.12, Android `minSdk 24`, iOS 15.0. Upgrade the family as one unit; mixing majors fails resolution through the shared platform interfaces.

### Rules

- Activate App Check **before** calling any other Firebase service — wrong order causes silent failures
- `kDebugMode` guard is mandatory — debug provider bypasses attestation for local development; shipping it to production defeats the purpose
- Add `FirebaseAppCheck` to the pre-release security checklist
- No code changes needed in repositories or services — App Check operates at the Firebase SDK network layer

### Pre-Release Checklist Addition

Add to the checklist in this file:
- [ ] Firebase App Check activated with platform-specific production providers (App Attest/DeviceCheck / Play Integrity)
- [ ] Debug provider guard (`kDebugMode`) confirmed — debug provider NOT active in release builds

## Privacy Compliance

### GDPR Requirements

- **Lawful Basis** — document the legal basis for each data type
- **Data Minimization** — collect only what's necessary
- **Consent Management** — granular consent with easy withdrawal
- **Data Subject Rights** — implement export, deletion, rectification, portability
- **Data Retention** — automated cleanup policies; never store data longer than needed

### CCPA Requirements

- **Consumer Rights** — right to know, delete, and opt out of data sales
- **Do Not Sell** — respect opt-out preferences
- **Privacy Preferences** — per-user opt-out tracking with audit history

## Pre-Release Security Checklist

- [ ] Zero hardcoded secrets in codebase
- [ ] `flutter_secure_storage` used for all sensitive data
- [ ] Release builds obfuscated
- [ ] Certificate pinning configured
- [ ] GDPR consent flow implemented
- [ ] Data export/deletion endpoints functional
- [ ] Privacy policy URL accessible from app
- [ ] Dependencies checked for known vulnerabilities (pub surfaces advisories on `dart pub get`; add the CI scanner your org uses)
- [ ] No service secrets in the client; secret-scan gate passes ([flutter-security-client-trust.md](flutter-security-client-trust.md))
- [ ] Biometric auth gates all sensitive actions (payment, secrets view)
- [ ] Token refresh interceptor is single-flight (one refresh for concurrent 401s, one replay per request)
- [ ] Only a definitive refresh-token rejection clears storage and redirects to login; connection errors/timeouts do not

## Crashlytics Structured Error Reporting

Every catch block in a repository or service MUST record to Crashlytics — not just log locally. Structured reporting makes incidents searchable and debuggable in the Firebase console.

### Pattern

Use this alongside the `Result<T>` repository pattern from `flutter-architecture-patterns.md`. The two are complementary: `Result<T>` ensures callers handle failures; Crashlytics ensures failures are observable in production.

```dart
import 'package:firebase_crashlytics/firebase_crashlytics.dart';

// ✅ REQUIRED — repository method returning Result<T> with structured Crashlytics reporting
Future<Result<Order>> fetchById(String id) async {
  try {
    final doc = await _firestore.collection('orders').doc(id).get();
    return Success(Order.fromFirestore(doc));
  } on FirebaseException catch (e, stack) {
    // 1. Human-readable breadcrumb (searchable in Crashlytics console)
    await FirebaseCrashlytics.instance.log(
      '[OrderRepository.fetchById] FirebaseException for order $id: ${e.code}',
    );
    // 2. Full error + stack trace — always await, dropping it loses the report
    await FirebaseCrashlytics.instance.recordError(
      e,
      stack,
      reason: 'OrderRepository.fetchById — id: $id',
      printDetails: false, // prevents stack trace leaking to logcat in release builds
    );
    return Failure(e);
  } catch (e, stack) {
    await FirebaseCrashlytics.instance.log(
      // runtimeType, never $e: an exception message can carry user text
      '[OrderRepository.fetchById] Unexpected ${e.runtimeType} for order $id',
    );
    await FirebaseCrashlytics.instance.recordError(
      e,
      stack,
      reason: 'OrderRepository.fetchById unexpected — id: $id',
      printDetails: false,
    );
    return Failure(UnexpectedException(e.runtimeType.toString()));
  }
}
```

For high-cardinality context that doesn't fit in the `reason` string:

```dart
FirebaseCrashlytics.instance.setCustomKey('user_type', userType);
FirebaseCrashlytics.instance.setCustomKey('order_status', order.status.name);
```

### Rules

- **`log()` before `recordError()`** — the log line becomes a breadcrumb shown above the crash in the Firebase console
- **Include `[ClassName.methodName]` in every log** — makes Crashlytics logs `grep`-able by call site
- **Include the entity ID when safe** — `order $id` is fine; never include PII (email, phone, name)
- **Always `await recordError()`** — it is async; dropping the await silently loses crash reports
- **`printDetails: false`** — prevents internal stack traces appearing in logcat/console in release builds
- **Return `Failure(e)`, do not rethrow** — use `Result<T>` so callers are forced to handle the failure case (see `flutter-architecture-patterns.md`)
- **`setCustomKey()` for structured context** — prefer this over embedding state in the `reason` string

### Pre-Release Checklist Addition

- [ ] Every repository catch block calls `FirebaseCrashlytics.instance.log()` + `await recordError()` and returns `Failure(e)`
- [ ] No PII in Crashlytics log strings or custom keys
- [ ] `printDetails: false` on all `recordError()` calls

## Incident Response (Mobile-Specific)

1. **Contain** — force app update or feature flag to disable compromised flow
2. **Investigate** — collect crash logs, analyze scope of data exposure
3. **Notify** — user notification + regulatory notification within required timeframes (72h GDPR)
4. **Remediate** — push hotfix, revoke compromised tokens, rotate keys
5. **Review** — post-incident report, update security policies

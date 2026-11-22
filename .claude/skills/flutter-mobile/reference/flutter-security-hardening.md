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
  local_auth: 3.0.2   # verified on pub.dev; v3 removed AuthenticationOptions/stickyAuth
```

### Pattern — gate a sensitive action

```dart
// lib/core/security/biometric_service.dart
import 'package:local_auth/local_auth.dart';

class BiometricService {
  final LocalAuthentication _auth = LocalAuthentication();

  /// Returns true if device supports and has enrolled biometrics.
  Future<bool> isAvailable() async {
    final canCheck = await _auth.canCheckBiometrics;
    final isDeviceSupported = await _auth.isDeviceSupported();
    return canCheck && isDeviceSupported;
  }

  /// Prompts the user. Returns true on success, false if the user failed/cancelled.
  /// Unexpected platform errors are logged and surface as `false` so the caller
  /// shows a visible "could not verify" state — never treat `false` as success.
  Future<bool> authenticate({required String reason}) async {
    try {
      return await _auth.authenticate(
        localizedReason: reason,
        biometricOnly: false,              // allow device PIN/passcode fallback
        persistAcrossBackgrounding: true,  // retry if the system cancels on backgrounding
      );
    } on LocalAuthException catch (e, stack) {
      // e.code is a LocalAuthExceptionCode (noBiometricHardware, temporaryLockout,
      // biometricLockout, userCanceled, ...) — branch on it for user-facing copy.
      FirebaseCrashlytics.instance.log('[BiometricService] auth failed: ${e.code}');
      await FirebaseCrashlytics.instance.recordError(e, stack,
          reason: 'BiometricService.authenticate', printDetails: false);
      return false;
    }
  }
}
```

```dart
// Riverpod provider
@Riverpod(keepAlive: true)
BiometricService biometricService(Ref ref) => BiometricService();
```

```dart
// Usage — gate a payment confirmation action
Future<void> confirmPayment() async {
  final bio = ref.read(biometricServiceProvider);
  final available = await bio.isAvailable();

  if (available) {
    final passed = await bio.authenticate(
      reason: 'Confirm your identity to complete the payment',
    );
    if (!passed) return;   // user cancelled or failed — do nothing silently
  }

  // Proceed only if biometrics passed (or not available on this device)
  await ref.read(paymentProvider.notifier).submit();
}
```

### iOS — `Info.plist`

```xml
<key>NSFaceIDUsageDescription</key>
<string>Confirm your identity to authorize sensitive actions</string>
```

### Android — `AndroidManifest.xml`

```xml
<uses-permission android:name="android.permission.USE_BIOMETRIC" />
```

### Rules

- **Always check `isAvailable()` first** — degrade gracefully on devices without biometrics
- **Never block the entire app** behind biometrics — only gate specific sensitive actions
- **`biometricOnly: false`** (the default in `local_auth` 3.x) — allow PIN/pattern fallback so users with damaged fingerprint sensors are not locked out
- **Do not store biometric templates yourself** — `local_auth` delegates to the OS secure enclave; your app never sees raw biometric data

---

## Token Refresh & Expiry Handling

Access tokens expire. Refresh them transparently using a Dio interceptor so the user is never interrupted mid-session.

### Pattern — Dio interceptor with queued retry

```dart
// lib/core/network/interceptors/auth_interceptor.dart
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthInterceptor extends QueuedInterceptor {
  AuthInterceptor({required this.secureStorage, required this.dio});

  final FlutterSecureStorage secureStorage;
  final Dio dio;   // the SAME Dio instance — used to replay failed requests

  static const _accessTokenKey  = 'access_token';
  static const _refreshTokenKey = 'refresh_token';

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await secureStorage.read(key: _accessTokenKey);
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode != 401) {
      handler.next(err);
      return;
    }

    // 401 — attempt token refresh
    try {
      final newToken = await _refresh();
      // Replay original request with new token
      final retryOptions = err.requestOptions
        ..headers['Authorization'] = 'Bearer $newToken';
      final response = await dio.fetch(retryOptions);
      handler.resolve(response);
    } on DioException catch (refreshError) {
      // Only a definitive server rejection of the refresh token ends the session.
      // Connection errors, timeouts and 5xx are TRANSIENT: keep credentials and
      // surface the failure (the user is offline, not signed out).
      if (_isCredentialRejection(refreshError)) {
        await secureStorage.deleteAll(); // in production route through ONE sign-out coordinator
      }
      handler.reject(err);
    }
  }

  /// Refresh endpoint answered 400/401/403 = refresh token invalid or revoked.
  /// Classify by response status/error code, never by message text.
  bool _isCredentialRejection(DioException e) {
    final status = e.response?.statusCode;
    return status == 400 || status == 401 || status == 403;
  }

  Future<String> _refresh() async {
    final refreshToken = await secureStorage.read(key: _refreshTokenKey);
    if (refreshToken == null) {
      // No credentials at all: a request made before sign-in is not a dead session.
      throw DioException(
        requestOptions: RequestOptions(),
        response: Response(requestOptions: RequestOptions(), statusCode: 401),
      );
    }

    final response = await Dio().post(
      '${Env.apiBaseUrl}/auth/refresh',
      data: {'refresh_token': refreshToken},
    );

    final newAccessToken  = response.data['access_token']  as String;
    final newRefreshToken = response.data['refresh_token'] as String;

    await secureStorage.write(key: _accessTokenKey,  value: newAccessToken);
    await secureStorage.write(key: _refreshTokenKey, value: newRefreshToken);
    return newAccessToken;
  }
}
```

Register on the Dio instance in `core/di/providers.dart`:
```dart
@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  final dio = Dio(BaseOptions(baseUrl: Env.apiBaseUrl));
  final storage = ref.watch(secureStorageProvider);
  dio.interceptors.add(AuthInterceptor(secureStorage: storage, dio: dio));
  return dio;
}
```

### Token storage keys

```dart
// lib/core/constants/storage_keys.dart
abstract final class StorageKeys {
  static const accessToken  = 'access_token';
  static const refreshToken = 'refresh_token';
  static const userId       = 'user_id';
}
```

### Rules

- **`QueuedInterceptor`** — queues concurrent 401 requests; prevents multiple simultaneous refresh calls
- **Store tokens in `flutter_secure_storage` only** — never in `SharedPreferences` or in-memory globals
- **Wipe only on credential rejection, never on a transient failure** — `deleteAll()` + redirect to login only when the refresh endpoint definitively rejects the refresh token (or the user signs out). A connection error or timeout during refresh keeps credentials and reports offline; wiping there deletes queued work for a user who merely lost signal
- **Classify by error type/status, never message text** — a substring match on "network" can skip a needed sign-out
- **One sign-out coordinator** — all wipes (tokens, local DB, keys, caches) go through one function; only a real sign-out reaches it
- **A 401 on a request made before any credentials existed is not a dead session** — pass it through; do not wipe
- **Cache last verified claims/roles per user** for transient-error reuse; clear them on sign-out and on a null auth-state emission. No TTL on the cache (a TTL would sign the user out while offline)
- **Refresh endpoint uses a fresh `Dio()` instance** — avoids circular interception of the refresh call itself
- **Never log token values** — log `'token refreshed'` not the token content

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
    // Android: Play Integrity in production; iOS: App Attest (with DeviceCheck fallback) or DeviceCheck.
    // Debug providers ONLY in debug builds. The `providerAndroid` / `providerApple` provider
    // objects replace the older `androidProvider` / `appleProvider` enum parameters.
    providerAndroid: kDebugMode
        ? AndroidDebugProvider()
        : AndroidPlayIntegrityProvider(),
    providerApple: kDebugMode
        ? AppleDebugProvider()
        : AppleAppAttestWithDeviceCheckFallbackProvider(),
  );

  runApp(const ProviderScope(child: App()));
}
```

### `pubspec.yaml`
```yaml
dependencies:
  firebase_app_check: 0.5.2   # verified on pub.dev; re-check before pinning
```

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
- [ ] Token refresh interceptor handles 401 transparently with QueuedInterceptor
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
    FirebaseCrashlytics.instance.log(
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
    FirebaseCrashlytics.instance.log(
      '[OrderRepository.fetchById] Unexpected error for order $id: $e',
    );
    await FirebaseCrashlytics.instance.recordError(
      e,
      stack,
      reason: 'OrderRepository.fetchById unexpected — id: $id',
      printDetails: false,
    );
    return Failure(UnexpectedException(e.toString()));
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

---
name: flutter-security-expert
description: Flutter mobile security and privacy compliance specialist. Use for secure storage reviews, certificate pinning, GDPR/CCPA compliance, code obfuscation, and mobile-specific security hardening. For general OWASP issues use security-reviewer instead.
allowed-tools: Bash, Read, Glob, Grep
agent: flutter-security-expert
context: fork
metadata:
  triggers: flutter security, secure storage, certificate pinning, GDPR, CCPA, mobile security, flutter hardening, keystore, flutter privacy, flutter release security
  related-skills: flutter-mobile, security-reviewer
  domain: security
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-11-23"
---

## Iron Law

Load `flutter-mobile/reference/flutter-security-hardening.md` (and `flutter-security-client-trust.md` for secrets/debug-gate/fail-closed checks) before auditing — never assess mobile security from memory.

# Flutter Security Expert

Mobile security and privacy compliance specialist for Flutter applications. Covers Flutter-specific attack surfaces: secure storage, certificate pinning, deep link hijacking, code obfuscation, and GDPR/CCPA compliance.

**Scope boundary:**
- This skill: Flutter-specific security and mobile privacy compliance
- `security-reviewer`: General OWASP Top 10, injection, auth, secrets in any language

## When to Use

- Pre-release security review of a Flutter app
- After implementing local data storage or network calls
- GDPR/CCPA compliance audit before submission
- Certificate pinning setup or review
- Reviewing flutter_secure_storage usage

## Audit Areas

| Area | What to Check |
|------|--------------|
| **Secure Storage** | `flutter_secure_storage` for tokens/keys; no plaintext SharedPreferences for sensitive data |
| **Certificate Pinning** | `dio` or `http` with pinned certificates; backup pins configured |
| **GDPR/CCPA** | Data retention limits, consent collection, right-to-delete implementation |
| **Code Obfuscation** | `--obfuscate --split-debug-info` in release builds |
| **Deep Link Security** | Intent filter validation, URL scheme hijacking prevention |
| **Build Security** | No debug flags in release; ProGuard/R8 enabled for Android; debug affordances behind compile-time `const` gates |
| **Client Trust** | No service/HMAC/private-key secrets reachable from Dart or `--dart-define`; privileged calls go through a user-authenticated backend; per-request-billed keys named |
| **Token / Session Lifecycle** | Single-flight refresh (one refresh for concurrent 401s, one replay per request, separate client without the auth interceptor); credentials wiped only on a 400/401/403 from the refresh endpoint, never on connection errors/timeouts/5xx; keystore read failure fails the request; one sign-out coordinator (tokens, DB key, FCM token, purchase identity) |
| **Firebase** | App Check activated before other Firebase calls with debug providers behind `kDebugMode`; Firestore rules tested on the emulator with a `demo-*` project and a permissive-rule negative; no real Firebase config in fixtures |
| **Push Messages** | Background handler top-level with `@pragma('vm:entry-point')`; payload routes through an allowlist plus id validation; no personal data in notification payloads; payloads not logged |
| **Biometrics** | `local_auth` 3.x result mapped to an explicit outcome; only "verified" unlocks; cancel/lockout/error visible; never the only authorization |
| **Payments** | Only publishable/public SDK keys in the app (`pk_`, RevenueCat `appl_`/`goog_`); fulfilment and entitlements decided server-side (webhook, RevenueCat REST) |
| **Security Preferences** | App-lock/permission settings fail closed when unreadable |
| **Log Hygiene** | No user text, token or `exception.toString()` interpolated into logs/Crashlytics messages; the log sink runs a redactor |

## Process

1. Scope — identify target files from request or glob `lib/**/*.dart`
2. Load `flutter-mobile/reference/flutter-security-hardening.md` and `flutter-security-client-trust.md` for checklists
3. Audit each area in the table above
4. Report findings by severity with file:line and remediation

## Verdict

```
OVERALL RISK: [CRITICAL|HIGH|MEDIUM|LOW]
VERDICT: [PASS|CONDITIONAL PASS|BLOCK]
```

- **BLOCK**: any CRITICAL finding (hardcoded or client-held service secret, TLS validation disabled (`badCertificateCallback` returning `true`), insecure token storage, credential wipe on transient network error)
- **CONDITIONAL PASS**: HIGH findings with written remediation plan. Missing certificate pinning is HIGH when the threat model requires it (MASVS-NETWORK-2: payments, health, regulated data) and MEDIUM otherwise; pinning without a backup pin and a rotation plan is itself HIGH (an expired certificate locks every user out)
- **PASS**: zero CRITICAL, zero HIGH

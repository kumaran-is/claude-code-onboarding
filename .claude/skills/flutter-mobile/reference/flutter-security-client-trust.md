# Flutter Security — Client Trust, Debug Gates, Fail-Closed Settings

Read this when deciding what may live in the app binary (keys, secrets, privileged calls), adding a debug/test affordance, encrypting a local database, implementing an app-lock or other security preference, or auditing logs for sensitive data. Companion to [flutter-security-hardening.md](flutter-security-hardening.md) (storage, pinning, biometrics, token refresh, privacy) — this file does not repeat those.

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
// wrong: user text can leak through the message
logger.warning('parse failed for note: $note, $e');
// right
logger.warning('note parse failed', error: e, stackTrace: st);
```

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

## Security Review Checklist (client trust)

```
□ No service/HMAC/private-key secret reachable from Dart, fromEnvironment or the define list
□ Per-request-billed / IP-restricted keys named explicitly in the scanner
□ Secret scanner has a positive and a negative control
□ Debug/test affordances gated by a compile-time const, checked once, verified in a release build
□ Permission-gated data withheld server-side, not just hidden in UI
□ Push/deep-link payloads mapped through allowlists
□ No user-typed text or exception.toString() interpolated into logs
□ DB key: secure RNG, keychain/keystore, destroyed on sign-out, single wipe coordinator
□ Unreadable security preference resolves fail-closed, with two-tier tests
```

# Flutter API Contract Parity, Client Construction and Request Bounds

Read this when adding or changing an API client, a DTO/response model, a base-URL or environment config, request timeouts, or code that interprets request failures. It covers keeping the app and the backend in agreement (routes, field types, wire keys), building HTTP clients so every request has a bounded lifetime, and mapping failures without losing their meaning. Retry/circuit-breaker patterns live in [flutter-network-resilience.md](flutter-network-resilience.md); error-surfacing rules in [global-error-handling.md](global-error-handling.md); secrets and token refresh in [flutter-security-hardening.md](flutter-security-hardening.md). Examples use Dio; the rules are client-agnostic.

## Contents

1. [Contract parity with the backend](#1-contract-parity-with-the-backend)
2. [Wire-format and DTO rules](#2-wire-format-and-dto-rules)
3. [One source of truth for base URLs](#3-one-source-of-truth-for-base-urls)
4. [Bounded request lifetime](#4-bounded-request-lifetime)
5. [Failure mapping](#5-failure-mapping)
6. [Review checklist](#6-review-checklist)

---

## 1. Contract parity with the backend

Unit tests with a fake HTTP adapter assert a client's path against a canned response. They can never notice that the route does not exist, lives under a different prefix, or on another service. Add a mechanical check that compares the two sides.

If the backend publishes an OpenAPI document (or any machine-readable route list):

- Add a CI/pre-PR check that every client's `(HTTP method, full path)` exists in the backend's snapshot. Write path strings as single literals (`'/orders/$id/status'`) so a script can resolve them; avoid building paths from fragments.
- Regenerate the committed snapshot **in the same PR** as any backend route change. A generator that rewrites every service's snapshot will touch services you did not change — revert those so the diff stays reviewable.
- A new response field is not "shipped" until the **owning service is rebuilt/deployed and the live response is probed for the field by name**. All-green unit tests, a correct schema and a correct client model still produce a missing field if one of the touched services was not rebuilt.
- A missing field's client default must fail toward the **status quo**, never a new restriction. A `@Default(false)` on a "can do X" flag silently removes a feature for everyone when the server omits the key. Test the key absent and both values.
- Never call a service that does not own the route; fix the server or the base URL, not the path.

If there is no machine-readable contract, write a thin contract test against a staging/local backend for each client, and treat that as the minimum.

## 2. Wire-format and DTO rules

- Read each field's type from the schema before typing it in Dart — never infer a wire format from a sibling DTO. Typical traps: decimals/money serialised as JSON **strings**; ids that are not UUIDs; integers that arrive as doubles; timestamps with and without offsets. Parse leniently at the boundary (and guard `isFinite`), then expose strong types.
- A schema field that is not `required` must not be Dart `required`; nullable on the wire ⇒ nullable in the model.
- If a path or body parameter is identified on the client by an identity provider's uid, do not type it as a UUID on the server — validate the shape that is actually issued.
- Pin wire **keys** with a test that deserialises a real payload: happy path, explicit `null`, and **absent key**.
- Keep JSON models (DTOs) separate from domain entities; map once at the repository boundary (see [flutter-architecture-patterns.md](flutter-architecture-patterns.md), DTO → domain mapper).
- Test fixtures for a list surface use the field set the **list endpoint** really returns (omitted fields are `null`), whenever logic branches on fallbacks; a rule written against a full detail payload can pass every widget test and fail on every live row.
- URLs a server **signed** (pre-signed upload/download) are used verbatim: never rewrite host, path or query, and never branch on platform to "fix" reachability on the client — the signature binds the host. Fix reachability where the URL is minted. (Details: [flutter-platform-gotchas.md](flutter-platform-gotchas.md).)

## 3. One source of truth for base URLs

- One config class owns every backend base URL: one getter per service, holding that service's full root including any path prefix; client code uses bare paths (`/orders`). Do not add a generic `API_BASE_URL`, and do not put a prefix in a path string.
- Build each client through one factory per service so every request gets the same interceptors, timeouts and base URL. A bare `Dio()` has none of them.
- Environment values come from `--dart-define` / `--dart-define-from-file`; deployed builds take explicit HTTPS URLs. In release mode throw at startup if a base URL is not HTTPS, in the provider that builds each credential-carrying client, so a mis-set URL fails fast instead of sending a bearer token in cleartext:

```dart
void assertHttpsInRelease(String baseUrl) {
  if (kReleaseMode && !baseUrl.startsWith('https://')) {
    throw StateError('Release builds require an https base URL');
  }
}
```

- Local development hosts differ by run target (simulator/web `localhost`, Android emulator `10.0.2.2`, a physical device needs the dev machine's LAN address). Resolve them in the same config class from a dev-only define; keep the machine-specific value in a git-ignored file; test both branches (`flutter test` and `flutter test --dart-define=…`) with a control that proves the branch actually differed, because a compile-time define makes an adaptive test pass vacuously. A LAN address in an env file goes stale when the machine's IP changes — compare it before an E2E run.
- Values both the app and a backend must agree on (cache TTLs, size caps, staleness windows, page sizes) are **config both sides read**, not a Dart literal with a comment naming the server constant ("a comment naming another file's constant is a dependency without a link"). First check whether the value is already on the wire. Otherwise: same key name **and unit** on both sides, `int.fromEnvironment`, guard `<= 0`, and pin the default against the example env file in a test. Design tokens and protocol constants (enum wire values, route paths) stay in code.

## 4. Bounded request lifetime

A request with no timeout is a request that can hang a screen forever. Decide the policy per client class and construct each through its own factory.

| Class | Typical bounds (tune per product; values are examples) |
|---|---|
| REST calls | connect ≈ 10 s, receive ≈ 30 s |
| Signed-URL transfers (upload/download) | same connect/receive; **send** timeout sized per payload (`bytes ÷ minimum throughput`, clamped to the signed URL's lifetime) |
| Identity-token fetch inside an interceptor | explicit timeout around the SDK call; do not assume the platform SDK bounds it |
| Streaming answers (SSE) | first-response timeout + idle-gap timeout enforced in Dart, plus a `CancelToken` on timeout **and** on subscriber cancel |

Facts to design around:

- Dio's `receiveTimeout` is the time to the first response bytes and then the gap between received chunks — not a total-duration cap (Dio docs). `null`/`Duration.zero` means no limit. So it does not bound a slow-but-steady download; enforce overall bounds yourself where needed.
- Web XHR-based adapters may behave differently from the IO adapter for long-lived responses (for example total-time caps). Hedged: test streaming on web with your pinned Dio version before relying on `receiveTimeout` for streams.
- **Timeout ≠ offline.** Map `connectionTimeout`/`sendTimeout`/`receiveTimeout` to a timeout error and only a connection error to a network error; "you are offline" comes from connectivity state. A timeout is transient and retryable.
- One retry layer only. Never auto-retry non-idempotent writes unless an idempotency key makes a replay safe; reuse the same key across retries.
- Realtime listeners (Firestore, sockets) reconnect on network loss but a **permission denial is terminal** for that listener: use bounded re-listen (backoff with a ceiling, timer cancelled on cancel, nothing re-subscribing once the screen stops watching), ignore stale cached snapshots after a denial, and drive UX from canonical server data rather than from the denial itself (it looks the same for "not granted yet", "outage" and "revoked").

## 5. Failure mapping

- **Never map a network failure onto a domain error.** Connection errors/timeouts are already distinguishable at the HTTP layer; a handler that catches every app exception and answers "code invalid" tells an offline user their input is wrong. Branch on the error code/type, and make the `default` arm the vaguest true statement, not the most specific verdict.
- A catch must tell the user as well as the log (global-error-handling.md §6). Capture the messenger/localizations before the `await`.
- Decide retry/auth behaviour from the error **type**, never from message substrings — an unrelated error whose text says "network" must not skip a needed sign-out or trigger a retry.
- An interceptor that overrides a shared `executeApiCall`-style wrapper must finish by mapping the exception it already caught; delegating back to the wrapper re-runs the request, double-firing a write after a transient failure.
- When a provider degrades to a fallback on error, disable provider auto-retry (see `riverpod-patterns`) so a later retry cannot swap the UI under the user.

## 6. Review checklist

- [ ] Every client route exists in the backend's snapshot (CI check or contract test); snapshot regenerated with the route change
- [ ] Field types read from the schema; non-required ⇒ nullable; decimals/ids parsed at the boundary
- [ ] Wire-key test covers normal, `null` and absent-key payloads
- [ ] New response fields verified against the live (rebuilt) service; client default fails toward the status quo
- [ ] Base URLs come from one config class; release builds assert HTTPS; no machine-specific host committed
- [ ] Every client comes from a factory with explicit timeouts; streams enforce first-byte and idle bounds
- [ ] Timeout, offline and domain errors stay distinct end to end; no `default` arm that asserts a domain verdict
- [ ] Shared limits/TTLs come from config both sides read, with the same key and unit
- [ ] Signed URLs used verbatim; no platform branches rewriting them

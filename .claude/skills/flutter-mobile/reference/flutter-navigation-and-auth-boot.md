# Flutter Navigation, Deep Links and Auth Boot Ordering

Read this before changing a router redirect, a route gate, bootstrap code that runs before `runApp`, a bottom sheet/dialog that closes by navigating, deep-link or notification-tap handling, or Android Back behaviour. It covers failures that compile, pass widget tests and only show up on a cold start or on a real device. Examples use GoRouter + Riverpod; apply the same reasoning to other stacks. Version-specific router behaviour is hedged — reproduce on your pinned version before adding a workaround.

Related: router + auth integration snippet in [flutter-architecture-patterns.md](flutter-architecture-patterns.md); provider lifecycle in the `riverpod-patterns` skill; iOS scene-delegate link forwarding in [flutter-platform-gotchas.md](flutter-platform-gotchas.md).

## Contents

1. [No authenticated request before auth resolves](#1-no-authenticated-request-before-auth-resolves)
2. [Router redirect semantics](#2-router-redirect-semantics)
3. [Work started before runApp](#3-work-started-before-runapp)
4. [Verifying a session-less boot](#4-verifying-a-session-less-boot)
5. [Shell navigation: choose the call by intent](#5-shell-navigation-choose-the-call-by-intent)
6. [Modal sheets and dialogs](#6-modal-sheets-and-dialogs)
7. [Android Back and predictive back](#7-android-back-and-predictive-back)
8. [Deep links and notification taps](#8-deep-links-and-notification-taps)
9. [Review checklist](#9-review-checklist)

---

## 1. No authenticated request before auth resolves

`currentUser == null` is also true while the auth SDK is still initialising. Never start authenticated work on `value == null`.

- Expose a tri-state phase and branch on it, not on nullability:

```dart
enum AuthPhase { unresolved, signedOut, signedIn }

@Riverpod(keepAlive: true)
AuthPhase authPhase(Ref ref) {
  final auth = ref.watch(authStateProvider); // AsyncValue<User?>
  if (auth.hasError) return AuthPhase.signedOut;   // stream error → treat as signed out
  if (!auth.hasValue) return AuthPhase.unresolved; // still initialising
  return auth.value == null ? AuthPhase.signedOut : AuthPhase.signedIn;
}
```

- **Close the class once, structurally, at the root.** Withhold the widget tree's `child` (show a splash) until `authPhase != unresolved`. Gate on *resolution*, not on splash-animation dismissal. Keep a bounded failsafe (a few seconds) so the app still renders if auth never emits; its reads then fail with 401 exactly as before.
- **Do not fix this one provider at a time.** Gating one of ten boot providers leaves every future screen unprotected.
- The auth HTTP interceptor must pass a 401 for a request made *before any credentials existed* straight through. Treating it as a dead session and wiping local data (database, keys, media) turns a start-up race into data loss. Wipe only on a real sign-out or a definitive server rejection — never on a transient failure, and classify by error type, not message text (see [flutter-security-hardening.md](flutter-security-hardening.md), token refresh).
- Authenticated calls reached from boot code carry their own `AuthPhase.signedIn` gate (load local cache unconditionally; fetch remote only when signed in, and re-run on sign-in).

## 2. Router redirect semantics

**`return null` means "no redirect — build the requested route".** It does not mean "wait". At cold start the requested route is usually the authenticated home.

```dart
// ❌ undecided is treated as "go ahead"
redirect: (context, state) {
  final onboarding = ref.read(onboardingDoneProvider);
  if (onboarding.isLoading) return null;      // builds the authenticated home
  ...
}

// ✅ return null only when you have DECIDED no redirect is needed
redirect: (context, state) {
  final phase = ref.read(authPhaseProvider);
  if (phase == AuthPhase.unresolved) return '/splash'; // safe, unauthenticated, no requests
  ...
}
```

Rules:

- When undecided, redirect to the safest **unauthenticated** destination: a top-level route outside the authenticated shell whose screen is pure presentation (no repository/API reads). Choose it deliberately — a login route may be the wrong default if it is accepted as a terminal state elsewhere in the chain (it can skip a first-run flow).
- **A gate that returns early is terminal for the locations it matches.** A pre-auth gate (intro tour, maintenance notice, invite) that allows `/login` while its condition is unmet strands a signed-in user on `/login`, because the post-auth gate never runs. Gate on auth state explicitly and let signed-in users fall through:

```dart
if (ref.read(authPhaseProvider) == AuthPhase.signedOut) {
  final tour = ref.read(tourSeenProvider);
  if (tour.isLoading) return '/tour';                 // unknown ⇒ NOT done
  if (!(tour.value ?? false)) return location == '/tour' ? null : '/tour';
}
return postAuthRedirect(ref, location); // signed-in users continue here
```

- Skip irrelevant async reads: if an identity is not admitted, bounce it *before* reading a provider whose answer cannot change the outcome.
- **Read in `redirect`, listen for refresh, never watch.** `ref.watch` of async providers inside a router-building provider registers them as dependencies of the router provider; when they go loading → data on cold start, the provider rebuilds and disposes the live `GoRouter`, and a later `context.go()` throws "used after being disposed". Build the router once (`keepAlive`), bridge providers to a `Listenable` with `ref.listen`, pass it as `refreshListenable`, read with `ref.read`.
- **Tests that catch this** (an E2E auth bypass short-circuits the redirect and hides it): drive the dependency providers loading → data and assert `identical(routerBefore, routerAfter)`; pin the *loading* state in a test that names it. A control that only distinguishes the fix because some provider happens to be un-overridden becomes a tautology when someone adds that override later.

## 3. Work started before `runApp`

Code in `bootstrap()` runs outside the widget tree, so the root gate in §1 cannot protect it.

- Activate providers there with `container.listen(provider, (_, _) {})`, **not** `container.read(provider)`. A bare read builds the provider chain once and nothing keeps it live, so listeners inside it (auth change → fetch, connectivity → drain) may never fire; every test still passes. The same applies to tests that activate a provider with `container.read` and then assert a listener fired — activate with `container.listen` and drive the real auth stream rather than pinning a phase.
- Put an inline marker on each pre-`runApp` activation stating why running it before auth settles is safe (for example `// auth-boot-safe: local cache only`). The marker makes review and an optional lint script (`container.read(` in bootstrap, `container.listen(` without the marker) trivial.

## 4. Verifying a session-less boot

Widget tests and E2E suites that bypass auth cannot prove this class is closed. Verify on a debug build on a simulator/device: a boot with no session issues **zero** authenticated requests (check the backend's request logs), and after sign-in every read carries a token.

- **iOS keeps keychain items across app uninstall.** Deleting the app then launching can restore the previous session, so you measure a signed-in boot while believing it was signed-out. On a *simulator* reset the keychain first (`xcrun simctl keychain booted reset`, simulator only) and confirm which shape you measured: a signed-in boot sends `Authorization` on every read; a session-less one sends none.
- Positive-control the log matcher itself (widen the time window until it returns hits) so "zero requests" means zero, not a wrong grep.

## 5. Shell navigation: choose the call by intent

An app with a bottom-nav shell has three different navigation needs. Using one call for all of them produces duplicate-shell races and stack corruption.

| Intent | Call |
|---|---|
| Switch tab / go to an in-shell destination | `context.go(inShellPath)` |
| Full-screen page above the shell (back returns) | `push`-style call |
| Intentional stack replacement: sign-in/out, onboarding, a finished flow back must not re-enter | replace-the-root (`go` to a top-level route) — name this explicitly in a helper |
| Deep link / notification tap | one dispatch helper used by every entry point |

- Never `push` an in-shell route from a page that sits above the shell: it mounts a second shell on top of the first.
- Never "fix" a navigation race with a sleep, delay, debounce or a transition-duration assumption, or by swallowing a duplicate-`GlobalKey` error.
- Prefer one set of project navigation helpers over raw `go`/`push` where the destination can leave or re-enter the shell; flag raw `go()` out of and back into the shell in review.
- **Version caveat (hedged).** A shell's navigator carries fixed keys, so a shell cannot be mounted twice; a `go()` that removes the shell from the root stack can leave the old shell mounted until the covering page's transition ends, and navigating back inside that window can build a second copy (debug: "Multiple widgets used the same GlobalKey"; release builds may show a blank body). This was observed on an older go_router line; go_router's changelog lists later fixes for shell navigator-key collisions (for example in 18.1.x). Reproduce on your pinned version (shell → `go(outside)` → one frame + ~100 ms → `go(shell)`; assert no duplicate-key error and one nav bar) **before** adding a workaround, and re-test after upgrading.
- `StatefulShellRoute` preserves per-tab state; a plain `ShellRoute` replaces its child on a tab switch and disposes the screen. Either way, treat "screen disposed mid-await" as a normal path (see the `riverpod-patterns` lifecycle section).
- A full-screen page reachable by deep link must always have a way back: opened cold there is nothing to pop, so give it a back control that pops when `context.canPop()` and otherwise `go`es to its owning tab.
- Entity detail routes take the id from the path (`/orders/:id`), never from an in-memory singleton, so a cold deep link reconstructs the screen.

## 6. Modal sheets and dialogs

When a floating nav bar or dock is painted above the shell's nested navigator, a sheet pushed on that navigator can be drawn *under* it, hiding its primary action. Moving sheets to the root navigator changes which navigator every close call must target, so these rules travel together:

1. Open every bottom sheet with `useRootNavigator: true`. Enforce with a small scan test over `lib/` that fails on a missing flag (and fails if it finds suspiciously few call sites, so a broken scan cannot pass).
2. **Close a sheet through the navigator that owns it.** `Navigator.of(sheetContext)` already resolves to the root. A close from the *opener's* context, or through a navigator captured before the sheet opened, must use `Navigator.of(context, rootNavigator: true)` — otherwise it pops the screen under the sheet and the sheet stays. A shared `open` helper should close its own sheet from its `sheetContext` and only report the result to the caller.
3. **Never navigate while the sheet is still open.** Leave after its `Future` completes. Router `pop()` behaviour with a pageless route on the root navigator differs by version; do not rely on it. Guard "is there a screen behind" on router match depth, not `canPop()` (true whenever a sheet is open).

```dart
var done = false;
await openSheet(context, onDone: () => done = true);
if (done && context.mounted && context.canPop()) context.pop();
```

**Test under a nested navigator.** A harness with only `MaterialApp(home: …)` has one navigator, so root == shell and a wrong pop passes. Mount the opener as the top page of a nested `Navigator` and assert the sheet is gone **and** the opener page is still there; revert one close call to prove the test fails.

## 7. Android Back and predictive back

- Predictive back is enabled with `android:enableOnBackInvokedCallback="true"` on `<application>`; intercept Back with `PopScope` (`canPop` + `onPopInvokedWithResult`) — `WillPopScope` is deprecated. (Flutter docs: Android predictive back.)
- The platform asks the app *ahead of time* whether the framework handles Back (`SystemNavigator.setFrameworkHandlesBack`). If the root navigator reports "nothing to pop" after a dialog/sheet closes while a nested shell navigator still has pages, the next Back can leave the app from a shell screen. Typical tell: Android-only, the in-app back arrow still works (it pops in Dart). Hedged approach: while the router `canPop()`, re-dispatch a `NavigationNotification(canHandlePop: true)` from a builder context above the `Navigator` and below `WidgetsApp` — verify the class and its semantics against the current Flutter API docs on your pinned version before adopting.
- Test on the platform channel, not on navigation: record `SystemNavigator.setFrameworkHandlesBack` calls (mock the `flutter/platform` channel) and pin both directions — somewhere to go back to (`true`), nowhere (`false`, so the root tab still exits). `tester.binding.handlePopRoute()` goes straight to Flutter and cannot see this.

## 8. Deep links and notification taps

- **Validate every parameter** from a link as untrusted input (allowlist the shape: UUID, integer, enum). Map notification payloads to routes through an allowlist; never `context.go(payload['path'])`.
- Accept only the app's own scheme/host; refuse paths carrying an encoded separator (`%2F`, `%5C`, `%3F`, `%23`, `%2E`), `%25`, or dot segments. Encode ids when building request paths.
- **Cold-launch vs warm links.** A link that *launches* the app is delivered with launch data (Android intent; iOS scene `connectionOptions.urlContexts`), not through the "open URL" callback. Pass it as the initial route.
- **A warm link can arrive while no router is listening** — before `runApp`, and (with the root gate from §1) from the first frame until auth resolves. The framework answers `didPushRouteInformation` with `false` when unhandled, and a fire-and-forget push is lost. Read the result and retry on a timer with a bounded window, newest link wins. A first-frame retry alone is not enough when a splash withholds the router for several seconds; test with real auth enabled, not an auth-bypass build.
- **iOS, if a custom scene delegate owns the Flutter engine:** nothing else delivers links to Flutter, so the delegate must forward both the launch link and later `openURLContexts` links (and let the auth SDK's own URL handler claim its callbacks first). See [flutter-platform-gotchas.md](flutter-platform-gotchas.md). If you use Flutter's own scene-delegate migration, check the current docs for how links reach the engine instead of copying native code from this file.
- Route all entry points (links, notification taps, in-app shortcuts) through the one dispatch helper from §5.
- Never expose sensitive routes (admin, payment confirmation) via links; prefer verified App Links / Universal Links over custom schemes.

## 9. Review checklist

- [ ] No authenticated request is issued before the auth phase resolves; the gate is structural (root), not per-provider
- [ ] Auth interceptor passes through a never-authenticated 401 and never wipes data on a transient failure
- [ ] Every `return null` in a redirect is a *decision*; undecided → safe unauthenticated route
- [ ] Early-returning gates handle every auth state they intercept
- [ ] Router provider uses `ref.read` in `redirect` and `refreshListenable` fed by `ref.listen`; a test asserts the router instance is stable
- [ ] Bootstrap activates providers with `container.listen`, each with a "safe before auth" note
- [ ] Session-less boot verified on a device/simulator with a clean keychain
- [ ] Navigation call chosen by intent; no sleeps/delays around navigation
- [ ] Sheets use `useRootNavigator: true`, close via the owning navigator, and are tested under a nested navigator
- [ ] Android Back behaviour after an overlay checked on a device; `PopScope` instead of `WillPopScope`
- [ ] Link parameters validated; cold and warm links tested (with real auth); a deep-linked full-screen page has a back path

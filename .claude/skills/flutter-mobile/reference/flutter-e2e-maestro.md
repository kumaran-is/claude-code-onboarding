# Flutter E2E — integration_test vs Maestro, Flow Conventions, Device Parity

> **Tool rule:** Flutter Android/iOS UI/E2E automation uses Maestro CLI/MCP exclusively; browser tools are never used for it. Missing Maestro/emulator/simulator/device = BLOCKED/NOT RUN. Canonical: `.claude/rules/testing-tool-selection.md`.

Read this before writing or running a Maestro flow, choosing between `integration_test` and Maestro, setting up
an emulator/simulator for E2E, or testing deep links and push notifications on a simulator. Unit/widget/golden traps are in
[flutter-testing-traps.md](flutter-testing-traps.md). Maestro behaviours below were checked against docs.maestro.dev and
Maestro CLI 2.12.1 is current (checked 2026-11-24); the flows here were verified on 2.11.0 (`maestro test --help`). 2.12.0 has one breaking change: a scroll `speed` outside 0–100 now fails instead of falling back to the default. Re-check after upgrades with the Maestro MCP `cheat_sheet` tool.
Run on Flutter 3.50.1 (2026-11-23): a debug build with `appId: ${APP_ID}`, `-e APP_ID=<id>` and
`--format junit --output report.xml` passed on an iPhone 17 simulator (iOS 26.4) and an Android 36.1 emulator
(Google Play image, arm64) and exited 1 on a deliberately wrong `assertVisible`; tested on both platforms.

## 1. Which tier proves what

| Tier | Runs | Can do | Cannot do | Gate |
|------|------|--------|-----------|------|
| Widget/unit | host VM, no device | provider overrides, fake clocks, debug asserts, layout assertions | real OS, real plugins | every PR |
| `integration_test` | in-process on a device/simulator | boot the real router + shell with provider overrides (fake auth, seeded local state, forced connectivity) | OS dialogs, install/permission flows | presence per PR; run on demand; CI job advisory |
| Maestro | black-box against the built app | real OS behaviour: permissions, deep links, airplane mode (Android), cross-platform YAML | inject Dart mocks | full suite before PR/release; scoped runs while iterating |

- Headless `flutter test integration_test/` fails with "No supported devices connected": gate **presence** of the files in CI, run them on
  a booted device locally, and run the device job in CI as **advisory** (warning + per-app summary table, never blocking a PR;
  manual dispatch may block). Device boots are slow and flaky; they must not wall off every PR.
- Split proof across tiers: Maestro proves the visible consequence ("exactly one completion after retries"); repository/integration
  tests prove the mechanism (idempotency key reuse, queue ordering). Do not make Maestro inspect a local database.
- Profile/release builds strip `assert()`; a green E2E says nothing about layout assertions. Prove layout in debug widget tests.
- Explore before codifying: start the app, inspect the live widget tree (Dart MCP `get_widget_tree`, Maestro `inspect_screen`),
  then write finders against what is really there (lazy lists, dev-only chrome and popup roles differ from the tree you imagine).

## 2. The seam: auth bypass and its blind spots

Black-box E2E needs a debug-only seam (an auth bypass, a seeded backend, test deep links). Rules:

- Gate the seam on a compile-time define and `kDebugMode`/non-release so it const-folds away in release; never ship it.
- A bypass installs no real identity: authenticated calls fail (401) and screens show their error surfaces. That is the bypass working,
  not a bug — but it also **deletes sign-in and sign-out from the test**, so a green bypass suite is blind to them. Verify real auth
  with a separate real-sign-in run.
- Add a **live-backend tier** for every feature that calls a backend: real sign-in against a seeded stack, at least one assertion
  that needs a genuine backend-answered success, plus a fault-injected failure case. An E2E that only proves the degraded fallback renders
  is not passing: a wrong URL and "no backend" look identical in that UI.
- Diagnose live reds by **data state before code theory**: row count above the endpoint's page cap, a first-run account already
  walked, seed rows whose time-relative state has expired, an auth-emulator store that is separate from the database (a non-zero
  account count ≠ seeded; assert the claims), a recreated emulator that wiped accounts while the database kept old ids, a fixture consumed
  by an earlier test. Seed rows that declare a shape use upsert-update, not insert-ignore (which prints success and keeps old values); verify by querying the row.

## 3. Platform divergences (silent false passes)

| Maestro command / area | iOS simulator | Android emulator | Do |
|------------------------|--------------|------------------|----|
| `back` | not supported (docs: Android and Web only) | works | Tap the app's Back control or use a shared `helpers/_back.yaml` |
| `setAirplaneMode` | passes but has no effect (docs: "iOS simulators do not have an airplane mode") | works | Offline flows are Android/physical only. An iOS run of an offline flow is **BLOCKED/INFRA_FAIL**, never PASS |
| `launchApp: permissions` / location | the iOS driver rejects some values you may use on Android (e.g. `location: deny`, observed on a 2.2.x driver; re-check) | works | Branch on `when: platform:` and use iOS-valid values |
| `launchApp: arguments:` | does **not** deep-link | does not deep-link | Use `openLink` |
| Deep link host | host dropped; route matches on the **path** | same | Use an empty host: `myapp:///orders/42` (not `myapp://orders/42`, which lands on `/42`) |
| First custom-scheme `openLink` | shows `Open in "<App>"?` and blocks later steps | none | Dismiss conditionally while that alert is visible (§4 snippet) |

- A stale older build with the same URL scheme on the simulator can capture links: if deep-link flows are red on a screen that looks
  like another app, list installed apps (`xcrun simctl listapps <udid>`) and uninstall stale ones before blaming code.
- Flutter 3.50 builds iOS plugins with Swift Package Manager by default; only CocoaPods-only plugins still add a `Podfile`.
  When one exists, an iOS build may rewrite its metadata (e.g. the CocoaPods version stamp in `Podfile.lock`); revert it before committing.
- Pin and document the emulator API level your Maestro version supports; drivers and API levels move together (one 2.2.x driver
  failed before the first command on a newer API; Maestro 2.11.0 drove API 36.1). An emulator whose `/data` is full fails
  `adb install` with `INSTALL_FAILED_INSUFFICIENT_STORAGE`: give the test AVD a larger `-partition-size` or a fresh AVD rather
  than reporting the flow red.

## 4. Flow conventions

- Location: `<app>/.maestro/*.yaml`; one journey per file; flow files that are only helpers live in `helpers/` with an `_` prefix.
- Header comment: what it proves, the precondition (fixture/seed state), platform limits. A wrong starting state is SETUP_FAIL, not FAIL.
- `appId: ${APP_ID}` and pass it with `maestro test -e APP_ID=<id>`; a hard-coded id fails `launchApp` with a bare install error and no assertion.
- `tags:` classify flows (`preconditioned`, `live`, `offline`); select with `--include-tags` / `--exclude-tags`.
- Shared steps → `runFlow: { file: helpers/_x.yaml, env: {...} }`; conditional steps → `runFlow: { when: { platform: iOS, visible: '…' }, commands: [...] }`.
- `text:` is a **full-match, case-insensitive regex** on the accessibility label, and Flutter merges a title with its subtitle into one node: use
  `"(?s).*Title.*"`. For per-row dynamic names give widgets `Semantics(identifier: …)` and match `id:` by regex rather than painted text.
- Wait with `extendedWaitUntil` / `waitForAnimationToEnd`; never fixed sleeps. `scrollUntilVisible` travels one direction: walk top→bottom, scroll
  `direction: UP` explicitly to return, never a bare `assertVisible` below the fold.
- A flow that mutates a server-persisted preference (locale, theme) restores it in the smallest window, with a self-heal guard.
- Capture `takeScreenshot` at the final business outcome and at the first failing checkpoint.

```yaml
# Order confirmation. PRECONDITION: seeded account with order 42 in "pending". PLATFORM: both.
appId: ${APP_ID}
tags: [preconditioned]
---
- launchApp
- runFlow:
    file: helpers/_open_link.yaml
    env: { LINK: "myapp:///orders/42" }          # empty host, path form
- extendedWaitUntil:
    visible: "(?s).*Order #42.*"                   # merged nodes -> DOTALL regex
    timeout: 20000
- tapOn:
    text: "Confirm"
    enabled: true                                  # target the actionable one; do not reach for optional
- assertVisible: "(?s).*Confirmed.*"               # required outcome: never optional
- takeScreenshot: order-confirmed
```

```yaml
# helpers/_open_link.yaml — dismiss the one-time iOS alert only while that alert is up
appId: ${APP_ID}
---
- openLink: ${LINK}
- runFlow:
    when:
      platform: iOS
      visible: 'Open in .*\?'                      # the alert title, never a bare "Open"
    commands:
      - tapOn:
          text: "Open"
          below: 'Open in .*\?'
```

## 5. Flows must be able to fail

A flow whose assertions are all `optional: true` passes whether the app works or not, and reads as coverage.

- Required navigation arrival, primary actions, state transitions and the final outcome are **never** `optional`.
- `optional: true` is allowed only for genuinely conditional platform UI (a permission prompt that may already be granted, an OS
  nag, a keyboard that may be closed), each with a comment naming the condition.
- A critical scenario contains, in order: an explicit precondition, a state-changing action, an intermediate checkpoint when
  multi-phase, a final business-state assertion, an evidence screenshot. A flow that only navigates and checks titles is a smoke test: register it as one.
- Assert strings the app actually renders: read them from the localization source, not memory or the design doc.
- Do not weaken a failing flow to turn it green (traps §7). Classification (PASS/FAIL/SETUP_FAIL/INFRA_FAIL): traps §8.
- If you add a checker, ship it with a known-bad and known-good control and make "control failed" a distinct exit code so a broken
  detector cannot read as a clean tree. A text check cannot judge whether an assertion is meaningful; review still does.

## 6. Spec ↔ flow ↔ test co-change

Coverage floors prove coverage did not drop, not that *your* change is exercised. For a UI-surface change (features, router, shell):

- the matching widget/unit test changes in the same PR, with **added assertion-bearing lines** (`expect(`, `find.`, `testWidgets(`): a comment, import or whitespace edit does not count;
- the matching Maestro flow changes in the same PR;
- before the PR, run only the flows for the screens you changed: tag each flow with its feature (`tags:` in the flow header) and run `maestro test --include-tags <feature> .maestro/`; the full suite runs in CI or nightly. A changed screen whose flows were not run is reported NOT RUN, not PASS;
- the escape hatch is an explicit tag in a commit message with a reason (e.g. `[widget-na: refactor, no observable change]`), reviewed like any exception;
- a check that parses diffs needs a self-test (known-bad must trip) and a full-depth checkout (`fetch-depth: 0`).

Co-change is a CI/hook concern (see the Flutter hooks owner); keep it advisory in a template and make it blocking per team.

## 7. Evidence and device parity

- Evidence layout (gitignored): `test-results/<app>/<scenario>/<timestamp>/` — PASS: `result.md`, metadata, final screenshot; non-PASS adds the runner
  log, first-failed-checkpoint screenshot and before/after shots. `takeScreenshot` writes to the process working directory unless you pass `--test-output-dir`.
  A missing screenshot is not a PASS; a log that never reached the first assertion is INFRA_FAIL.
- After a Maestro run that PASSED on a real emulator, simulator or device, record it: `python3 .claude/scripts/review_state.py stamp write ui-mobile --note "<flows, device, passed count>"`.
  The Stop hook reminds you when Flutter `lib/` changed without one; no device means BLOCKED, never a stamp.
- **Open the failure screenshot before naming a root cause.** A red assert alone cannot distinguish "not rendered", "rendered off-screen" and "feature broken".
- Attribute an intermittent red as mine vs inherited only with ≥ 3 runs on the base branch (traps §9).
- Never name a device by literal id (`emulator-5554`, a pasted UDID). Resolve it from configuration through one script that prints the id on stdout only and
  diagnostics on stderr, and exits non-zero with **no** stdout when it fails (an empty `-d` is safe; a wrong one is not). Pass `adb -s "$SERIAL"` on every call.
- "Booted" is not "ready": wait until the system server answers (e.g. `adb -s "$SERIAL" shell cmd activity get-current-user`) before installing.
  `adb` exit codes lie (unknown subcommands can exit 0): verify device mutations by re-reading state.
- Inherited radio state: an offline flow can leave airplane mode on, failing the next run on Android while iOS stays green (the simulator shares the host network).
  Check `settings get global airplane_mode_on` and reachability from inside the guest (`nc` to `10.0.2.2:<port>`; the guest has `nc`, not `curl`).
- Pin the AVD/simulator by name+runtime in config; fail loudly (with a message) when it is missing — a `set -e` script whose `grep` finds no AVD can exit with no output at all.

## 8. Deep links and push notifications on a simulator

`xcrun simctl push` injects a **local** notification; it proves presentation, payload parsing, launch/resume, tap routing and
state-aware destinations. It never proves server → FCM → APNs delivery, token registration or physical-device behaviour.
State which you tested: `SIMULATOR` or `TRANSPORT`.

```bash
cat > /tmp/payload.apns <<'JSON'
{ "aps": { "alert": { "title": "Order shipped", "body": "Order 42" } },
  "type": "order.shipped", "orderId": "42", "eventId": "evt-1" }
JSON
xcrun simctl push booted com.example.app /tmp/payload.apns   # payload: top-level object, has "aps", ≤ 4096 bytes
```

- Verified against `xcrun simctl push --help` (Xcode on the writing machine): `<device> [<bundle id>] (<json file> | -)`; a `Simulator Target Bundle` key may replace the bundle argument.
- Background the app first; foreground banners depend on the app's presentation options and a simulated push is not an `onMessage` event.
- Two modes: synthetic event ids (UI/route only — may not claim "marked read") vs a real event id from a real feed (may claim mark-read).
- Keep a catalogue of payloads per type with the destination expected after tap, including a state-aware case (already-confirmed → different screen)
  and a missing-entity fallback. Take ids from the seed script's constants, never pasted UUIDs.
- Acceptance unit: event → policy → card/push → tap → destination → read state. Test each hop.

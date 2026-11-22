# Flutter Testing Traps — Tests That Pass Vacuously, Flake, or Lie

Read this when writing or reviewing widget/unit/golden tests, when a test is green but you do not trust it, when a
suite flakes, or when a gate is red and you have to decide whether your change caused it. Templates for the happy path
live in [flutter-testing-patterns.md](flutter-testing-patterns.md); E2E/Maestro in [flutter-e2e-maestro.md](flutter-e2e-maestro.md).

**Core idea:** a test proves nothing until it can fail for its own stated reason. Most bugs below make a test
*unable to fail*. Version-dependent claims are marked; re-check them against your pinned Flutter/Riverpod.

---

## 1. Test surface and font are not a phone

| Trap | Effect | Fix |
|------|--------|-----|
| Default test surface is 800×600 | A test that only sets `textScaler` measures a tablet; phone-width overflow never appears | Set the view explicitly and reset it |
| Tests render in the monospace test font (Ahem-style, much wider than real UI fonts) | Any width/dp number from a widget test is meaningless on device | Assert structure, an edge, or a font-independent axis (height); verify real-font reflow on a simulator |

```dart
tester.view.physicalSize = const Size(390 * 3, 900 * 3); // 390×900 logical at DPR 3
tester.view.devicePixelRatio = 3.0;
addTearDown(tester.view.resetPhysicalSize);
addTearDown(tester.view.resetDevicePixelRatio);
// Use the worst-case fixture: longest string, every locale, largest text scale.
```

Never write "button is 48dp wide on device" from a widget test; it guards structural regressions only.
Non-debug (profile/release) builds strip `assert()`, so layout assertions must be proven in a debug-mode widget test
(assert `tester.takeException()` is null) or a debug device run — a green release-mode E2E cannot catch an overflow.

## 2. One `testWidgets` = one `pumpWidget`

A second `pumpWidget` of the same widget type and key **reuses the element and its `State`**. Later provider
overrides never apply, and a loop re-asserts the first case N times. Any `State` flag latched on the first build
(`_didInit`, `_seeded`) stays latched.

```dart
// ✗ tests values.first, N times
for (final v in values) {
  await tester.pumpWidget(harness(value: v));
  expect(find.text(expected[v]!), findsOneWidget);
}
// ✓ distinct key disposes the old State (or: one testWidgets per case — required when a State flag varies)
for (final v in values) {
  await tester.pumpWidget(harness(key: ValueKey(v), value: v));
  expect(find.text(expected[v]!), findsOneWidget);
}
```

Give shared `pumpApp`/harness helpers an optional `Key? key` and say why in a comment. Never pump a second
`ProviderScope` with different overrides to change state mid-test; drive one scope's override from a
`StreamController` and `add()` the new value. Run the positive control (§7) **per value**, not once.

## 3. Assertions that cannot fail

| Shape | Why it is inert | Do instead |
|-------|-----------------|-----------|
| `TextOverflow.ellipsis` added to "fix" overflow | Overflow becomes silent: `takeException()` is null, `findsOneWidget` passes | `expect(tester.renderObject<RenderParagraph>(f).didExceedMaxLines, isFalse)`; for `maxLines: null`/`softWrap: false` assert line count or `size.width >= getMaxIntrinsicWidth(double.infinity)`; at large type stack instead of squeeze |
| Aggregate of N values (`join`, `sum`, `toSet`, `contains`) | `enterText` writes the controller directly, so the "whole" is true even if the widget's per-box logic is deleted | Assert the elements: `['A','B','1','2']` not `'AB12'` |
| Matcher loose enough to fit several variants (`textContaining`) | Matches both plural/ICU branches, pins neither | Assert the exact string per branch; one test per branch |
| Negative assertion with ONE finder strategy | Passes vacuously when the finder goes blind (semantics moved a string) | Pair with a second strategy (text OR semantics label), and prove the positive form first |
| Row below the fold in a lazy list | An unbuilt row makes `takeException()` pass vacuously | Inject state and scroll the row into view deliberately, then assert |
| Fixture richer than the real payload | Fallback logic (`address ?? reference`) passes with full fixtures and breaks on the real list endpoint | Build fixtures from the endpoint's real field set (omitted fields are null) whenever logic branches on fallbacks; run the live flow before calling it done |
| Screen has an offline/empty arm that renders the same widget | Asserting the shared empty-state widget passes on the wrong arm | Override connectivity to the arm under test; assert something only that arm builds |
| "Renders in dark theme" | Tautological: it renders in any theme | Pump under both themes, collect painted colours from the `RenderParagraph`s, require the two sets to be **disjoint**; a hard-coded colour lands in both and fails by name. Proves theme-awareness, not correctness — contrast still needs review |

```dart
Set<Color> paintedTextColors(WidgetTester t) => {
  for (final p in t.renderObjectList<RenderParagraph>(find.byType(RichText)))
    if (p.text.style?.color != null) p.text.style!.color!,
};
// pump light (key: ValueKey('light')) → a; pump dark (key: ValueKey('dark')) → b
// expect(a.intersection(b), isEmpty);  Positive-control with a deliberately theme-blind tree.
// Mutate the ColorScheme token, not a base TextStyle: .copyWith(color:) at the call site masks the mutation.
```
(Recipe sketch; `p.text.style` is the span's own style — merge inherited styles if your widgets rely on them.)

## 4. Finder, semantics and stream traps

- `tester.getSemantics(find.byKey(k))` resolves to the **nearest ancestor** semantics node, so a merged label can
  be what you read. Locate by `find.bySemanticsLabel(...)` (it also counts nodes, exposing double-node bugs). A label inside a
  labelled section can be child-count dependent (`"SECTION\nChild"`): dump the label first, then assert with an anchored `RegExp`.
- Read merged flags through `getSemantics(...)`/`getSemanticsData()` and `data.flagsCollection.isButton`.
  `SemanticsData.hasFlag` is **deprecated** (API docs: "deprecated after v3.32.0-0.0.pre", use `flagsCollection`).
- Perform semantic actions with `tester.semantics.performAction(find.semantics.byLabel('Send'), SemanticsAction.tap)`
  (`SemanticsController.performAction` — the `semanticsOwner` route is the old way; check the deprecation notes on your SDK).
  Call `tester.ensureSemantics()` and **dispose the handle in the test body** (last statement or `finally`), not via
  `addTearDown` — the leak check runs before teardown callbacks.
- `find.byType` skips offstage widgets by default (zero-size items in lazy lists); pass `skipOffstage: false` when needed.
- `scrollUntilVisible` throws "Too many elements" on a screen with a multiline `TextField`: pass
  `scrollable: find.byType(Scrollable).first`. `enterText` needs the field built — inject state instead of scrolling blind.
- An un-listened single-subscription `StreamController`'s `close()` never completes, so `addTearDown(controller.close)`
  hangs every test that never subscribes (tell: the test process idles at ~0% CPU, no output). For a never-resolving
  stream use `Stream.fromFuture(Completer<T>().future)` built inside the override callback.
- If a provider's `ref.listen` callbacks never fire in a test, check how it was activated: Riverpod 3 can pause
  listeners of providers nobody is watching. Activate it the way production does (`container.listen(p, (_, _) {})`)
  before reading. *(Mechanism per Riverpod 3 pause/resume docs; verify against your version.)*
- A provider chain added to a screen that is mounted by a shell breaks every test that mounts the router: sweep all
  router-mounting test files and give each the never-completing override.
- `flutter test <dir>` compiles one kernel: a single type error makes siblings report `loading <file>`. Re-run the suspect file alone before diagnosing. Run from the package root: from a monorepo root, relative asset/fixture paths fail with `PathNotFoundException`.

## 5. Time, timers and concurrency

If you inject a clock, **every** time source must be virtual. A virtual clock with a real `Timer.periodic` or
`Future.delayed` passes on an idle machine and fails (`Expected 2, Actual 1`) when the suite saturates the CPU — and
it fails in a package your change never touched, so the first cost is attribution.

```dart
// pubspec: dev_dependencies: fake_async: 1.3.3   (latest on pub.dev when written; flutter_test ships it transitively
// but Dart requires a direct declaration to import it)
test('emits null once the sample ages past the window', () {
  fakeAsync((async) {
    var now = DateTime(2025);
    final seen = <Sample?>[];
    final sub = ageAware(source, clock: () => now, window: const Duration(seconds: 30)).listen(seen.add);
    source.add(sample);
    async.elapse(Duration.zero);
    now = now.add(const Duration(seconds: 31));
    async.elapse(const Duration(seconds: 1)); // the ticker fires virtually
    expect(seen.last, isNull);
    sub.cancel();
  });
});
```

- No `sleep`/`Future.delayed` as synchronisation; wait on a condition or elapse a fake clock. Seed all randomness.
- `fakeAsync` cannot await real I/O; keep real I/O out of the unit under test (fake it) or use `tester.runAsync`.
- Concurrency/lease/lock tests pin the **contested moment**: park A inside operation X, start B, release in order.
  "Start both and hope they overlap" stays green with the guard removed. Always run the remove-the-guard control.

## 6. Golden determinism

1. One canonical golden set, committed. Do not keep per-OS PNG sets.
2. Fix the surface and pixel ratio (§1); load real fonts, or obscure text (Ahem) so font hinting cannot differ per OS.
3. Cross-OS anti-aliasing drift is small but nonzero; exact match (0.0) fails on a different OS than the one that
   generated the baseline. Allow a small tolerance sized to measured drift with headroom, small enough that real
   regressions still fail (an order of magnitude below a real layout change).
4. Update policy: regenerate (`--update-goldens`) only after an intentional visual change, review the PNG diff in the PR,
   never to turn CI green.
5. Prefer goldens for shared components/tokens (light + dark, key states) over per-screen goldens.

With `alchemist` (pub.dev: maintained; 0.14.1 supports Flutter ≥ 3.32, 0.15.0 needs Flutter ≥ 3.44 / Dart ^3.12 —
pick the version your SDK supports and pin it; `CiGoldensConfig.diffThreshold` and the config below compile and run on alchemist 0.15.0 / Flutter 3.44.2):

```dart
// test/flutter_test_config.dart — wraps every test in the package; a no-op for non-golden tests
import 'dart:async';
import 'package:alchemist/alchemist.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) {
  return AlchemistConfig.runWithConfig(
    config: const AlchemistConfig(
      platformGoldensConfig: PlatformGoldensConfig(enabled: false),
      ciGoldensConfig: CiGoldensConfig(diffThreshold: 0.01), // fraction (0.01 = 1%); size to YOUR measured drift
    ),
    run: () async => await testMain(), // alchemist 0.15.0 wants Future<void> Function(); a bare `testMain` does not compile
  );
}
```

Tolerance value, defaults (`obscureText`, `renderShadows`) and the "ambient comparator must be `LocalFileComparator`" restriction
come from a specific version's source — re-read the package docs for your pinned version before relying on them.
`golden_toolkit` is discontinued; do not use it.

## 7. Controls: make the test fail on purpose

Before calling a test done:

1. Break the production behaviour it claims to guard (delete the guard, invert the condition).
2. Re-run only that test. It must go red, **for the reason in its title**.
3. Looped or parameterised tests: do this once per case.
4. Record a mutation matrix when several tests share one behaviour:

| mutation | test A | test B | test C |
|----------|--------|--------|--------|
| none (baseline) | PASS | PASS | PASS |
| remove guard | FAIL | FAIL | PASS |
| leak the ticker | PASS | PASS | FAIL |

Every test must be red under at least one mutation. A test no mutation turns red is inert.

**Never weaken a test to make it pass.** Do not make a required assertion optional, delete a checkpoint, relax a
fixture, or edit an oracle to match wrong behaviour. A failing check is a product problem until proven otherwise.
Report the failure; do not launder it. (Same rule for E2E flows: [flutter-e2e-maestro.md](flutter-e2e-maestro.md) §5.)

## 8. Outcome classification (never just pass/fail)

| Outcome | Meaning | Action |
|---------|---------|--------|
| **PASS** | The app behaved correctly | Keep evidence |
| **FAIL** | The app ran; behaviour was wrong | Product bug: root-cause, fix, re-run the exact scenario |
| **SETUP_FAIL** | Precondition invalid (stale fixture, wrong account, not signed in, aged seed data) | Reset once, re-verify; still wrong → stop and report |
| **INFRA_FAIL** | Environment prevented execution (simulator won't boot, runner missing, backend down, emulator left offline) | Fix the environment; do not touch tests or product code |

Never report SETUP_FAIL or INFRA_FAIL as FAIL: it sends someone to fix code that was never broken. In the validation
matrix below, these two are reported as **BLOCKED** with the reason.

## 9. Flaky tests, false reds and attribution

**Flake protocol**
1. Re-run the failing test alone, then on the base branch **at least 3 times**. One green base run proves nothing about a flake.
2. A red under CPU saturation is not evidence: compare with an idle run before touching code.
3. Do not fix by adding sleeps or blind retries. A retry-to-green is acceptable only with traces kept and a tracking issue.
4. Quarantine = a non-blocking lane with an owner, a root-cause tag (infra | test bug | product race), an expiry
   (e.g. 4 weeks, then fix or delete) and re-entry criteria (e.g. 20 consecutive passes). Treat these numbers as defaults to tune.
5. Assert the settled end state, never a spinner, skeleton or animation-timing window.

**Read the failure's own attribution first.** A red Flutter run prints `The relevant error-causing widget was:` plus a
stack. A huge overflow number (e.g. `overflowed by 99718 pixels`) usually means a build threw (missing theme extension,
null check) and left a layout unsized: the overflow is the symptom. Read the first framework frame before theorising
about layout. Open the failure **screenshot** before naming a UI root cause ("not visible" ≠ "not rendered" ≠ "feature broken").

**A red gate is not proof of source drift until stale local state is ruled out.**

| Stale state | Tell | Clear |
|-------------|------|-------|
| Build artifacts (e.g. `build/ios/**`, pods) | All errors under that path; real-source error count 0 | Delete that artifact dir |
| Generated code after a merge/branch switch | `Target of URI hasn't been generated`, `_$XFromJson isn't defined` | `dart run build_runner build --delete-conflicting-outputs` |
| Localization output out of sync with ARB files | `getter 'x' isn't defined for AppLocalizations` though the key exists | `flutter gen-l10n` |
| **Orphaned** generated file (source deleted/renamed) | Many errors inside one generated file | Delete that file; regenerating does not remove it |

```bash
# real vs build-artifact errors (pattern depends on your analyzer output format)
total=$(grep -c ' error ' analyze.log); art=$(grep ' error ' analyze.log | grep -c 'build/'); echo "real=$((total-art))"
```
Running the iOS app regenerates its package checkouts under `build/`; run analyzer/test gates before launching, or clean afterwards.
A throw-away worktree of the base branch has no codegen, so "does it fail on base?" there is unsound for generated-code projects:
remove your change in place, regenerate, re-run instead.

## 10. Validation matrix — change type → required validation → command

Status vocabulary: **PASS**, **FAIL**, **BLOCKED** (could not run; say why), **NOT RUN** (skipped; say why),
**NOT APPLICABLE** (change cannot affect it). Report counts from tool output; "looks right" is not evidence. Substitute
your project's runner for `flutter test` where it wraps one.

| Change type | Required validation | Command |
|-------------|--------------------|---------|
| Pure logic, use case, provider | Unit test: happy path + ≥ 1 failure path; control (§7) | `flutter test test/unit/<path>` |
| Bug fix | Failing test first (shown red), then green; scoped re-run of the exact failing case | `flutter test <file>` before/after |
| New or changed screen/widget | Widget test per state (loading/data/error/empty) at phone viewport; `takeException()` null; semantics label asserted | `flutter test test/widget/<path>` |
| Timer/stream/clock logic | `fakeAsync` test; repeat 3× to rule out flake | `flutter test <file>` ×3 |
| Shared component, tokens, theme | Widget test + goldens (light/dark); disjoint-colour check; update goldens only if the change is intentional | `flutter test test/golden/` |
| Router/auth redirect | Cold-start routing test + `integration_test` boot on a device | `flutter test integration_test/<file> -d <device>` |
| User-visible UI change | Co-changed widget test **and** E2E flow updated; scoped flow run | `maestro test <flow>.yaml` |
| Backend-calling UI | One real-auth flow vs a seeded stack asserting a backend-answered success plus an injected failure | see e2e §2 |
| Offline/airplane behaviour | Android emulator or physical device only; iOS simulator run → BLOCKED | see e2e §3 |
| Generated code, l10n, merge, branch switch | Regenerate before any gate; orphan sweep | `dart run build_runner build -d`; `flutter gen-l10n` |
| Pre-PR / release | Analyzer 0 issues, formatter clean, full tests, coverage floors on **hand-written** code (generated excluded), full E2E suite **last**, after version/changelog edits | `flutter analyze`; `dart format --set-exit-if-changed .`; `flutter test --coverage` |

Run slow gates last: any edit after the full E2E run (version bump, changelog, docs inside the gate's scope) voids it.
Coverage floors should only ratchet up; lowering one needs an explicit, recorded approval. Exclude generated files
(`*.g.dart`, `*.freezed.dart`, generated l10n) from the measurement (e.g. `lcov --remove coverage/lcov.info '*.g.dart' '*.freezed.dart' -o coverage/lcov.clean.info`), or they distort the ratio.

# Flutter CI (GitHub Actions)

PR gate for a Flutter 3.50.1 / Dart 3.14.0 app: pinned SDK, codegen, format, analyze, unit/widget/golden tests, a
dependency-advisory gate and one build per platform. Device UI/E2E is **Maestro only**
(`.claude/rules/testing-tool-selection.md`) and runs in its own job; without an emulator or simulator it is **BLOCKED**,
never replaced by a browser or Flutter Web run. Per-check status words and gate-integrity rules:
`.claude/rules/flutter-verification.md`. What each test tier proves:
`../../flutter-mobile/reference/flutter-e2e-maestro.md` §1 and `../../flutter-mobile/reference/flutter-testing-traps.md` §10.

**Evidence (2026-11-23).** Every `run:` command in the `verify`, `android` and `ios` jobs was executed locally on
Flutter 3.50.1 against a sample app (macOS host): each exited 0, and each gate failed on a planted defect (tampered
`pubspec.lock` → `--enforce-lockfile` exit 65; advisory-affected dependency → advisory gate exit 1; unformatted file,
deprecated import, 1-px golden change → exit 1). The Maestro flow passed on an iPhone 17 simulator and an Android 36.1
emulator and failed on a wrong assertion. The **workflow file itself has not run on GitHub**: runner images, caching and
the emulator action are DOCUMENTED BUT NOT TESTED. iOS CI on `macos-*` runners is documented, not verified.

Action pins (resolved 2026-11-23 with `git ls-remote`, commit SHAs; re-resolve before copying):
`actions/checkout` v7.0.1, `subosito/flutter-action` v2.23.0, `actions/setup-java` v6.3.0,
`actions/upload-artifact` v7.0.2, `ReactiveCircus/android-emulator-runner` v2.38.0.
`flutter-version-file` reads the **exact** Flutter version from `pubspec.yaml` (`environment: flutter: 3.50.1`, never a
range — flutter-action v2.23.0 README); that constraint resolves with `flutter pub get` on 3.50.1. `cache: true` caches
the SDK and, unless `pub-cache` is set, the pub cache too.

```yaml
name: Flutter CI
on:
  pull_request:
    paths:
      - 'mobile/**'                       # app root; list every shared input the jobs read:
      - 'mobile/pubspec.lock'             # lockfile
      - 'mobile/analysis_options.yaml'    # lint config
      - '.github/workflows/flutter-ci.yml'
permissions:
  contents: read
concurrency:
  group: flutter-ci-${{ github.ref }}
  cancel-in-progress: true
defaults:
  run:
    shell: bash                           # explicit bash = -eo pipefail on every step
    working-directory: mobile

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2 # v2.23.0
        with:
          channel: stable
          flutter-version-file: mobile/pubspec.yaml
          cache: true
      - name: Resolve exactly the lockfile and fail on security advisories
        run: |
          flutter pub get --enforce-lockfile 2>&1 | tee pub-get.log
          if grep -q 'affected by security advisories' pub-get.log; then
            echo "::error::pub reports security advisories for locked dependencies"
            exit 1
          fi
      # Generated code is usually gitignored: generate BEFORE analyze/test or both inspect nothing.
      - run: dart run build_runner build
      - run: dart format --output=none --set-exit-if-changed lib test
      - run: flutter analyze
      - run: flutter test --coverage --test-randomize-ordering-seed=random
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        if: failure()
        with:
          name: golden-failures
          path: mobile/test/**/failures/
          if-no-files-found: ignore

  android:
    needs: verify
    runs-on: ubuntu-latest
    timeout-minutes: 40
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-java@d1374f8ac74474200d16ef8ecee22c7ae7a51880 # v6.3.0
        with:
          distribution: temurin
          java-version: '21'
      - uses: subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2 # v2.23.0
        with:
          channel: stable
          flutter-version-file: mobile/pubspec.yaml
          cache: true
      - run: flutter pub get --enforce-lockfile
      - run: dart run build_runner build
      - run: flutter build appbundle --release --obfuscate --split-debug-info=build/symbols

  ios:                                    # documented, not verified on a GitHub macOS runner
    needs: verify
    runs-on: macos-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2 # v2.23.0
        with:
          channel: stable
          flutter-version-file: mobile/pubspec.yaml
          cache: true
      - run: flutter pub get --enforce-lockfile
      - run: dart run build_runner build
      - run: flutter build ios --release --no-codesign
```

Each `run:` step is its own gate: GitHub Actions fails the step on the tool's exit code. Do not append `| tail`,
`|| true` or `continue-on-error` to any of them. `dart pub get` prints advisories but **exits 0**, so the grep step is
what turns them into a gate; it stops on an unreadable lockfile first because the shell runs with `pipefail`.

## Rules

- **Pin the SDK** (exact version in `pubspec.yaml`) and install with `--enforce-lockfile`, so CI resolves the
  same packages as the committed `pubspec.lock`.
- **Codegen before analysis.** A missing `*.g.dart` / `*.freezed.dart` / `*.mocks.dart` makes analyze and tests fail
  for the wrong reason, or pass vacuously if the gate only reads generated output. build_runner 2.16.2 prints
  "These options have been removed and were ignored: --delete-conflicting-outputs" for both that flag and `-d` (tested),
  so do not add them.
- **build_runner and mockito:** mockito 5.8.1 (latest) needs `build <5.0.0`; build_runner 2.17.1 needs `build 5.0.x`
  and 2.17.0 is retracted. An app that generates mocks with mockito pins `build_runner: 2.16.2`; one that uses only
  mocktail can take 2.17.1. Tested: the 2.17.1 + mockito 5.8.1 pair fails `pub get`.
- **Melos workspaces:** run `dart run melos bootstrap` and `dart run melos run <script> --no-select` (Melos as a
  workspace dev_dependency, never a global activation): `../../flutter-mobile/reference/flutter-build-and-workspace.md`.
- **Never loosen a gate to go green:** no lowering coverage floors, no new `// ignore:` lines, no regenerated
  goldens to match a regression (`flutter-verification.md` "Gate integrity"). Goldens are rendered on the CI OS: generate
  and review them on that OS (or use alchemist CI goldens, which render text as blocks), never on a developer Mac.
- **Build once, promote the artifact.** The release workflow builds the signed AAB/IPA once, uploads it with its
  `build/symbols` (needed to read obfuscated stack traces), and every later stage (internal → beta → production) promotes
  that same artifact; never rebuild per stage.
- **Signing secrets** (keystore, App Store Connect key) belong only in the release workflow, from GitHub
  environment secrets with required reviewers — never in the PR job. Store upload: `gpd-release-flow` (Google Play),
  `asc-release-flow` (App Store); end-to-end runbooks: `docs/workflows/android-google-play-release.md`,
  `docs/workflows/ios-app-store-release.md`.
- **Maestro device job:** separate job that boots an emulator or simulator, installs the built app and runs
  `maestro test -e APP_ID=<id> --format junit --output report.xml .maestro/`, uploading the report and `~/.maestro/tests`
  on failure. Android on `ubuntu-latest` (KVM) can use `ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d # v2.38.0`
  with `api-level`, `arch: x86_64` and the flow command in `script:`; install the CLI pinned
  (`MAESTRO_VERSION=2.11.0` for the `get.maestro.mobile.dev` installer). Start it **advisory** (warning + summary, not
  blocking) until the flows are stable, as `flutter-e2e-maestro.md` §1 recommends; a missing device reports BLOCKED, not PASS.
- **GenUI apps:** `a2ui_flutter` 0.5.0 / `a2ui_core` 0.9.0 need Flutter ≥ 3.47.0 / Dart ≥ 3.13.0, which the 3.50.1 pin
  satisfies; the older-SDK path (`a2ui_flutter` 0.4.0 / `a2ui_core` 0.8.0) is only for apps still below 3.47.
- **Monorepo with GenUI:** the A2UI contract job set (schema, parity, Flutter analyze/test) is in
  `genui-contract-ci.md`; do not duplicate it here.

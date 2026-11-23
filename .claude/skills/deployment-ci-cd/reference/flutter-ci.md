# Flutter CI (GitHub Actions)

PR gate for a Flutter 3.41.x app: pinned SDK, codegen, format, analyze, unit/widget tests, and a release build.
Device UI/E2E is **Maestro only** (`.claude/rules/testing-tool-selection.md`) and runs in its own job; without an
emulator or simulator it is **BLOCKED**, never replaced by a browser or Flutter Web run. Per-check status words and
gate-integrity rules: `.claude/rules/flutter-verification.md`. What each test tier proves:
`../../flutter-mobile/reference/flutter-e2e-maestro.md` §1 and `../../flutter-mobile/reference/flutter-testing-traps.md` §10.

Action pins (resolved 2026-11-23 with `git ls-remote`; re-resolve before copying): `actions/checkout` v7.0.1,
`subosito/flutter-action` v2.23.0. `flutter-version-file` needs the **exact** Flutter version in `pubspec.yaml`
(`environment: flutter: 3.41.x` with a real patch number) — DOCUMENTED BUT NOT TESTED (flutter-action v2.23.0 README).

```yaml
name: Flutter CI
on:
  pull_request:
    paths:
      - 'mobile/**'                       # app root; list every shared input the job reads:
      - 'mobile/pubspec.lock'             # lockfile
      - 'mobile/analysis_options.yaml'    # lint config
      - '.github/workflows/flutter-ci.yml'
permissions:
  contents: read
concurrency:
  group: flutter-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    defaults:
      run:
        working-directory: mobile
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
      # Generated code is usually gitignored: generate BEFORE analyze/test or both inspect nothing.
      - run: dart run build_runner build --delete-conflicting-outputs
      - run: dart format --output=none --set-exit-if-changed lib test
      - run: flutter analyze
      - run: flutter test --coverage
      - run: flutter build appbundle --release --obfuscate --split-debug-info=build/symbols
```

Each `run:` step is its own gate: GitHub Actions fails the step on the tool's exit code. Do not append `| tail`,
`|| true` or `continue-on-error` to any of them.

## Rules

- **Pin the SDK** (exact version in `pubspec.yaml`) and install with `--enforce-lockfile`, so CI resolves the
  same packages as the committed `pubspec.lock`.
- **Codegen before analysis.** A missing `*.g.dart` / `*.freezed.dart` makes analyze and tests fail for the wrong
  reason, or pass vacuously if the gate only reads generated output.
- **Never loosen a gate to go green:** no lowering coverage floors, no new `// ignore:` lines, no regenerated
  goldens to match a regression (`flutter-verification.md` "Gate integrity").
- **Signing secrets** (keystore, App Store Connect key) belong only in the release workflow, from GitHub
  environment secrets with required reviewers — never in the PR job. Store upload: `gpd-release-flow` (Google Play),
  `asc-release-flow` (App Store); end-to-end runbooks: `docs/workflows/android-google-play-release.md`,
  `docs/workflows/ios-app-store-release.md`.
- **Maestro device job:** separate job on a runner that can boot an emulator or simulator, `maestro test` with
  `-e APP_ID=<id>`, artifacts uploaded on failure. Start it **advisory** (warning + summary, not blocking) until the
  flows are stable, as `flutter-e2e-maestro.md` §1 recommends; a missing device reports BLOCKED, not PASS.
- **Monorepo with GenUI:** the A2UI contract job set (schema, parity, Flutter analyze/test) is in
  `genui-contract-ci.md`; do not duplicate it here.

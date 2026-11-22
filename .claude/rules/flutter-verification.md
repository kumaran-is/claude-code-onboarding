---
paths:
  - "**/*.dart"
  - "**/pubspec.yaml"
  - "**/analysis_options.yaml"
  - ".github/workflows/**"
---

# Flutter verification

Path-scoped: loads only when Dart, pubspec, analysis-options or workflow files are in play. Detail and commands: `.claude/skills/flutter-mobile/reference/flutter-testing-traps.md` (validation matrix) and `.claude/commands/verify.md`.

- **Status words per check:** PASS | FAIL | BLOCKED | NOT RUN | NOT APPLICABLE. Only PASS is a pass. Never write "tests pass" for a command you did not run in this session.
- **Order:** narrow check after each fix → one review of the complete change → fix findings in one batch → run heavy gates (device/E2E, release build) once, last. An edit after a heavy gate voids that gate.
- **Exit codes:** use the command's own exit code, never a pipe's. For `flutter analyze` count errors, warnings and infos.
- **Attribute before re-running:** is the failing file in my diff against the merge base? For a suspected flake, capture the artifact, re-run that one test once, and record it. Never re-run until green.
- **Per package root:** run tests from each package's own root; mixing roots in one invocation fabricates failures.
- **Generated code:** codegen output (`*.g.dart`, `*.freezed.dart`) is often gitignored. CI must run codegen before analyze/test, and a check that reads generated output is vacuous when it is absent. After changing a generator annotation, regenerate before judging.
- **Zero findings needs a positive control.** A scan that returns nothing proves nothing until it is shown to find a planted violation. A diff-aware gate run on uncommitted work is vacuous.
- **Gate integrity:** never lower a coverage floor, loosen `analysis_options.yaml`, skip or delete a failing test, regenerate a golden to match a regression, or add a lint ignore to get green. Fix the cause, or get explicit approval naming the number. Thresholds only ratchet stricter.
- **CI parity:** derive the local gate list from the CI workflow files; path-filtered workflows must list the shared inputs they depend on (lockfile, analysis options, scripts); pin the SDK version in CI.

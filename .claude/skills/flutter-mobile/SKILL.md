---
name: flutter-mobile
description: This skill provides patterns and templates for Flutter 3.50.x / Dart 3.14.0 cross-platform mobile development. It should be activated when building Flutter screens, Riverpod providers, Freezed models, or widget tests.
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: Flutter, Dart, Riverpod, Flutter widget, Flutter app, mobile development, iOS, Android, cross-platform mobile, Flutter screen
  related-skills: riverpod-patterns, ui-standards-tokens
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

**NO FLUTTER UI WITHOUT RUNNING THE MFRI RISK SCORE FIRST — load `reference/mfri-scoring.md` before writing any screen**

# Flutter Mobile Development Skill

## Code Conventions
- Use **Riverpod** for state management
- Follow feature-first folder structure: `lib/features/<feature>/`
- Separate `data/`, `domain/`, `presentation/` layers (clean architecture)
- Use `freezed` for immutable models
- Firebase integration via `firebase_core`, `cloud_firestore`, `firebase_auth`

## SDK Baseline and Material Imports

Verified on Flutter 3.50.1 / Dart 3.14.0. Since Flutter 3.47, `package:flutter/material.dart` and `package:flutter/cupertino.dart` are deprecated: import `package:material_ui/material_ui.dart` (and `package:cupertino_ui/cupertino_ui.dart` when you use Cupertino widgets), pinned exactly (`material_ui: 1.11.1`, `cupertino_ui: 1.1.7`). A legacy import is a `deprecated_member_use` info, so `flutter analyze` is no longer zero-issue.

- Migrate existing code with `dart fix --apply --code=migrate_design_widgets`, then replace the `material_ui: any` it adds with the exact pin. Keep `uses-material-design: true`.
- `material_ui` holds its own copies of the classes, so a legacy `ThemeData`/`TextField` is a different type. Under a `material_ui` `MaterialApp`, a plugin still built on `flutter/material.dart` sees the default light theme and its text fields throw "No Material widget found". Wrap only that plugin's subtree in one host file: `MaterialUiCompatibilityBridge(child: legacy.Material(type: legacy.MaterialType.transparency, child: …))` with the legacy import prefixed `as legacy` and the `deprecated_member_use` ignores in that file only.
- Localizations: use `GlobalMaterialLocalizations.delegates` from `material_ui`; importing `flutter_localizations` unprefixed alongside it is an `ambiguous_import` error.
- go_router 18 needs the `material_ui` `MaterialApp.router`; under a legacy `MaterialApp` it falls back to non-Material page transitions.

## Quick Scaffold

New apps come from `/scaffold-flutter-app` (raw `flutter create` is blocked by a hook outside the scaffold command). Adding dependencies to an existing app:

```bash
# Exact pins: look each version up on pub.dev, then resolve them together
flutter pub add material_ui:1.11.1 flutter_riverpod:3.5.0 riverpod_annotation:4.0.8
flutter pub add freezed_annotation:3.1.0 json_annotation:4.12.0 go_router:18.1.4 dio:5.11.1
flutter pub add dev:riverpod_generator:4.0.10 dev:freezed:4.0.3 dev:json_serializable:6.15.2 dev:build_runner:2.17.1 dev:mocktail:1.0.5

# Run code generation (build_runner 2.16.2+ removed --delete-conflicting-outputs; passing it only prints a warning)
dart run build_runner build
```

Versions were the latest stable on pub.dev in November 2026 and resolve together on Flutter 3.50.1; re-check before pinning. Firebase pins: `flutter-templates.md`. Mockito codegen conflicts with this set: mockito 5.8.1 needs `build <5` while build_runner 2.17.1 needs `build 5.0.x`, so `pub get` fails; a project that generates mocks with mockito pins build_runner 2.16.2 (2.17.0 is retracted). mocktail needs no codegen and has no conflict.

## Melos Workspace Commands

In a Melos monorepo, run Melos through the workspace (a pinned root dev_dependency) at the workspace root:
- `dart run melos bootstrap` — installs all workspace dependencies (run at the root; a member-level `flutter pub get` resolves the same workspace, so root is the convention, not a hard requirement)
- `dart run melos run test:flutter --no-select` / `test:dart` — runs tests across the matching packages
- `dart run melos run build_runner --no-select` — runs code generation across all packages

Melos 7+ uses Dart pub workspaces (root `workspace:` list, `resolution: workspace` in every member, no `melos.yaml`). Setup, scripts, local-backend run targets and Gradle/isolate traps: [reference/flutter-build-and-workspace.md](reference/flutter-build-and-workspace.md).

## Shared Packages (monorepo pattern)

In a workspace, apps consume shared packages instead of publishing them. With Melos 7+ / pub workspaces, a member depends on another member by name with a normal version constraint; the workspace resolves it to the local copy, which must satisfy that constraint:
```yaml
resolution: workspace
dependencies:
  <shared_ui_package>: ^0.1.0   # must match the member's own `version:`; pin external packages exactly
```
Pre-workspace setups use `path: ../../packages/<name>` instead. Do NOT create a `lib/design_system/` directory in individual apps — shared UI components belong in the workspace's shared UI package.

## Dio HTTP Client (monorepo pattern)

In a Melos workspace, place the shared Dio instance with auth + retry interceptors in the shared core package's providers directory. Do NOT create new Dio instances in individual features.

## Before Writing Any UI Code

Before creating or modifying any widget, screen, or visual component:

1. **Run MFRI scoring** — read `reference/mfri-scoring.md` and complete the checkpoint template. Score < 3 = stop and redesign. Score 3-5 = add a validation milestone.
2. **Load `ui-standards-tokens` skill** — read `reference/ui-design-tokens.md` for spacing, color, typography, radius tokens
3. **Verify token awareness** — can you name the spacing token (`AppSpacing.md`), color approach (`Theme.of(context).colorScheme`), and typography pattern (`Theme.of(context).textTheme`) you will use?
4. If not → read the reference file before writing any widget code
5. For accessibility: read `reference/ui-accessibility-patterns.md` before adding interactive elements

## Process

**Feature phase order:** `mobile-design` checkpoint (MFRI) → plan → scaffold (new apps only: `/scaffold-flutter-app`) → TDD (failing widget/provider test first) → implement (steps below) → `/lint-design-system` → parallel reviewers (`riverpod-reviewer`, `flutter-security-expert`, `accessibility-auditor`) → Maestro flows in `<app>/.maestro/` ([reference/flutter-e2e-maestro.md](reference/flutter-e2e-maestro.md)) on iOS simulator and Android emulator.

**Plan gate:** no implementation until `docs/plans/YYYY-MM-DD-<feature>.md` exists and records the Riverpod provider type per piece of state (and why), the MFRI score, the exact file paths to create or modify, and the Firebase collections or packages it depends on. A stale or vague plan ("add a screen") is updated first.

1. **Read templates** - Use Read tool on `reference/flutter-templates.md` for all code templates (Freezed models, Riverpod providers, screens, GoRouter, tests, Firebase integration)
2. **Create feature structure** - Build `lib/features/<feature>/data/`, `domain/`, `presentation/` directories
3. **Define models** - Create Freezed data models in `data/models/` with Firestore serialization
4. **Build providers** - Create Riverpod notifiers with `@riverpod` annotation in `presentation/providers/`
5. **Design screens** - Build `ConsumerWidget` screens that watch `AsyncValue<T>` providers
6. **Run codegen** - Execute `dart run build_runner build`
7. **Write tests** - Create widget tests with `ProviderScope` overrides

## Key Patterns

| Pattern | Description |
|---------|-------------|
| `@freezed` models | Immutable data classes with `fromFirestore` factory |
| `@riverpod` providers | Code-generated state notifiers with `AsyncValue` |
| `ConsumerWidget` | Widgets that watch providers via `ref.watch()` |
| `AsyncValue.when()` | Handle loading/error/data states declaratively |
| Clean Architecture | Separate data/domain/presentation layers |
| GoRouter | Declarative routing with path parameters |
| Firebase Auth | Stream-based auth state with `authStateChanges()` |
| Firestore snapshots | Real-time data with `.snapshots()` streams |

## Modern Flutter Architecture (2025/2026)

For architecture patterns, accessibility, performance, UX, and premium polish guidelines:

Read [reference/flutter-architecture-patterns.md](reference/flutter-architecture-patterns.md) — Sealed classes, Result types, Riverpod AsyncNotifier
Read [reference/flutter-performance-ux.md](reference/flutter-performance-ux.md) — Accessibility, performance, haptic feedback, shimmer, animations
Read [reference/flutter-design-polish.md](reference/flutter-design-polish.md) — Glassmorphism, premium cards, dark/light themes, gradients
Read [reference/accessibility-audit-checklist.md](reference/accessibility-audit-checklist.md) — WCAG 2.2 AA Flutter checklist (used by `accessibility-auditor` agent)
Read [reference/flutter-security-hardening.md](reference/flutter-security-hardening.md) — Security hardening & privacy compliance (used by `flutter-security-expert` agent)
Read [reference/smart-dumb-widgets.md](reference/smart-dumb-widgets.md) — Smart (ConsumerWidget) vs Dumb (StatelessWidget) pattern, ref.watch/read placement rules, decision tree, Riverpod enforcement gates
Read [reference/flutter-use-case-layer.md](reference/flutter-use-case-layer.md) — When to add a use case, when not to, file location, example with two repositories, unit testing with fakes

### Task-triggered references (load only the row that matches your change)

| Changing… | Read |
|-----------|------|
| Router redirects, route gates, pre-`runApp` bootstrap, cold-start auth, sheets/dialogs that close by navigating, Android Back, deep links | [reference/flutter-navigation-and-auth-boot.md](reference/flutter-navigation-and-auth-boot.md) |
| API client, DTO/response model, base URL/env config, timeouts, failure mapping, client↔server contract parity | [reference/flutter-api-contract-parity.md](reference/flutter-api-contract-parity.md) |
| Offline write path: durable queue, retries, idempotency, background drain, attachment uploads, review checklist | [reference/flutter-offline-reliability.md](reference/flutter-offline-reliability.md) (queue model: [flutter-offline-sync.md](reference/flutter-offline-sync.md)) |
| Offline read path: queued-write display, temp ids, refresh/delete rules, schema migrations, account-bound cache, sign-out, backup exclusion | [reference/flutter-offline-cache-and-reads.md](reference/flutter-offline-cache-and-reads.md) |
| A test is green but untrusted, flaky suites, golden determinism, red gates, choosing validations per change type | [reference/flutter-testing-traps.md](reference/flutter-testing-traps.md) |
| Maestro flows, `integration_test` vs Maestro, device/simulator prep, deep-link and push testing | [reference/flutter-e2e-maestro.md](reference/flutter-e2e-maestro.md) |
| UI copy, ARB keys, plurals, second language, locale/date/currency formats | [reference/flutter-localization.md](reference/flutter-localization.md) |
| Workspace setup (Melos 7+, `dart run melos`), local-backend run targets, Gradle memory, signed upload URLs, `Isolate.run` | [reference/flutter-build-and-workspace.md](reference/flutter-build-and-workspace.md) |
| What may live in the app binary, debug/test gates, local DB encryption, fail-closed security settings | [reference/flutter-security-client-trust.md](reference/flutter-security-client-trust.md) |
| iOS/Android native config and toolchain floors (Gradle/AGP/Kotlin, SDK levels, iOS 15, SwiftPM), UIScene, cleartext/local-network, platform traps | [reference/flutter-platform-gotchas.md](reference/flutter-platform-gotchas.md) |

## Documentation Sources

Before generating code, consult these sources for current syntax and APIs:

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| Flutter / Dart | `Dart MCP server` | Latest Flutter widgets, Dart syntax, platform APIs |
| Riverpod | `Context7` MCP | Provider types, ref usage, AsyncValue patterns |
| Firebase Firestore | `Firebase MCP server` | Firestore operations, rules validation, auth flows |

## iOS Build, Run & Debug (XcodeBuildMCP)

For iOS-specific workflows, use the `xcodebuild` MCP server instead of raw CLI commands. It provides structured output, error parsing, and debugging that `flutter build ios` via Bash cannot.

### When to Use Which

| Task | Use This | Not This |
|------|----------|----------|
| Build iOS for simulator | `build_sim` (MCP) | `flutter build ios --simulator` (Bash) |
| Build + install + launch on simulator | `build_run_sim` (MCP) | `flutter run` (Bash) |
| Build for physical device | `build_device` (MCP) | `flutter build ios` (Bash) |
| Debug a crash or inspect state | `debug_attach_sim` → `debug_variables` (MCP) | Manual Xcode debugging |
| Capture runtime logs | `start_sim_log_cap` / `stop_sim_log_cap` (MCP) | Reading console manually |
| Check signing/scheme config | `show_build_settings` / `list_schemes` (MCP) | `xcodebuild -showBuildSettings` (Bash) |
| UI interaction (tap, swipe, type) | `tap`, `swipe`, `type_text` (MCP) | Not available via Bash |
| Build Android | `flutter build apk` (Bash) | N/A — XcodeBuildMCP is iOS/macOS only |

### iOS Debug Workflow

```
1. discover_projs → find ios/Runner.xcworkspace
2. list_schemes → identify the Runner scheme
3. build_run_sim → build, install, and launch on simulator
4. start_sim_log_cap → begin capturing logs
5. [reproduce the issue]
6. debug_attach_sim → attach LLDB debugger
7. debug_breakpoint_add → set breakpoint at suspect line
8. debug_variables / debug_stack → inspect state
9. stop_sim_log_cap → get captured logs
```

### Gotchas

- **Flutter projects**: The Xcode project is at `ios/Runner.xcworkspace`, not the project root
- **First build**: Run `flutter build ios` once first to generate the Xcode project and Pods
- **Signing**: `show_build_settings` exposes signing config — use this to diagnose code signing failures
- **Scheme name**: Flutter apps use the `Runner` scheme by default

## E2E Testing (Maestro MCP)

For cross-platform E2E testing, use the `maestro` MCP server. It runs test flows on both iOS simulator and Android emulator from natural language prompts.

### When to Use Which Test Tool

| Test Type | Tool | When |
|-----------|------|------|
| Widget/unit tests | `flutter test` (Bash) or `dart-mcp-server` `run_tests` | Every feature — fast, isolated, no device needed |
| iOS build + quick visual check | `xcodebuild` MCP (`build_run_sim`, `screenshot`) | Spot-checking a screen during development |
| Repeatable E2E flows | `maestro` MCP | Login, checkout, CRUD journeys — saved and rerunnable |
| Cross-platform E2E | `maestro` MCP | Same YAML flow runs on iOS simulator AND Android emulator |
| CI/CD regression suite | `maestro test <app>/.maestro/` (Bash) | Pre-merge gate in GitHub Actions |

Conventions, `integration_test` vs Maestro, and iOS/Android divergences: [reference/flutter-e2e-maestro.md](reference/flutter-e2e-maestro.md). **Tool rule:** Flutter Android/iOS UI/E2E is Maestro CLI/MCP only; browser automation is never used for it, and a missing Maestro/device is BLOCKED/NOT RUN ([`testing-tool-selection.md`](../../rules/testing-tool-selection.md)).

### E2E Workflow

```
1. Build and launch app (XcodeBuildMCP for iOS, flutter run for Android)
2. Describe the test flow in natural language
3. Claude generates YAML via Maestro MCP and runs it
4. Claude reports pass/fail per step
5. Save generated YAML to <app>/.maestro/<flow-name>.yaml for reuse
```

### Flow File Conventions

- Save flows to `.maestro/` inside each app (`<app>/.maestro/`)
- Name files by user journey: `login-flow.yaml`, `create-workout-flow.yaml`
- Use `appId` matching your app's bundle ID
- One flow per file — keep flows focused on a single journey

### Gotchas

- **App must be running**: Maestro interacts with a live app — build and launch first
- **Accessibility labels**: Maestro finds elements by text and accessibility labels — ensure `Semantics` widgets have labels
- **Timing**: Use `waitForAnimationToEnd` or `extendedWaitUntil` for slow transitions, not hardcoded sleeps
- **Cross-platform element names**: iOS and Android may render text differently — use `id` attributes for reliable cross-platform selectors

## Common Commands

```bash
flutter run                          # Run on connected device/emulator
flutter test                         # Run tests
flutter build apk --debug            # Build Android APK
flutter build ios --simulator        # Build iOS for the simulator (also generates the Xcode project)
flutter pub get                      # Install dependencies
flutter clean                        # Clean build artifacts
dart run build_runner build          # Run code generation
flutter analyze                      # Static analysis
```

## Error Handling

**Build runner fails**: Delete `.dart_tool/build/`, run `flutter clean`, retry codegen

**Missing generated files**: Ensure `part` directives match filename (e.g., `part 'user_model.g.dart';`)

**Provider not found**: Run `dart run build_runner build`, import generated `.g.dart` file

**Firestore Timestamp errors**: Use `(data['createdAt'] as Timestamp).toDate().toUtc()` (`toDate()` returns local time) in `fromFirestore`

**Hot reload breaks state**: Restart app fully when changing provider signatures

**AsyncValue stuck loading**: Check repository returns data, use `AsyncValue.guard()` to catch errors

## Hard Prohibitions

- No `Navigator.push` with raw strings — use GoRouter type-safe routes exclusively
- No returning null on async error — use `AsyncValue.error`, never null/empty fallbacks
- No `Color(0x...)` or `Colors.*` — use `Theme.of(context).colorScheme.*`
- No raw `EdgeInsets` with numeric values — use `AppSpacing.*` tokens
- No inline `TextStyle(fontSize: ...)` — use `Theme.of(context).textTheme.*`

## Sealed Types vs Boolean Flag Soup

Anti-pattern — boolean flags that create invalid states:
```dart
// ❌ 4 booleans = 16 possible states, most invalid
class LoadState {
  bool isLoading = false;
  bool isError = false;
  bool isEmpty = false;
  bool isSuccess = false;
  // isLoading=true AND isSuccess=true is invalid but representable
}
```

Correct — sealed class makes invalid states unrepresentable:
```dart
// ✅ Dart 3 sealed class — exactly 4 valid states
sealed class LoadState<T> {}

final class LoadingState<T> extends LoadState<T> {}
final class ErrorState<T> extends LoadState<T> {
  final Object error;
  final StackTrace? stack;
  ErrorState(this.error, [this.stack]);
}
final class EmptyState<T> extends LoadState<T> {}
final class SuccessState<T> extends LoadState<T> {
  final T data;
  SuccessState(this.data);
}

// Usage — exhaustive pattern matching (compiler enforces all cases):
Widget build(BuildContext context) {
  return switch (state) {
    LoadingState() => const CircularProgressIndicator(),
    ErrorState(:final error) => ErrorView(error: error), // app widget, not Flutter's ErrorWidget
    EmptyState() => const Text('No items'),
    SuccessState(:final data) => ItemList(data),
  };
}
```

Rule: Use sealed classes + `switch` expressions for any state with 3+ mutually exclusive cases. Applies to: UI state, network state, auth state, form state.

Applies to: Flutter 3.50.x / Dart 3.14.0 (sealed classes require Dart 3.0+)

## State Management Quick Reference

Library-agnostic comparison (for Riverpod-specific patterns, see `.claude/skills/riverpod-patterns/`):

| Library | Best for | Avoid when |
|---------|----------|-----------|
| **Riverpod** | Complex apps, DI, testability | Simple apps — overhead not justified |
| **Bloc** | Team environments, strict separation, audit-ready | Solo devs — too much boilerplate |
| **Provider** | Simple state, migration path from InheritedWidget | New projects — use Riverpod instead |
| **GetX** | Rapid prototyping | Production apps — couples UI to logic |
| **flutter_hooks** | Functional widget style, reusable stateful logic | Mixed teams unfamiliar with hooks |
| **setState** | Local ephemeral UI state (single widget) | Shared state across widgets |
| **InheritedWidget** | Framework/library authors only | App code — use Provider/Riverpod |

This workspace's stack uses **Riverpod** — see `.claude/skills/riverpod-patterns/` for detailed patterns.

## Post-Code Review

After writing Dart code, dispatch these reviewer agents:
- `riverpod-reviewer` — state management, provider types, AsyncValue handling
- `flutter-security-expert` — secure storage, certificate pinning, data protection
- `accessibility-auditor` — WCAG 2.2 AA, Semantics widgets, touch targets

Pre-submit checks (smart/dumb pattern):
- [ ] `shared_ui/` widgets extend `StatelessWidget` — zero ref/ConsumerWidget usage
- [ ] `ref.watch()` only in `ConsumerWidget` `build()`; `ref.read()` only in callbacks

## Templates Reference

For all code templates (pubspec.yaml, Freezed models, Riverpod providers, screen widgets, GoRouter config, widget tests, Firebase integration, repository patterns):

Read `reference/flutter-templates.md`

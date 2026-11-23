# Feature Development — Flutter Mobile

> **When to use**: Building a new screen, feature, or flow in the Flutter mobile app (iOS + Android)
> **Time estimate**: 2–5 hours per feature screen
> **Prerequisites**: Approved spec in `docs/specs/`, approved plan in `docs/plans/`

## Overview

Full Flutter mobile feature lifecycle from scaffold (if new app) through Riverpod state management to design-compliant, reviewed, tested screen. Uses Dart MCP, xcodebuild MCP, and Maestro MCP for testing.

---

## Phases

### Phase 0 — Mobile Design Thinking (MANDATORY before any UI work)

**Trigger**: Before building any new Flutter screen or feature with UI complexity
**Skill**: Load `mobile-design` skill (`skills/mobile-design/SKILL.md`)
**Action**: Complete the Mobile Checkpoint template

**Steps:**
1. Read `skills/mobile-design/reference/touch-psychology.md` — Fitts' Law, thumb zones, gesture design
2. Read `skills/mobile-design/reference/mobile-performance.md` — Flutter const patterns, Riverpod selectors, 60fps
3. If iOS-specific UI: read `skills/mobile-design/reference/platform-ios.md`
4. If Android-specific UI: read `skills/mobile-design/reference/platform-android.md`
5. Complete MFRI scoring (score formula from `mobile-design` SKILL.md)
6. Fill out Mobile Checkpoint — Platform, Framework, Files Read, MFRI Score, 3 principles, anti-patterns

**MFRI gate:**
- Score >= 6 -> proceed to Phase 1
- Score 3-5 -> proceed with performance + UX validation milestone added
- Score < 3 -> redesign before proceeding

**Gate**: Mobile Checkpoint complete; MFRI >= 3

---

### Phase 0.5 — Plan Verification (MANDATORY gate before any implementation)

**Trigger**: Before writing any code — applies to new features AND new screens in existing apps
**Rule**: No implementation starts without a plan file in `docs/plans/`

**Checkpoint:**
```
🔴 PLAN VERIFICATION

Does docs/plans/YYYY-MM-DD-<feature-name>.md exist?
  YES → Verify it contains: feature scope, affected files, provider types, screen list
  NO  → STOP — create the plan first (see steps below)
```

**If plan does NOT exist — create it now:**
1. Run `/brainstorm` if approach is unclear — ≥3 alternatives before committing
2. Run `feature-forge` skill to produce EARS-format requirements + Given/When/Then criteria
3. Write `docs/plans/YYYY-MM-DD-<feature-name>.md` with:
   - **Feature scope** — what screens, providers, models are involved
   - **Affected files** — list exact file paths that will be created or modified
   - **Provider type decisions** — which Riverpod provider type per piece of state (and why)
   - **MFRI score** — carry forward from Phase 0
   - **Dependencies** — external packages or Firebase collections needed
4. Get plan reviewed — use `/plan-review` for non-trivial features (>2 files changed)
5. Only after plan exists → proceed to Phase 1

**If plan EXISTS — verify it is current:**
- Scope matches what is actually being built today
- File paths are specific (not just "add a screen")
- If stale or vague → update it before proceeding

**Gate**: `docs/plans/YYYY-MM-DD-<feature-name>.md` exists AND contains specific file paths and provider decisions

---

### Phase 1 — Project Scaffold (new apps only)

**Trigger**: No existing Flutter project
**Command**: `/scaffold-flutter-app [app-name]`
**Source**: `commands/scaffold-flutter-app.md`
**11-step process**:
1. `flutter create` with org and platforms
2. Update `pubspec.yaml` with dependencies: Riverpod, Freezed, GoRouter, Firebase
3. Create clean architecture folder structure
4. Create Freezed model with Firestore factory
5. Create Riverpod provider (annotated)
6. Create `ConsumerWidget` screen with `AsyncValue.when()`
7. Configure GoRouter with routes
8. Set up `main.dart` with `ProviderScope` and Firebase
9. Add widget test
10. Run `build_runner`
11. Print summary

**Produces**: Production-ready Flutter app scaffold
**Gate**: `flutter test` passes, `flutter analyze` clean

---

### Phase 2 — Load Skill

**Trigger**: About to implement any Flutter feature
**Action**: Load `flutter-mobile` skill (`skills/flutter-mobile/SKILL.md`)
**Also load**: `riverpod-patterns` skill (`skills/riverpod-patterns/SKILL.md`)
**MCP servers** (from `skills/flutter-mobile/SKILL.md:87-105`):
- Dart MCP — `dart analyze`, format, test commands
- xcodebuild MCP — iOS simulator build + launch
- Firebase MCP — Firestore, Auth, FCM integration
- Context7 — Riverpod docs

**7-step implementation process** (from `skills/flutter-mobile/SKILL.md:48-151`):
1. Read templates for the feature type
2. Create feature folder structure
3. Define Freezed data models
4. Build Riverpod providers
5. Design screens with Material 3 / adaptive UI
6. Run `build_runner` for code generation
7. Write widget + integration tests

**Gate**: Skill and MCP loaded

---

### Phase 3 — TDD: Write Failing Test First

**Iron Law** (from `skills/test-driven-development/SKILL.md:16-21`): `NO IMPLEMENTATION WITHOUT A FAILING TEST FIRST`

**For Flutter** (from `skills/test-driven-development/references/tdd-patterns-flutter.md`):
- Widget tests with `WidgetTester` and `pumpWidget()`
- Provider tests with `ProviderContainer`
- Golden tests for visual regression

**Red-Green-Refactor**:
1. **Red** — Write widget test that asserts expected UI state, confirm `FAILED`
2. **Green** — Build minimum widget to pass
3. **Refactor** — Clean structure

**Gate**: Test fails for right reason (widget not found, not compile error)

---

### Phase 4 — Implement Feature

**Build order** (from `skills/flutter-mobile/SKILL.md`):
1. Freezed model → `lib/features/<name>/data/models/<name>_model.dart`
2. Repository interface → `lib/features/<name>/domain/repositories/<name>_repository.dart`
3. Repository implementation → `lib/features/<name>/data/repositories/`
   - Wrap all Firestore/HTTP calls in `ResilientNetworkService.execute()` (see `reference/flutter-network-resilience.md`)
   - Every catch block: `FirebaseCrashlytics.instance.log()` + `await recordError()` + `return Failure(e)` (see `reference/flutter-security-hardening.md` §Crashlytics)
4. Riverpod provider → `lib/features/<name>/presentation/providers/<name>_provider.dart`
   - For screens loading multiple data sources: use staged loading pattern (see `reference/flutter-performance-ux.md` §Staged Loading)
5. Screen → `lib/features/<name>/presentation/screens/<name>_screen.dart`
6. Widgets → `lib/features/<name>/presentation/widgets/`
7. Add route to GoRouter

**Riverpod provider selection** (from `skills/riverpod-patterns/SKILL.md`):

| Use case | Provider type |
|----------|--------------|
| Computed/derived data | `Provider` |
| One-shot async load | `FutureProvider` |
| Firestore stream | `StreamProvider` |
| Mutable state (simple) | `StateNotifierProvider` (legacy) / `NotifierProvider` |
| Mutable state (async) | `AsyncNotifierProvider` |

**AsyncValue.when() pattern** — always handle all 3 states:
```dart
ref.watch(myProvider).when(
  data: (data) => MyWidget(data: data),
  loading: () => const CircularProgressIndicator(),
  error: (err, stack) => ErrorWidget(err.toString()),
)
```

**Run after model changes**: `flutter pub run build_runner build --delete-conflicting-outputs`

**Gate**: `flutter test` passes, `flutter analyze` clean

---

### Phase 5 — Design System Compliance

**Trigger**: Screen implemented
**Skill**: Load `design-system` skill (`skills/design-system/SKILL.md`)
**Command**: `/lint-design-system`

**Flutter rules enforced** (from `.claude/hookify.design-no-hardcoded-colors-dart.local.md` and `.claude/hookify.design-no-raw-spacing-dart.local.md`):
- No `Color(0x...)` or `Colors.*` (except via `colorScheme`)
- No raw `EdgeInsets.all(16)` — use `AppSpacing.xs/sm/md/lg/xl/xxl`
- No inline `TextStyle` — use theme text styles
- Touch targets >= 48dp for all interactive elements

**Agent**: `ui-standards-expert` for Material 3 theming compliance
**Agent**: `accessibility-auditor` for WCAG 2.2 AA (Semantics widgets, focus, contrast, target size)

**Gate**: Zero design violations; no blocking WCAG 2.2 AA findings, manual checks listed (automated tests never prove conformance)

---

### Phase 6 — Review (run in parallel)

**Agent 1**: `riverpod-reviewer` (sonnet)
- Vibe: *"Wrong provider type = wrong lifecycle = subtle state bugs in prod"*
- Checks: provider type selection, `ref.watch` vs `ref.read` correctness, `AsyncValue.when()` completeness, lifecycle management

**Agent 2**: `flutter-security-expert` (sonnet)
- Vibe: *"Treats the device as hostile — secure storage first, GDPR always"*
- Checks: secure storage for credentials (not SharedPreferences), certificate pinning, data retention, GDPR compliance

**Agent 3**: `accessibility-auditor` (sonnet)
- Vibe: *"Defaults to non-compliant until proven otherwise — every user deserves access"*
- Checks: Semantics widgets, focus management, color contrast ratios, touch target sizes

**Gate**: Zero CRITICAL findings; HIGH findings resolved

---

### Phase 7 — E2E Testing

**Trigger**: Review findings resolved
**Tool**: Maestro MCP (via `settings.local.json` — `maestro` in allowed bash commands)

**Maestro test flow**:
```yaml
# .maestro/flows/<feature>_flow.yaml
appId: com.example.app
---
- launchApp
- tapOn: "Login Button"
- inputText:
    id: email_field
    text: test@example.com
- assertVisible: "Dashboard"
```

**Run**: `maestro test .maestro/flows/<feature>_flow.yaml`
**Gate**: E2E flow passes on both iOS simulator and Android emulator

---

### Phase 8 — Pre-Commit + PR

**Command**: `/validate-changes` → APPROVE required
**Command**: `/review-pr` → 6-role review
**Gate**: APPROVE + CRITICAL/HIGH resolved

---

## Quick Reference

| Phase | What to Run | Produces | Gate |
|-------|-------------|----------|------|
| 0 — Mobile Design | `mobile-design` skill + Mobile Checkpoint | MFRI score, checkpoint | MFRI >= 3 |
| 0.5 — Plan | `/brainstorm` + `feature-forge` → `docs/plans/` | Plan file with scope + file paths | Plan file exists |
| 1 — Scaffold | `/scaffold-flutter-app` | Full app skeleton | `flutter test` passes |
| 2 — Load skill | `flutter-mobile` + `riverpod-patterns` | Patterns + MCP | MCP connected |
| 3 — TDD | Write widget test | Failing test | `FAILED` status |
| 4 — Implement | model → provider → screen → route | Working screen | `flutter test` passes |
| 5 — Design | `/lint-design-system` + `ui-standards-expert` + `accessibility-auditor` | Compliance report | Zero violations |
| 6 — Review | `riverpod-reviewer` + `flutter-security-expert` + `accessibility-auditor` | Findings | Zero CRITICAL |
| 7 — E2E | Maestro test | E2E flow result | Both platforms pass |
| 8 — PR | `/validate-changes` + `/review-pr` | APPROVE + review | Gate passed |

---

## Common Pitfalls

- **`ref.read()` in `build()`** — causes stale data; use `ref.watch()` for reactive UI
- **`Colors.blue` instead of `colorScheme.primary`** — hookify will warn; breaks dark mode
- **Raw `EdgeInsets.all(16)` instead of `AppSpacing.md`** — design system violation
- **Not running `build_runner`** — Freezed models won't generate; `flutter test` will fail with missing files
- **Missing `AsyncValue.error` state** — user sees blank screen on failure; always handle all 3 states
- **SharedPreferences for credentials** — insecure; use `flutter_secure_storage` for anything sensitive
- **No network resilience** — bare Firestore/HTTP calls with no timeout or retry will fail silently under poor connectivity; wrap every outbound call in `ResilientNetworkService.execute()` (`reference/flutter-network-resilience.md`)
- **Silent catch blocks in repositories** — `catch (e) { return []; }` hides failures; every catch block must call `FirebaseCrashlytics.instance.log()` + `await recordError()` and return `Failure(e)` (`reference/flutter-security-hardening.md` §Crashlytics)
- **Single-shot loading for multi-source screens** — waiting for all data before showing anything causes blank screens; use staged loading to show high-priority data first (`reference/flutter-performance-ux.md` §Staged Loading)
- **No offline support on data-writing features** — if the feature creates, edits, or deletes data, it must save locally first and queue for background sync; never block the user on network availability (`reference/flutter-offline-sync.md`)

## Related Workflows

- [`ideation-to-spec.md`](ideation-to-spec.md) — spec and plan first
- [`ios-app-store-release.md`](ios-app-store-release.md) — release to App Store
- [`android-google-play-release.md`](android-google-play-release.md) — release to Google Play
- [`design-system-compliance.md`](design-system-compliance.md) — design system enforcement detail

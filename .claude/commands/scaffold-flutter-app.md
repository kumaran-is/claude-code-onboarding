---
description: Scaffold a new Flutter app with Riverpod, clean architecture, GoRouter, and Firebase setup
argument-hint: "[app name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold Flutter App

Create a new Flutter mobile application with the following:

**App name / theme:** $ARGUMENTS (default to "my_app" if not provided. If a theme is given like "fitness tracker" or "weather app", tailor the sample feature accordingly)

## Steps
Toolchain: Flutter 3.50.x / Dart 3.14.0 (verified on 3.50.1). Check `flutter --version` first; on an older SDK stop and report BLOCKED rather than pinning packages that need 3.47+.

1. Run `CC_SCAFFOLD=scaffold-flutter-app flutter create --org com.company --platforms ios,android <name>` (the `CC_SCAFFOLD=` prefix is the per-command authorization that `block-raw-scaffold.sh` requires; it is logged to `.git/claude-state/scaffold-audit.log`). The 3.50 template already imports `package:material_ui/material_ui.dart` and declares `material_ui: ^1.1.0`; replace that with the exact pin `material_ui: 1.11.1` and keep `uses-material-design: true`. Raise `environment: sdk:` to `^3.14.0` if the generated lower bound is older.
2. Update `pubspec.yaml` with exact pins for Riverpod 3, Freezed 4, go_router 18, Firebase and riverpod_lint (versions: `flutter-templates.md`; re-check pub.dev and resolve them together with `flutter pub get`). Material/Cupertino widgets come from `material_ui` / `cupertino_ui`, never `package:flutter/material.dart` or `package:flutter/cupertino.dart` (deprecated since 3.47); if any file still imports them, run `dart fix --apply --code=migrate_design_widgets` and replace the `material_ui: any` it adds with the exact pin.
3. Create `build.yaml` with riverpod_generator, json_serializable (snake_case), and freezed options; create `l10n.yaml` with arb-dir, template-arb-file, and output-class settings
4. Create `analysis_options.yaml` that includes `package:flutter_lints/flutter.yaml` and enables riverpod_lint as an analyzer plugin (top-level `plugins: riverpod_lint: <pin>`; riverpod_lint 3 no longer uses `custom_lint`)
5. Create clean architecture folder structure:
   - `assets/fonts/`, `assets/images/`, `assets/icons/`, `assets/lottie/`, `assets/raw/` — static assets (`raw/` for design references, optional at runtime)
   - `lib/main.dart` — one line only: `void main() => bootstrap(() => const App())`
   - `lib/bootstrap.dart` — async init, `FlutterError.onError` → Crashlytics, `Firebase.initializeApp`, `FirebaseAppCheck.activate`, `ProviderScope`
   - `lib/app.dart` — `ConsumerWidget` + `MaterialApp.router` (from `material_ui`) + theme wiring; `localizationsDelegates` come from `material_ui`'s `GlobalMaterialLocalizations.delegates`
   - `lib/core/di/providers.dart` — global `@Riverpod(keepAlive: true)` singletons (Dio, repositories)
   - `lib/core/error/app_exception.dart` — sealed exception hierarchy
   - `lib/core/error/error_handler.dart` — Crashlytics integration point
   - `lib/core/network/dio_provider.dart` + `lib/core/network/interceptors/` — Dio setup
   - `lib/core/storage/secure_storage_provider.dart` — `flutter_secure_storage` provider (sensitive data: tokens, keys)
   - `lib/core/storage/preferences_provider.dart` — `SharedPreferencesAsync` from `shared_preferences` (non-sensitive preferences only; structured cache and offline data use Drift, see `flutter-offline-sync.md`). `hive_flutter` is stale (last release 2021, SDK `<3.0.0`): do not add it
   - `lib/core/router/app_router.dart` + `route_names.dart` + `guards/` — GoRouter config
   - `lib/core/constants/` — app-wide constants (NO secrets — env vars only)
   - `lib/core/utils/` — logger, formatters, validators
   - `lib/core/extensions/` — Dart extension methods
   - `lib/core/l10n/` — Localisation .arb files and generated l10n delegates
   - `lib/design_system/tokens/` — one file per token family, ONE scale each (see flutter-templates.md): `color_tokens.dart` (raw palette, theme files only), `app_spacing.dart` (`AppSpacing`, `AppSize`), `app_radius.dart`, `app_elevation.dart`, `app_motion.dart` (`AppMotion.of` collapses durations under reduced motion)
   - `lib/design_system/typography/` — `font_families.dart`, `app_text_styles.dart`, `app_text_theme.dart`
   - `lib/design_system/theme/` — `app_theme.dart`, `app_color_scheme.dart`, `app_theme_extension.dart`, `theme_provider.dart`
   - `lib/design_system/components/` — buttons/, inputs/, cards/, dialogs/, loaders/: presentational `StatelessWidget`s whose line 1 is `// Tier: Atom|Molecule|Organism` (`design-system/reference/atomic-decision-tree.md`)
   - `DESIGN.md` at the app root — the skeleton from `design-system/reference/design-md-governance.md` §5, filled from the generated token files and marked `status: toolkit-default` (never invent brand values; the human approves or replaces them)
   - `lib/features/<feature>/data/datasources/` — remote + local datasources
   - `lib/features/<feature>/data/models/` — DTOs with `.g.dart` codegen
   - `lib/features/<feature>/data/repositories/` — repository impl
   - `lib/features/<feature>/domain/entities/` — pure Dart, Freezed
   - `lib/features/<feature>/domain/repositories/` — abstract interface
   - `lib/features/<feature>/domain/usecases/` — single-responsibility use cases
   - `lib/features/<feature>/domain/value_objects/` — validated primitives (Email, Password)
   - `lib/features/<feature>/presentation/providers/` — `@riverpod` notifier + Freezed state
   - `lib/features/<feature>/presentation/screens/` — screen widgets
   - `lib/features/<feature>/presentation/widgets/` — feature-scoped sub-widgets
   - `lib/features/common/` — shared widgets + providers reused across features
   - `test/unit/`, `test/widget/`, `test/integration/`, `test/helpers/` — test structure
6. Create sample Freezed entity (domain) + DTO (data) with `fromJson`
7. Create sample `@riverpod` notifier with Freezed sealed state
8. Create sample `ConsumerWidget` screen + `AsyncValue.when()`
9. Configure GoRouter as `@Riverpod(keepAlive: true)` with an auth redirect guard that reads state with `ref.read` and refreshes via `refreshListenable` (never `ref.watch`), redirects to a safe unauthenticated route — not `null` — while auth is unresolved, plus an auth-phase gate at the app root (see `flutter-navigation-and-auth-boot.md`)
10. Add a sample widget test using `ProviderScope` overrides
11. Run `dart run build_runner build` (build_runner 2.16.2+ ignores `--delete-conflicting-outputs` / `-d` with a "removed" warning)
12. Workspace wiring — `HOST=$(python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --find-host .)` (exit 1 = standalone; do not walk parents ad-hoc). Then `python3 …/discover_monorepo.py --root "$HOST"`. Only if `join.dart` is true: add the app path to that list if missing, add `resolution: workspace` to the app `pubspec.yaml`, reference shared packages by name (not `path:`), then run `dart run melos bootstrap` from the workspace root (Melos as a root `dev_dependency`). Melos 7+ has no `melos.yaml`; check the workspace's Melos version first. Do not add Nx. Outside a Dart workspace, skip this step. Details: `polyglot-monorepo/reference/discover-and-migrate.md`.
13. Verify — each with its OWN exit code (PASS / FAIL / BLOCKED):
    ```bash
    dart format --output=none --set-exit-if-changed . > /tmp/fmt.log 2>&1; echo "FORMAT EXIT:$?"
    flutter analyze > /tmp/analyze.log 2>&1; echo "ANALYZE EXIT:$?"
    flutter test > /tmp/test.log 2>&1; echo "TEST EXIT:$?"
    flutter build apk --debug > /tmp/apk.log 2>&1; echo "APK EXIT:$?"
    flutter build ios --simulator --debug > /tmp/ios.log 2>&1; echo "IOS SIM EXIT:$?"   # macOS + Xcode only; otherwise NOT RUN
    python3 .claude/scripts/check-design-system.py --root <app path> > /tmp/ds.log 2>&1; echo "DESIGN GATE EXIT:$?"; tail -5 /tmp/ds.log   # from the Claude project root
    ```
    `flutter analyze` must report zero issues: a leftover `package:flutter/material.dart` import is a `deprecated_member_use` info and fails the gate. Expected native floors from the 3.50 templates: Android Gradle 9.5.0, AGP 9.3.1, Kotlin 2.4.20, Java 17, minSdk 24, compile/target SDK 36; iOS deployment target 15.0 with Swift Package Manager enabled (see `flutter-platform-gotchas.md`).
    Device UI/E2E is Maestro only (`.claude/rules/testing-tool-selection.md`); without a booted emulator/simulator it is BLOCKED, never a browser substitute.
14. Print summary of created files, the verification results, next steps, and how to run

Use the flutter-mobile skill for patterns and templates.

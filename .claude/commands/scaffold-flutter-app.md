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
1. Run `CC_SCAFFOLD=scaffold-flutter-app flutter create --org com.company --platforms ios,android <name>` (the `CC_SCAFFOLD=` prefix is the per-command authorization that `block-raw-scaffold.sh` requires; it is logged to `.claude/state/scaffold-audit.log`)
2. Update `pubspec.yaml` with Riverpod 3.x, Freezed 3.x, GoRouter 15, Firebase, riverpod_lint (see flutter-templates.md for exact versions)
3. Create `build.yaml` with riverpod_generator, json_serializable (snake_case), and freezed options; create `l10n.yaml` with arb-dir, template-arb-file, and output-class settings
4. Create `analysis_options.yaml` with `custom_lint` plugin and `riverpod_lint` rules
5. Create clean architecture folder structure:
   - `assets/fonts/`, `assets/images/`, `assets/icons/`, `assets/lottie/`, `assets/raw/` — static assets (`raw/` for design references, optional at runtime)
   - `lib/main.dart` — one line only: `void main() => bootstrap(() => const App())`
   - `lib/bootstrap.dart` — async init, `FlutterError.onError` → Crashlytics, `Firebase.initializeApp`, `FirebaseAppCheck.activate`, `ProviderScope`
   - `lib/app.dart` — `ConsumerWidget` + `MaterialApp.router` + theme wiring
   - `lib/core/di/providers.dart` — global `@Riverpod(keepAlive: true)` singletons (Dio, repositories)
   - `lib/core/error/app_exception.dart` — sealed exception hierarchy
   - `lib/core/error/error_handler.dart` — Crashlytics integration point
   - `lib/core/network/dio_provider.dart` + `lib/core/network/interceptors/` — Dio setup
   - `lib/core/storage/secure_storage_provider.dart` — `flutter_secure_storage` provider (sensitive data: tokens, keys)
   - `lib/core/storage/hive_provider.dart` — `hive_flutter` provider (non-sensitive: preferences, cache)
   - `lib/core/router/app_router.dart` + `route_names.dart` + `guards/` — GoRouter config
   - `lib/core/constants/` — app-wide constants (NO secrets — env vars only)
   - `lib/core/utils/` — logger, formatters, validators
   - `lib/core/extensions/` — Dart extension methods
   - `lib/core/l10n/` — Localisation .arb files and generated l10n delegates
   - `lib/design_system/tokens/` — one file per token type (see flutter-templates.md)
   - `lib/design_system/typography/` — `font_families.dart`, `app_text_styles.dart`, `app_text_theme.dart`
   - `lib/design_system/theme/` — `app_theme.dart`, `app_color_scheme.dart`, `app_theme_extension.dart`, `theme_provider.dart`
   - `lib/design_system/components/` — buttons/, inputs/, cards/, dialogs/, loaders/
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
11. Run `dart run build_runner build --delete-conflicting-outputs`
12. Workspace wiring — only if the app is created inside an existing pub/Melos workspace (root `pubspec.yaml` with a `workspace:` list): add the app path to that list, add `resolution: workspace` to the app `pubspec.yaml`, reference shared packages by name, then run `melos bootstrap` from the workspace root. Never run `flutter pub get` inside the member. Melos 7+ has no `melos.yaml`; check the workspace's Melos version first. Outside a workspace, skip this step.
13. Verify — each with its OWN exit code (PASS / FAIL / BLOCKED):
    ```bash
    dart format --output=none --set-exit-if-changed . > /tmp/fmt.log 2>&1; echo "FORMAT EXIT:$?"
    flutter analyze > /tmp/analyze.log 2>&1; echo "ANALYZE EXIT:$?"
    flutter test > /tmp/test.log 2>&1; echo "TEST EXIT:$?"
    ```
    Device UI/E2E is Maestro only (`.claude/rules/testing-tool-selection.md`); without a booted emulator/simulator it is BLOCKED, never a browser substitute.
14. Print summary of created files, the verification results, next steps, and how to run

Use the flutter-mobile skill for patterns and templates.

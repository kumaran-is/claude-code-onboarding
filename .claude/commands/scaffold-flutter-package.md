---
description: Scaffold a new component or domain model into shared Flutter Melos packages (shared_ui or shared_core).
argument-hint: "shared_ui <ComponentName> | shared_core <ModelName>"
allowed-tools: Bash, Read, Write, Edit
---

# /scaffold-flutter-package

Scaffold a new component or domain model into shared Flutter packages within a Melos monorepo.

## Usage

```
/scaffold-flutter-package shared_ui <ComponentName>
/scaffold-flutter-package shared_core <ModelName>
```

## shared_ui — New UI Component

Target: `packages/shared_ui/lib/components/<component_name>/`

Structure:
```
packages/shared_ui/lib/components/<component_name>/
  <component_name>.dart          # Main widget (StatelessWidget — no Riverpod imports)
  index.dart                     # Barrel export
```

Template for `<component_name>.dart` (Material widgets come from `material_ui`, which the package must declare as an exact pin, e.g. `material_ui: 1.11.1`; `package:flutter/material.dart` is deprecated since Flutter 3.47):
```dart
// Tier: Atom
import 'package:material_ui/material_ui.dart';

class <ComponentName> extends StatelessWidget {
  const <ComponentName>({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) =>
      FilledButton(onPressed: onPressed, child: Text(label));
}
```

After creating, add to the package's main export file (e.g., `packages/shared_ui/lib/shared_ui.dart`):
```dart
export 'components/<component_name>/index.dart';
```

### Rules for shared_ui components

- Components in shared_ui are **dumb** — they receive all data via constructor args and emit events via `VoidCallback`/`ValueChanged<T>`. They extend `StatelessWidget` (or `StatefulWidget` for local UI state only) and contain zero `ref.watch()` / `ref.read()` calls.
- Add `// Tier: Atom | Molecule | Organism` as the first comment in the component file before all imports.
- Never put app-specific logic or service calls inside a shared_ui component.
- Never duplicate a component that already exists in shared_ui in an individual app.

## shared_core — New Domain Model

Target: `packages/shared_core/lib/models/<model_name>/`

Structure:
```
packages/shared_core/lib/models/<model_name>/
  <model_name>.dart              # Freezed model with json_serializable
  <model_name>.freezed.dart      # Generated — run dart run melos run build_runner
  <model_name>.g.dart            # Generated JSON serialization
  index.dart                     # Barrel export
```

Template for `<model_name>.dart`:
```dart
import 'package:freezed_annotation/freezed_annotation.dart';

part '<model_name>.freezed.dart';
part '<model_name>.g.dart';

@freezed
abstract class <ModelName> with _$<ModelName> {   // Freezed 3+: `abstract` (or `sealed` for unions) is required
  const factory <ModelName>({
    required String id,
    // add fields here
  }) = _<ModelName>;

  factory <ModelName>.fromJson(Map<String, Object?> json) =>
      _$<ModelName>FromJson(json);
}
```

After creating, add to the package's main export file (e.g., `packages/shared_core/lib/shared_core.dart`):
```dart
export 'models/<model_name>/index.dart';
```

### Rules for shared_core models

- Every domain model MUST use `@freezed` annotation — no plain mutable classes.
- Run `dart run melos run build_runner --no-select` (or equivalent) after adding a new model to generate `.freezed.dart` and `.g.dart` files.
- Never duplicate a domain model across individual apps — it belongs in shared_core.

## Post-Scaffold Steps

If the new package is a new workspace member, add its path to the root `pubspec.yaml` `workspace:` list, set `resolution: workspace` in its `pubspec.yaml`, and run `dart run melos bootstrap` from the workspace root (Melos 8.10.1 as a root dev_dependency, run with `dart run melos`; script layout in `flutter-build-and-workspace.md` §1). A member without `resolution: workspace`, a listed path with no pubspec, or two members pinning different versions of one package each fail `pub get` — fix the pubspec, never add an override to hide it.

```bash
# Regenerate all codegen (Freezed, Riverpod, json_serializable)
dart run melos run build_runner --no-select > /tmp/melos-build.log 2>&1; echo "BUILD_RUNNER EXIT:$?"

# Verify the new export resolves without errors (scripts must exist in the root pubspec; missing → BLOCKED)
dart run melos run analyze --no-select > /tmp/melos-analyze.log 2>&1; echo "ANALYZE EXIT:$?"
dart run melos run format:check --no-select > /tmp/melos-format.log 2>&1; echo "FORMAT EXIT:$?"
dart run melos run test:flutter --no-select > /tmp/melos-test-flutter.log 2>&1; echo "TEST FLUTTER EXIT:$?"   # shared_ui widget tests
dart run melos run test:dart --no-select > /tmp/melos-test-dart.log 2>&1; echo "TEST DART EXIT:$?"         # shared_core unit tests
```

$ARGUMENTS

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

After creating, add to the package's main export file (e.g., `packages/shared_ui/lib/shared_ui.dart`):
```dart
export 'components/<component_name>/index.dart';
```

### Rules for shared_ui components

- Components in shared_ui are **dumb** — they receive all data via constructor `input()` or constructor args and emit events via `VoidCallback`/`Function(T)`. Zero `inject()` or `ref.watch()` calls.
- Add `// Tier: Atom | Molecule | Organism` as the first comment in the component file before all imports.
- Never put app-specific logic or service calls inside a shared_ui component.
- Never duplicate a component that already exists in shared_ui in an individual app.

## shared_core — New Domain Model

Target: `packages/shared_core/lib/models/<model_name>/`

Structure:
```
packages/shared_core/lib/models/<model_name>/
  <model_name>.dart              # Freezed model with json_serializable
  <model_name>.freezed.dart      # Generated — run melos run build_runner
  <model_name>.g.dart            # Generated JSON serialization
  index.dart                     # Barrel export
```

Template for `<model_name>.dart`:
```dart
import 'package:freezed_annotation/freezed_annotation.dart';

part '<model_name>.freezed.dart';
part '<model_name>.g.dart';

@freezed
class <ModelName> with _$<ModelName> {
  const factory <ModelName>({
    required String id,
    // add fields here
  }) = _<ModelName>;

  factory <ModelName>.fromJson(Map<String, dynamic> json) =>
      _$<ModelName>FromJson(json);
}
```

After creating, add to the package's main export file (e.g., `packages/shared_core/lib/shared_core.dart`):
```dart
export 'models/<model_name>/index.dart';
```

### Rules for shared_core models

- Every domain model MUST use `@freezed` annotation — no plain mutable classes.
- Run `melos run build_runner` (or equivalent) after adding a new model to generate `.freezed.dart` and `.g.dart` files.
- Never duplicate a domain model across individual apps — it belongs in shared_core.

## Post-Scaffold Steps

If the new package is a new workspace member, add its path to the root `pubspec.yaml` `workspace:` list, set `resolution: workspace` in its `pubspec.yaml`, and run `melos bootstrap` from the workspace root — never `flutter pub get` inside the member (Melos 7+; verify against your Melos version).

```bash
# Regenerate all codegen (Freezed, Riverpod, json_serializable)
melos run build_runner

# Verify the new export resolves without errors
melos run analyze
```

$ARGUMENTS

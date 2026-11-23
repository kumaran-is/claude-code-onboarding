# Rive — Flutter Reference (rive 0.14.11)

Verified on Flutter 3.50.1 / Dart 3.14.0 with `rive: 0.14.11` (runtime `rive_native 0.1.11`). Every snippet below compiles with zero analyzer issues.

## Table of Contents
1. [The 0.14 runtime in one paragraph](#1-the-014-runtime-in-one-paragraph)
2. [Renderer selection](#2-renderer-selection)
3. [Widget pattern: RiveWidgetBuilder + Data Binding](#3-widget-pattern-rivewidgetbuilder--data-binding)
4. [Data Binding (replaces state machine inputs)](#4-data-binding-replaces-state-machine-inputs)
5. [Artboards and state machines](#5-artboards-and-state-machines)
6. [Preloading and sharing a File](#6-preloading-and-sharing-a-file)
7. [Errors](#7-errors)
8. [RiveNative.init()](#8-rivenativeinit)
9. [RivePanel — shared texture](#9-rivepanel--shared-texture)
10. [Testing](#10-testing)
11. [Checklist](#11-checklist)
12. [Removed APIs — migration table](#12-removed-apis--migration-table)

---

## 1. The 0.14 runtime in one paragraph

`rive` 0.14 is a new runtime on top of `rive_native` (C++ runtime + Rive renderer). The legacy runtime (`RiveAnimation`, `RiveFile.import`, `StateMachineController.fromArtboard`, `SMIBool`/`SMINumber`/`SMITrigger`) ended at `rive: 0.13.20` and does not exist in 0.14. In 0.14, **state machine inputs (`stateMachine.boolean/number/trigger`) are `@Deprecated`** ("Use Data Binding instead of state machine inputs"), and the 3.50.1 analyzer flags them. New code drives animations through a **view model instance** (Data Binding). Ask the designer to expose view-model properties in the `.riv`, not state machine inputs.

---

## 2. Renderer selection

The renderer is chosen per `File` through `riveFactory`:

| Factory | Use for |
|---|---|
| `Factory.rive` | Default. Vector-heavy files, gradients, meshes, bones, many instances |
| `Factory.flutter` | Simple glyph-level files drawn through Flutter's canvas (Impeller/Skia) |

Rendering differs on Impeller? Compare with `flutter run --no-enable-impeller` before filing an issue at github.com/rive-app/rive-flutter.

---

## 3. Widget pattern: RiveWidgetBuilder + Data Binding

- The **widget owns the `FileLoader`** and disposes it.
- **`RiveWidgetBuilder` owns the `RiveWidgetController` and the `ViewModelInstance`** it creates, and disposes them itself. Do not dispose them again.
- `RiveWidget.fit` takes rive's `Fit` (`Fit.contain`), not Flutter's `BoxFit`.

```dart
import 'package:material_ui/material_ui.dart';
import 'package:rive/rive.dart';

/// The .riv exposes a view model with a boolean property `isOn`.
class AnimatedToggle extends StatefulWidget {
  const AnimatedToggle({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  State<AnimatedToggle> createState() => _AnimatedToggleState();
}

class _AnimatedToggleState extends State<AnimatedToggle> {
  late final FileLoader _fileLoader = FileLoader.fromAsset(
    AnimationAssets.toggle,
    riveFactory: Factory.rive,
  );
  ViewModelInstanceBoolean? _isOn;

  @override
  void didUpdateWidget(AnimatedToggle oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.value != oldWidget.value) _isOn?.value = widget.value;
  }

  @override
  void dispose() {
    _isOn = null; // owned and disposed by RiveWidgetBuilder
    _fileLoader.dispose();
    super.dispose();
  }

  void _onLoaded(RiveLoaded state) {
    _isOn = state.viewModelInstance?.boolean('isOn');
    _isOn?.value = widget.value;
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    return Semantics(
      label: widget.label,
      toggled: widget.value,
      button: true,
      excludeSemantics: true,
      // excludeSemantics drops the InkWell's tap action: re-add it here,
      // or screen-reader users cannot activate the control.
      onTap: () => widget.onChanged(!widget.value),
      child: InkWell(
        onTap: () => widget.onChanged(!widget.value),
        child: SizedBox(
          width: 64,
          height: 48,
          // Reduced motion removes the movement, never the control.
          child: reduceMotion
              ? Switch(value: widget.value, onChanged: widget.onChanged)
              : RiveWidgetBuilder(
                  fileLoader: _fileLoader,
                  artboardSelector: ArtboardSelector.byName('Toggle'),
                  stateMachineSelector: StateMachineSelector.byName('Main'),
                  dataBind: DataBind.auto(),
                  onLoaded: _onLoaded,
                  onFailed: (error, stack) => FlutterError.reportError(
                    FlutterErrorDetails(
                      exception: error,
                      stack: stack,
                      library: 'rive',
                    ),
                  ),
                  builder: (context, state) => switch (state) {
                    RiveLoading() => const SizedBox.shrink(),
                    // Visible, working fallback: the switch still toggles.
                    RiveFailed() => Switch(
                        value: widget.value,
                        onChanged: widget.onChanged,
                      ),
                    RiveLoaded(:final controller) => RiveWidget(
                        controller: controller,
                        fit: Fit.contain,
                      ),
                  },
                ),
        ),
      ),
    );
  }
}
```

`RiveState` is sealed (`RiveLoading`, `RiveLoaded`, `RiveFailed`), so the `switch` is exhaustive. `RiveLoaded` carries `file`, `controller` and `viewModelInstance`.

---

## 4. Data Binding (replaces state machine inputs)

| Need | View-model property | Dart |
|---|---|---|
| On/off, loading flag | boolean | `vmi.boolean('isLoading')?.value = true` |
| Progress, level | number | `vmi.number('progress')?.value = 0.75` |
| One-shot event (success burst) | trigger | `vmi.trigger('onSuccess')?.trigger()` |
| Runtime text | string | `vmi.string('title')?.value = 'Done'` |
| Theme colour | color | `vmi.color('accent')?.value = scheme.primary` |
| Nested group | view model | `vmi.viewModel('header')?.number('count')` |

Other getters: `enumerator`, `image`, `font`, `list`, `artboard`. Each returns `null` when the property name or type does not match the file: treat `null` as a contract break with the designer and report it (`FlutterError.reportError`) instead of ignoring it.

- `DataBind.auto()` binds the artboard's default view-model instance. `DataBind.empty()` binds an empty instance; `BindByInstance(vmi)` binds one you created.
- Observe values coming back from the file with `property.addListener(callback)` and remove the listener in `dispose()`.
- Map app state to properties in one place (for example `didUpdateWidget` or a Riverpod listener), never per frame.

```dart
// Loading -> success -> error driven from a sealed app state.
void syncAuthState(ViewModelInstance vmi, AuthViewState state) {
  vmi.boolean('isLoading')?.value = state is AuthLoading;
  vmi.boolean('isError')?.value = state is AuthFailed;
  if (state is AuthSucceeded) vmi.trigger('onSuccess')?.trigger();
}
```

---

## 5. Artboards and state machines

Select them on the builder (or on `RiveWidgetController` if you build one yourself):

```dart
RiveWidgetBuilder(
  fileLoader: _fileLoader,
  artboardSelector: ArtboardSelector.byName('Welcome'), // or .byIndex / .byDefault
  stateMachineSelector: StateMachineSelector.byName('Main'),
  builder: (context, state) => ...,
)
```

Changing `artboardSelector`, `stateMachineSelector` or `dataBind` rebuilds the controller **without reloading the file**; changing the `fileLoader` instance reloads it. So keep one `FileLoader` per widget state (create it once, never in `build`). One `.riv` with several artboards is one asset load and shares embedded assets.

---

## 6. Preloading and sharing a File

Decode once, share the `File`, dispose it once.

```dart
import 'package:rive/rive.dart';

class RiveFileCache {
  final Map<String, File> _files = {};

  Future<void> preload(Iterable<String> assets) async {
    for (final asset in assets) {
      if (_files.containsKey(asset)) continue;
      final file = await File.asset(asset, riveFactory: Factory.rive);
      if (file == null) {
        throw StateError('Rive asset failed to decode: $asset');
      }
      _files[asset] = file;
    }
  }

  /// FileLoader.fromFile disposes the File it wraps when the loader is
  /// disposed, so widgets using a cached loader must NOT dispose it:
  /// the cache disposes every File once in [dispose].
  FileLoader loader(String asset) {
    final file = _files[asset];
    if (file == null) throw StateError('$asset was not preloaded');
    return FileLoader.fromFile(file, riveFactory: Factory.rive);
  }

  void dispose() {
    for (final file in _files.values) {
      file.dispose();
    }
    _files.clear();
  }
}
```

`File.decode(bytes, riveFactory: ...)`, `File.path(...)` and `File.url(...)` also exist; prefer bundled assets (no network at first paint).

---

## 7. Errors

`RiveWidgetBuilder` turns an `Exception` thrown while loading into `RiveFailed(error, stackTrace)` and calls `onFailed`. Always render a visible, working fallback for `RiveFailed` and report the error (`FlutterError.reportError` reaches `FlutterError.onError`, where Crashlytics or your logger is wired). Never let a failure become a blank box.

---

## 8. RiveNative.init()

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await RiveNative.init(); // loads the native runtime before the first Rive widget
  runApp(const App());
}
```

`RiveNative.init()` returns `Future<bool>` (`false` when the native library could not load); log and show fallbacks if it is `false`.

---

## 9. RivePanel — shared texture

Several Rive widgets on one screen can paint into one shared texture: wrap them in `RivePanel` and set `useSharedTexture: true` **on each `RiveWidget`** (the panel has no such flag; its parameters are `backgroundColor`, `renderResolution` and `child`).

```dart
RivePanel(
  child: Row(
    children: [
      for (final controller in controllers)
        Expanded(
          child: RiveWidget(controller: controller, useSharedTexture: true),
        ),
    ],
  ),
)
```

Profile before and after (DevTools raster thread, frame times) and keep it only if it measurably helps.

---

## 10. Testing

- Widget tests that **render** a `.riv` need the native library on the test host: run `dart run rive_native:setup --platform macos` (or `linux` / `windows`) once; it downloads the prebuilt library. Without it, test only the branches that do not touch the runtime.
- Always test: reduced motion keeps a working control; `RiveFailed` shows the fallback; the semantics node has the label, toggled state and a tap action.

```dart
testWidgets('reduced motion keeps a working, labelled control', (tester) async {
  var value = false;
  await tester.pumpWidget(
    StatefulBuilder(
      builder: (context, setState) => MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: Scaffold(
            body: AnimatedToggle(
              label: 'Notifications',
              value: value,
              onChanged: (v) => setState(() => value = v),
            ),
          ),
        ),
      ),
    ),
  );
  expect(find.byType(Switch), findsOneWidget);
  await tester.tap(find.byType(AnimatedToggle));
  await tester.pump();
  expect(value, isTrue);
  expect(
    tester.getSemantics(find.byType(AnimatedToggle)),
    matchesSemantics(
      label: 'Notifications',
      isButton: true,
      hasToggledState: true,
      isToggled: true,
      hasTapAction: true,
    ),
  );
});
```

---

## 11. Checklist

- [ ] `rive: 0.14.11` pinned; no `RiveAnimation`, `RiveFile`, `SMI*`, `StateMachineController` (legacy, removed)
- [ ] No `stateMachine.boolean/number/trigger` (deprecated): view-model properties via Data Binding
- [ ] `await RiveNative.init()` before `runApp`, result checked
- [ ] `FileLoader` created once per state and disposed; builder-owned controller/view model not disposed twice
- [ ] `RiveFailed` renders a working fallback and reports the error
- [ ] Reduced motion keeps the control and its meaning
- [ ] Semantics: label, state (`toggled`/`value`) and a tap action
- [ ] `.riv` < 500 KB; renderer chosen explicitly

---

## 12. Removed APIs — migration table

| Legacy (≤ 0.13.20) | 0.14.11 |
|---|---|
| `RiveAnimation.asset(path, stateMachines: [...])` | `RiveWidgetBuilder(fileLoader: FileLoader.fromAsset(path, riveFactory: ...), builder: ...)` + `RiveWidget(controller: ...)` |
| `RiveFile.import(bytes)` | `File.decode(bytes, riveFactory: ...)` |
| `StateMachineController.fromArtboard` + `artboard.addController` | `RiveWidgetController(file, artboardSelector: ..., stateMachineSelector: ...)` |
| `SMIBool` / `SMINumber` / `SMITrigger` | `ViewModelInstanceBoolean` / `Number` / `Trigger` via Data Binding |
| `controller.viewModelInstance?.getNumber('x')?.change(v)` | `vmi.number('x')?.value = v` |
| `fit: BoxFit.contain` | `fit: Fit.contain` |
| `RivePanel(useSharedTexture: true)` | `RivePanel(child: ...)` + `RiveWidget(useSharedTexture: true)` |

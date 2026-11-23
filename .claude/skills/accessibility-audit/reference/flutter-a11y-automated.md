# Flutter Automated Accessibility Testing

Automated accessibility tests for Flutter 3.50.x (Dart 3.14) with `flutter_test`. Verified on Flutter 3.50.1: every
test below compiles with zero analyzer issues and passes, and each guideline check was shown to fail on a planted
defect (unlabelled control, 30x30 target, low-contrast text). They complement the checklist at
`.claude/skills/flutter-mobile/reference/accessibility-audit-checklist.md`. Device checks (TalkBack, VoiceOver,
Switch Access) run on an emulator/simulator with Maestro and manually, never in a browser
(`.claude/rules/testing-tool-selection.md`).

Imports: since Flutter 3.47 `package:flutter/material.dart` is deprecated; app and test code import
`package:material_ui/material_ui.dart` (pin `material_ui: 1.11.1`). `find.byType(TextField)` then matches only
material_ui's `TextField`.

## 1. A shared test harness (light/dark, text scale, reduced motion)

Put this in `test/helpers/a11y_harness.dart` and reuse it in every screen's tests.

```dart
import 'package:material_ui/material_ui.dart';

/// Wraps [child] in the app theme with the accessibility settings under test.
Widget a11yHarness(
  Widget child, {
  ThemeData? light,
  ThemeData? dark,
  ThemeMode mode = ThemeMode.light,
  double textScale = 1,
  bool disableAnimations = false,
}) {
  return MaterialApp(
    theme: light ?? ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1565C0))),
    darkTheme: dark ??
        ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF1565C0),
            brightness: Brightness.dark,
          ),
        ),
    themeMode: mode,
    builder: (context, app) => MediaQuery(
      data: MediaQuery.of(context).copyWith(
        textScaler: TextScaler.linear(textScale),
        disableAnimations: disableAnimations,
      ),
      child: app!,
    ),
    home: Scaffold(body: Center(child: child)),
  );
}
```

## 2. Guideline matchers (`meetsGuideline`) — the primary automated gate

`flutter_test` ships four guidelines: `androidTapTargetGuideline` (48x48), `iOSTapTargetGuideline` (44x44),
`labeledTapTargetGuideline` (tap/long-press nodes need a label) and `textContrastGuideline` (WCAG minimum text
contrast, measured from rendered pixels).

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class OrderActions extends StatelessWidget {
  const OrderActions({super.key, required this.onDelete});

  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          tooltip: 'Delete order ORD-001',
          icon: const Icon(Icons.delete_outline),
          onPressed: onDelete,
        ),
        FilledButton(onPressed: () {}, child: const Text('Reorder')),
      ],
    );
  }
}

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('order actions meet the guidelines ($brightness)', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xFF1565C0),
              brightness: brightness,
            ),
          ),
          home: Scaffold(body: Center(child: OrderActions(onDelete: () {}))),
        ),
      );
      // Prove the theme swap took effect, or "dark" silently re-measures light.
      final context = tester.element(find.byType(OrderActions));
      expect(Theme.of(context).colorScheme.brightness, brightness);

      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      // An IconButton tooltip is exposed as the node's tooltip, not its label.
      expect(
        tester.getSemantics(find.byTooltip('Delete order ORD-001')),
        isSemantics(tooltip: 'Delete order ORD-001', isButton: true, hasTapAction: true),
      );
      handle.dispose(); // in the test body: addTearDown can fire too late
    });
  }
}
```

Rules:

- **Assert both tap-target guidelines.** A 44dp control passes iOS and fails Android.
- **Validate the probe before trusting a pass.** Run the same four guidelines on a deliberately bad tree (a 30x30
  unlabelled `GestureDetector`, light-grey text on white) and confirm they fail. A probe that matches nothing looks
  exactly like a clean screen.
- **A probe that does not compile or run is UNMEASURED, not clean.** Report it separately.
- **Contrast is theme-dependent: run light AND dark,** and assert the brightness as above.
- **Never nest `MergeSemantics` inside a tappable** (`InkWell`, a card with `onTap`, `ListTile`). The tappable already
  merges its descendants; a nested merge moves the text to a child node and `labeledTapTargetGuideline` fails with
  "expected tappable node to have semantic label".
- **These matchers are a floor.** They cannot see focus order, heading placement, double announcements or a
  load-bearing `ExcludeSemantics`; review those separately.
- Prefer `isSemantics(...)` for partial checks; `matchesSemantics(...)` compares every flag and breaks when the
  framework adds one.

## 3. Text scaling and reduced motion

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class SaveBar extends StatelessWidget {
  const SaveBar({super.key});

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      onPressed: () {},
      icon: const Icon(Icons.save),
      // Text that can wrap or ellipsize instead of overflowing at 200%.
      label: const Text('Save changes to your profile', maxLines: 2, overflow: TextOverflow.ellipsis),
    );
  }
}

void main() {
  testWidgets('no overflow at 200% text on a 320dp-wide screen', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, app) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(2)),
          child: app!,
        ),
        home: const Scaffold(body: Center(child: SaveBar())),
      ),
    );
    expect(tester.takeException(), isNull); // a RenderFlex overflow would be reported here
    final context = tester.element(find.byType(SaveBar));
    expect(MediaQuery.textScalerOf(context).scale(10), 20);
  });

  testWidgets('reduced motion: nothing keeps ticking', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, app) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: true),
          child: app!,
        ),
        home: Scaffold(
          body: Builder(
            builder: (context) => MediaQuery.disableAnimationsOf(context)
                ? const Icon(Icons.sync, semanticLabel: 'Syncing')
                : const CircularProgressIndicator(semanticsLabel: 'Syncing'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle(); // would time out if an animation looped
    expect(find.bySemanticsLabel('Syncing'), findsOneWidget);
  });
}
```

`textScaleFactor`, `MediaQuery.textScaleFactorOf` and `MediaQueryData(textScaleFactor:)` are deprecated: use
`textScaler`, `MediaQuery.textScalerOf` and `TextScaler.linear`. Android 14+ scales text non-linearly, so never
compute layout from a single scale factor; let text wrap.

## 4. Focus order and keyboard

```dart
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  testWidgets('tab order follows the visual order', (tester) async {
    final name = FocusNode(debugLabel: 'name');
    final email = FocusNode(debugLabel: 'email');
    addTearDown(name.dispose);
    addTearDown(email.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              TextField(focusNode: name, decoration: const InputDecoration(labelText: 'Name')),
              TextField(focusNode: email, decoration: const InputDecoration(labelText: 'Email')),
            ],
          ),
        ),
      ),
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    expect(name.hasPrimaryFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    expect(email.hasPrimaryFocus, isTrue);
  });
}
```

## 5. Announcements and live regions

`SemanticsService.announce` is deprecated (since 3.35): use `SemanticsService.sendAnnouncement(View.of(context), ...)`.
For status text that updates in place, prefer `Semantics(liveRegion: true)`.

```dart
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class DeleteButton extends StatelessWidget {
  const DeleteButton({super.key});

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: () => SemanticsService.sendAnnouncement(
        View.of(context),
        'Order deleted',
        Directionality.of(context),
      ),
      child: const Text('Delete'),
    );
  }
}

void main() {
  testWidgets('deleting announces the result', (tester) async {
    final announcements = <String>[];
    tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<dynamic>(
      SystemChannels.accessibility,
      (message) async {
        final event = message as Map<Object?, Object?>;
        if (event['type'] == 'announce') {
          final data = event['data']! as Map<Object?, Object?>;
          announcements.add(data['message']! as String);
        }
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger
          .setMockDecodedMessageHandler<dynamic>(SystemChannels.accessibility, null),
    );

    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: DeleteButton())));
    await tester.tap(find.text('Delete'));
    await tester.pump();
    expect(announcements, ['Order deleted']);
  });
}
```

## 6. Colour contrast of design tokens

`textContrastGuideline` measures rendered text. To check token pairs directly (for example every `on*`/surface pair
of the light and dark schemes), use `Color.computeLuminance()`; `Color.red/green/blue/value/opacity` are deprecated.

```dart
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

double contrastRatio(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

void main() {
  for (final brightness in Brightness.values) {
    test('scheme text roles meet 4.5:1 ($brightness)', () {
      final s = ColorScheme.fromSeed(seedColor: const Color(0xFF1565C0), brightness: brightness);
      final pairs = {
        'onSurface/surface': (s.onSurface, s.surface),
        'onSurfaceVariant/surface': (s.onSurfaceVariant, s.surface),
        'onPrimary/primary': (s.onPrimary, s.primary),
        'onError/error': (s.onError, s.error),
      };
      pairs.forEach((name, pair) {
        expect(contrastRatio(pair.$1, pair.$2), greaterThanOrEqualTo(4.5), reason: name);
      });
    });
  }
}
```

## Running

```bash
flutter test test/accessibility/      # widget-level checks
flutter analyze                       # 0 issues; catches deprecated a11y APIs
```

On-device screen-reader and switch-access flows: Maestro (`maestro test .maestro/`) on an Android emulator / iOS
simulator, plus the manual checklist. If no device is available, report BLOCKED, not PASS.

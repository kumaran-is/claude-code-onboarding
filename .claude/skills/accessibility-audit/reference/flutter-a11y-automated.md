# Flutter Automated Accessibility Testing

Automated accessibility testing patterns for Flutter 3.41.x using `flutter_test` SemanticsController. These patterns complement the existing checklist at `.claude/skills/flutter-mobile/reference/accessibility-audit-checklist.md`.

## 1. SemanticsController — Widget-Level Audit

```dart
// test/accessibility/order_card_a11y_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:your_app/widgets/order_card.dart';

void main() {
  group('OrderCard — Accessibility', () {
    testWidgets('all interactive elements have semantic labels', (tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: OrderCard(
              orderId: 'ORD-001',
              itemName: 'Widget Pro',
              onDelete: () {},
              onEdit: () {},
            ),
          ),
        ),
      );

      // Verify delete button has semantic label
      expect(
        tester.getSemantics(find.byTooltip('Delete order')),
        matchesSemantics(
          label: 'Delete order',
          isButton: true,
          hasTapAction: true,
        ),
      );

      // Verify edit button has semantic label
      expect(
        tester.getSemantics(find.byTooltip('Edit order')),
        matchesSemantics(
          label: 'Edit order',
          isButton: true,
          hasTapAction: true,
        ),
      );

      handle.dispose();
    });

    testWidgets('decorative images are excluded from semantics', (tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: OrderCard(orderId: 'ORD-001', itemName: 'Test')),
        ),
      );

      // Decorative image should not appear in semantic tree
      final semanticsTree = tester.getSemantics(find.byType(OrderCard));
      expect(semanticsTree.label, isNot(contains('decorative')));

      handle.dispose();
    });

    testWidgets('text scales correctly at 2x', (tester) async {
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(textScaler: TextScaler.linear(2.0)),
          child: MaterialApp(
            home: Scaffold(body: OrderCard(orderId: 'ORD-001', itemName: 'Widget')),
          ),
        ),
      );

      // Widget should render without overflow at 2x scale
      expect(tester.takeException(), isNull);
    });
  });
}
```

## 2. Touch Target Size Verification

```dart
// test/accessibility/touch_target_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const double minimumTouchTarget = 48.0; // WCAG 2.5.5 / Material 3

  group('Touch target sizes', () {
    testWidgets('all buttons meet 48dp minimum', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: YourScreenWidget()),
        ),
      );

      final buttons = find.byType(IconButton);
      for (final button in tester.widgetList(buttons)) {
        final renderBox = tester.renderObject(find.byWidget(button as Widget)) as RenderBox;
        final size = renderBox.size;
        expect(
          size.width,
          greaterThanOrEqualTo(minimumTouchTarget),
          reason: 'Button width ${size.width}dp is below 48dp minimum',
        );
        expect(
          size.height,
          greaterThanOrEqualTo(minimumTouchTarget),
          reason: 'Button height ${size.height}dp is below 48dp minimum',
        );
      }
    });
  });
}
```

> **Limit of the RenderBox check above:** it measures the widget's render box, not the semantics node. When a child owns the node (e.g. a `TextField`), wrapping it in a bigger box passes this test and the node stays small. Prefer the guideline matchers in 2b.

## 2b. Guideline Matchers (`meetsGuideline`)

`flutter_test` ships four accessibility guidelines (verified against the Flutter API docs): `androidTapTargetGuideline` (48x48), `iOSTapTargetGuideline` (44x44), `labeledTapTargetGuideline` (tap/long-press nodes need a label) and `textContrastGuideline` (WCAG minimum text contrast, measured from rendered pixels). Add them to each screen's own test file, reusing its harness:

```dart
testWidgets('meets accessibility guidelines', (tester) async {
  final handle = tester.ensureSemantics();
  await tester.pumpWidget(buildScreenHarness());
  await tester.pumpAndSettle();
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
  handle.dispose(); // in the test body: addTearDown can fire too late
});
```

Rules:

- **Assert both tap-target guidelines.** A 44dp control passes iOS and fails Android.
- **Validate the probe before trusting a pass.** Run the same four guidelines on a deliberately bad tree (a 12x12 unlabeled `GestureDetector`, light-grey text on white) and confirm they fail. A probe that matches nothing looks exactly like a clean screen.
- **A probe that does not compile or run is UNMEASURED, not clean.** Report it separately.
- **Contrast is theme-dependent: run light AND dark.** Assert the theme swap took effect, or the "dark" run silently re-measures light.
- **Never nest `MergeSemantics` inside a tappable** (`InkWell`, a card with `onTap`, `ListTile`). The tappable already merges its descendants; a nested merge moves the text to a child node and `labeledTapTargetGuideline` fails with "expected tappable node to have semantic label". Hoisting the wrapper outside turns the check green but leaves a redundant widget. When two candidate fixes both go green, try the combinations (outer only, inner only, both, neither) to find which one matters.
- **These matchers are a floor.** They cannot see focus order, heading placement, double announcements or a load-bearing `ExcludeSemantics`; review those separately.

## 3. Focus Order Testing

```dart
// test/accessibility/focus_order_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('form fields have logical focus order', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: CreateOrderForm())),
    );

    // Tab to first field
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();

    final firstFocused = tester.binding.focusManager.primaryFocus?.debugLabel;
    expect(firstFocused, contains('name')); // Name field first

    // Tab to next field
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();

    final secondFocused = tester.binding.focusManager.primaryFocus?.debugLabel;
    expect(secondFocused, contains('email')); // Email field second
  });
}
```

## 4. Screen Reader Announcement Testing

```dart
// test/accessibility/announcements_test.dart
import 'package:flutter/semantics.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('deleting item announces result to screen reader', (tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    final List<SemanticsEvent> events = [];

    // Listen for semantic announcements
    tester.binding.defaultBinaryMessenger.setMockMessageHandler(
      'flutter/accessibility',
      (message) async {
        // Capture announcement events
        return null;
      },
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: OrderListScreen())),
    );

    // Trigger delete
    await tester.tap(find.byTooltip('Delete order ORD-001'));
    await tester.pumpAndSettle();

    // Verify live region updated
    expect(
      find.bySemanticsLabel(RegExp(r'Order deleted')),
      findsOneWidget,
    );

    handle.dispose();
  });
}
```

## 5. Color Contrast — Flutter

Flutter does not have a built-in contrast checker. Use this helper in tests:

```dart
// test/helpers/contrast_checker.dart
import 'dart:math';
import 'package:flutter/material.dart';

class ContrastChecker {
  static double relativeLuminance(Color color) {
    double toLinear(double channel) {
      return channel <= 0.03928
          ? channel / 12.92
          : pow((channel + 0.055) / 1.055, 2.4).toDouble();
    }

    return 0.2126 * toLinear(color.red / 255) +
        0.7152 * toLinear(color.green / 255) +
        0.0722 * toLinear(color.blue / 255);
  }

  static double contrastRatio(Color foreground, Color background) {
    final l1 = relativeLuminance(foreground);
    final l2 = relativeLuminance(background);
    final lighter = max(l1, l2);
    final darker = min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  /// WCAG AA: 4.5:1 for normal text, 3:1 for large text (18sp+)
  static bool meetsWcagAA(Color fg, Color bg, {bool largeText = false}) {
    final ratio = contrastRatio(fg, bg);
    return largeText ? ratio >= 3.0 : ratio >= 4.5;
  }
}

// Usage in test
test('primary text meets WCAG AA contrast', () {
  const fg = Color(0xFF212121); // colorScheme.onSurface
  const bg = Color(0xFFFFFFFF); // colorScheme.surface
  expect(ContrastChecker.meetsWcagAA(fg, bg), isTrue);
});
```

## 6. Full Screen Audit Helper

```dart
// test/helpers/a11y_audit.dart
import 'package:flutter_test/flutter_test.dart';

/// Run after pumping a screen to check common a11y patterns
Future<void> runA11yAudit(WidgetTester tester) async {
  final handle = tester.ensureSemantics();

  // 1. Check all images have labels or are excluded
  final images = find.byType(Image);
  for (final image in tester.widgetList(images)) {
    // Images should either be in ExcludeSemantics or have a Semantics wrapper
    // This is a reminder check — automated validation via SemanticsController
  }

  // 2. Check no text overflow at 2x scale (run once with scaled text)
  // Call this from a separate testWidgets with MediaQuery override

  // 3. Verify semantic tree is not empty (confirms Semantics widgets present)
  final semantics = tester.getSemantics(find.byType(Scaffold).first);
  expect(semantics.childrenCount, greaterThan(0));

  handle.dispose();
}
```

## Running Flutter Accessibility Tests

```bash
# Run all a11y tests
flutter test test/accessibility/

# Run with verbose semantics output
flutter test test/accessibility/ --reporter=expanded

# Run integration tests on device (TalkBack / VoiceOver)
flutter drive --driver=test_driver/integration_test.dart --target=integration_test/a11y_test.dart
```

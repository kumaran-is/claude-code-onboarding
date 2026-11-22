# Flutter Localization — String Catalogue, Plurals, Parity

Read this before adding UI copy, a second language, an ARB key, a plural/gender string, a date/number/currency format, or a language switcher. It covers the string-catalogue layer (`flutter gen-l10n` + ARB). Visual resilience to long text (200% scale, RTL, wrapping) lives in [accessibility-audit-checklist.md](accessibility-audit-checklist.md) and [flutter-design-polish.md](flutter-design-polish.md).

Default choice: the SDK's `flutter_localizations` + `gen-l10n` + ARB files. They generate type-safe accessors from the same `intl` ecosystem used for dates and numbers. Avoid third-party `.tr()`-style string-key packages unless the project already standardises on one (they fragment the formatting story).

## 1. Setup

`pubspec.yaml`:

```yaml
dependencies:
  flutter_localizations:
    sdk: flutter
  intl: any   # version is pinned by the Flutter SDK constraint — do not override
flutter:
  generate: true
```

`l10n.yaml` (next to `pubspec.yaml`; options verified against docs.flutter.dev/ui/internationalization):

```yaml
arb-dir: lib/l10n
template-arb-file: app_en.arb
output-localization-file: app_localizations.dart
output-class: AppLocalizations
untranslated-messages-file: build/untranslated_messages.json   # report gaps instead of only printing them
```

Wire into the root app widget:

```dart
MaterialApp(
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  supportedLocales: AppLocalizations.supportedLocales,
  locale: selectedLocale, // null = follow the device locale
)
```

Generated files are build output: regenerate with `flutter gen-l10n` (or any build) after editing ARB files, and after merging branches. A stale generated file compiles against old strings.

## 2. ARB files

Template `app_en.arb` — every key has an `@key` description for translators:

```json
{
  "@@locale": "en",
  "signInButton": "Sign in",
  "@signInButton": { "description": "Primary action on the sign-in screen" },

  "openTaskCount": "{count, plural, =0{No open tasks} =1{1 open task} other{{count} open tasks}}",
  "@openTaskCount": {
    "description": "Open-task count on the dashboard",
    "placeholders": { "count": { "type": "int" } }
  },

  "statusLabel": "{status, select, open{Open} done{Done} other{Unknown}}",
  "@statusLabel": {
    "description": "Task status chip text",
    "placeholders": { "status": { "type": "String" } }
  }
}
```

Translation `app_es.arb` carries the same keys and the same `{placeholders}` (no `@` blocks needed). Call sites:

```dart
final l10n = AppLocalizations.of(context)!; // `!` only if nullable-getter is left at its default
Text(l10n.openTaskCount(openCount));
```

Plural/select rules (verified against the Flutter internationalization docs):

- Plurals and gender are ICU messages in the ARB, never Dart `if (count == 1)`. Other languages have more than "one vs many".
- `other` is required in both `plural` and `select`.
- Inside a branch, use the named placeholder (`other{{count} open tasks}`).
- Do not hand a `{count}`-style template to a widget that substitutes it with `replaceAll`: it cannot pluralize. When a shared component needs a count in its label, take a builder (`String Function(int count)`) and let the caller pass the generated plural method.
- **Test every branch** of a plural/select key (`=0`, `=1`, `other`). A test that only exercises `other` passes against a template that ignores the count.
- Do not assume positional argument order from the message text. After adding or reordering a placeholder, read the generated method signature in `app_localizations.dart` and assert the exact composed string in a test (several `String` placeholders can swap silently and still compile).

## 3. What counts as user-facing copy

Every user-facing string comes from the catalogue, including strings a user hears or sees only on some paths:

- `Semantics(label:)`, `semanticsLabel:`, `tooltip:`, and date/time picker `helpText`.
- Every field of a labels/strings object passed to a shared component: the shared component takes copy via its constructor, the app supplies `l10n.*`.
- Interpolated prose (`'Showing $n results, newest first'`). Judge the text outside `${...}`: prose needs a key with placeholders; pure composition (`'$day $time'`) does not.
- A constructor default (`defaultMessage: 'No internet connection'`) and an enum getter that returns English prose are literals too. Give the enum a method that takes the localisations object.
- Shared-package components read their own catalogue; they never hardcode copy.

Not translatable (exempt with a reason comment, e.g. `// ignore-l10n: brand name`): brand names, wire tokens, punctuation glyphs, debug-only fixtures.

Related rules:

- Never persist prose as a default value sent to an API. Send the enum's stable wire token; localise at display time.
- Server error text and agent/backend free text are not localised copy. Branch on a typed code or flag and render a localised key.
- A displayed number is converted once. Render a server-supplied display value verbatim instead of re-deriving it from a rounded stored value.
- A row that would show a label with no value shows a localised "not specified" value, never a blank.
- One term per concept per locale; pin terminology with a test that scans the ARB files.

## 4. Parity and coverage are different checks

- `gen-l10n` does not fail the build when a locale file lacks a key; it reports untranslated messages (printed, or written to `untranslated-messages-file`). In practice the missing key resolves to the template language at runtime — verify this once in your project by deleting a key and running the app. A green build therefore does not prove the second language is complete.
- **Parity:** every ARB file has the same key set and the same `{placeholder}` set as the template. Enforce with a unit test and/or CI step, and a write-time warning when the template ARB changes while sibling ARB files do not.
- **Coverage:** no literal user-facing strings remain in widget code (section 3). Parity can be green while coverage is red, because a string that never entered any catalogue is invisible to a parity check. Run a hardcoded-string check as a separate gate.
- Add every new key to **all** locale files in the same change. If the real translation is pending, add the template text and note it in the `@key` description so the gap stays visible.

Minimal parity test:

```dart
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

Set<String> _keys(Map<String, dynamic> arb) =>
    arb.keys.where((k) => !k.startsWith('@')).toSet();

void main() {
  test('every ARB file has the template keys', () {
    final dir = Directory('lib/l10n');
    final template =
        jsonDecode(File('lib/l10n/app_en.arb').readAsStringSync()) as Map<String, dynamic>;
    for (final f in dir.listSync().whereType<File>().where((f) => f.path.endsWith('.arb'))) {
      final arb = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      expect(_keys(arb), _keys(template), reason: f.path);
    }
  });
}
```

Extend it to compare `{placeholder}` sets per key if translations are edited by hand.

## 5. Formats and locale selection

- Format dates/numbers with `intl` (`DateFormat`, `NumberFormat`), never by string concatenation.
- A date pattern localises the names, not the order: `DateFormat('EEEE, MMM d', locale)` yields "lunes, oct 26" in Spanish. Build from locale skeletons (`DateFormat.yMMMEd(locale)`, `DateFormat.MMMd(locale)`) so the order follows the locale. Pin the order in a test.
- Currency is a policy decision made once: either follow the locale (`NumberFormat.simpleCurrency(locale: ...)`, which can pick a different symbol) or keep amounts locale-invariant. Route every amount through one formatter; never glue a `$` onto an interpolation.
- A default is not a choice. Only apply a saved locale if the user explicitly picked one; never persist the device locale or a server default as a user choice, or it overrides the device on every later launch (and survives sign-out). With no explicit choice, follow the device locale.
- When mapping a wire enum to display labels, enumerate the field's own type, not a similar-looking list elsewhere. A catch-all `_ =>` arm makes a mapping mistake silent, so prefer an exhaustive `switch` on a real enum, or test every real member (not a fabricated unknown value).
- Third-party SDK sheets (payments, pickers) localise too and may guess from the bare locale (e.g. a billing country). Pre-fill what you know and open each SDK sheet once per supported locale.
- Never bake translatable copy into an image asset.

## 6. Testing localised UI

```dart
testWidgets('shows the Spanish CTA', (tester) async {
  await tester.pumpWidget(const MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    locale: Locale('es'),
    home: SignInScreen(),
  ));
  await tester.pumpAndSettle();
  final l10n = AppLocalizations.of(tester.element(find.byType(SignInScreen)))!;
  expect(find.text(l10n.signInButton), findsOneWidget);
});
```

- Assert through the generated accessor, not a raw English literal.
- Layout tests need the longest translation, a phone-sized surface and a check that no overflow exception was thrown; widget tests use a test font, so confirm reflow on a device. See [flutter-testing-traps.md](flutter-testing-traps.md).
- A helper that expands a section by its English heading fails in another locale; key such helpers on the locale under test.
- Tests that pump a widget needing a shared-package catalogue must register that package's delegate, or the widget crashes with a null check on `of(context)`.
- Add a detector self-check to any hardcoded-string scanner: it must flag a known-bad sample and ignore a known-good one before its "0 findings" is trusted.

# i18n, l10n, RTL and Intl formatting (framework-neutral)

Applies to web (Angular, React) and, where noted, Flutter. Accessibility side (`lang`, translated accessible names) is WCAG 3.1.1/3.1.2 in `accessibility-audit/reference/wcag22-checklist.md`.

Status: Intl and CSS behaviour below is verified (Node 24 `Intl`, Tailwind 4.3.5 in Chromium). Library comparisons are RECOMMENDED PRACTICE, not measured.

## 1. Decide the model first (record it in an ADR)

| Option | How it works | Runtime language switch | Notes |
|---|---|---|---|
| Angular `@angular/localize` (`i18n` attributes, `$localize`) | Extracts messages (`ng extract-i18n`), builds **one bundle per locale** at compile time | No (reload to another locale's build) | Fastest at runtime, SSR-friendly, ICU plural/select built in; one deploy path per locale |
| Angular runtime library (for example Transloco) | Loads translation JSON at runtime | Yes | Extra runtime cost and lazy loading per scope. UNVERIFIED for v21 compatibility: check the library's peer range before adopting |
| React: FormatJS / `react-intl` | ICU MessageFormat, `<FormattedMessage>`, `useIntl()` | Yes | Same ICU syntax as Angular, so translators see one format |
| React: `i18next` + `react-i18next` | Key-based JSON, plugins for ICU | Yes | Large ecosystem; enable the ICU plugin if you need ICU plurals |
| Flutter | ARB files + `gen-l10n` with `intl` 0.20.3; Material/Cupertino delegates from `material_ui`'s `GlobalMaterialLocalizations.delegates` (importing `flutter_localizations` unprefixed alongside `material_ui` is an `ambiguous_import` error on 3.50) | Yes | Owned by `flutter-mobile`; same rules below apply |

## 2. Formatting rules (all stacks)

- Format with `Intl.*` (or the framework wrapper bound to the active locale: Angular pipes with `LOCALE_ID` after `registerLocaleData`, React `useIntl()`), never by hand.
- Store instants in UTC (ISO 8601); display in the user's time zone.
- Never concatenate translated fragments (`t('You have') + n + t('items')`). Use one ICU message with `plural`/`select`.

```ts
const n = 1234567.891;
new Intl.NumberFormat('de-DE').format(n);                                   // "1.234.567,891"
new Intl.NumberFormat('en-IN').format(n);                                   // "12,34,567.891"
new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(1234.5); // "￥1,235" (0 decimals for JPY)
new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' })
  .format(new Date('2026-01-15T10:00:00Z'));                                // "15 Jan 2026, 15:30"
new Intl.PluralRules('ar').select(3);                                       // "few" (Arabic has 6 plural categories)
new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-1, 'day');   // "yesterday"
```

ICU message (Angular `$localize`/`i18n`, FormatJS and i18next-ICU share this syntax):

```
{count, plural, =0 {No messages} one {# message} other {# messages}}
```

Currency: always pass the currency code from data; never infer it from the locale. Keep amounts as integer minor units or decimal strings until formatting.

## 3. RTL

- Set `lang` and `dir` on `<html>` per locale (`<html lang="ar" dir="rtl">`); set `lang` on inline foreign-language phrases.
- Use logical properties: CSS `margin-inline-start`, `padding-inline-end`, `inset-inline-start`, `text-align: start`, `border-start-start-radius`. Tailwind 4: `ms-*`/`me-*`, `ps-*`/`pe-*`, `start-*`/`end-*`, `text-start`, `border-s`, `rounded-s`. Verified: under `dir="rtl"`, `ms-4` computes to `margin-right: 16px`.
- Mirror directional icons (back arrows, chevrons) with `rtl:rotate-180`; never mirror logos, media controls or clocks.
- Flutter: `Directionality` follows the locale; use `EdgeInsetsDirectional` and `AlignmentDirectional`.
- Test one RTL locale in visual regression and one long-string locale (German, Finnish) for truncation at 200 % text.

## 4. Translate everything a user perceives

Visible text, `aria-label`, `alt`, `title`, page titles (route titles), live-region messages, validation messages and email/push templates. Do not build accessible names from untranslated keys.

## 5. Review checklist

- [ ] Model chosen and recorded (build-time vs runtime)
- [ ] No string concatenation of translated fragments; ICU plural/select used
- [ ] Dates, numbers, currency and relative time formatted with `Intl`/locale-bound pipes; UTC stored
- [ ] `<html lang dir>` set per locale; logical properties only (no `ml-*`/`mr-*`/`left-*` for layout direction)
- [ ] Accessible names and titles translated
- [ ] One RTL and one long-string locale checked

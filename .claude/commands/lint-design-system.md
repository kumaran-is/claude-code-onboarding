---
description: Scan files for design system violations — literal colours, arbitrary spacing, raw typography, inline styles, daisyUI 4 class names and small touch targets across Flutter and web (Angular, React)
allowed-tools: Bash, Glob, Grep, Read
---

# /lint-design-system

Scan changed files for design system violations. Detects hardcoded colors, raw spacing values, inline typography, and touch target issues.

## Process

### 1. Detect Stack

Determine which stack to scan:
- If `*.dart` files exist in `lib/` → run Flutter checks
- If `*.html`, `*.scss`, `*.ts` files exist in `src/app/` → run web checks (Angular); `*.tsx`/`*.jsx` in `src/` → web checks (React)
- If both → run both

### 2. Flutter Design Checks

Scan `lib/**/*.dart` (exclude `*.g.dart`, `*.freezed.dart`):

| Check | Pattern | Violation |
|---|---|---|
| Hardcoded colors | `Color(0x...)`, `Colors.xxx` | Use `Theme.of(context).colorScheme` tokens |
| Raw spacing | `EdgeInsets.all(N)`, `SizedBox(height: N)` with numeric literals | Use `AppSpacing.xs/sm/md/lg/xl/xxl` |
| Raw TextStyle | `TextStyle(fontSize: N)` | Use `Theme.of(context).textTheme` |
| Small touch targets | `SizedBox` with width/height < 48 wrapping `GestureDetector`/`InkWell` | 48×48 dp platform guideline (WCAG 2.5.8 AA floor is 24×24); assert with `androidTapTargetGuideline` in widget tests |

Commands to run:
```bash
# Hardcoded colors
grep -rn "Color(0x\|Colors\." lib/ --include="*.dart" | grep -v ".g.dart" | grep -v ".freezed.dart" | grep -v "test/" | grep -v "// ignore-design"

# Raw spacing
grep -rn "EdgeInsets\.\(all\|symmetric\|only\)([0-9]" lib/ --include="*.dart" | grep -v ".g.dart" | grep -v ".freezed.dart" | grep -v "// ignore-design"

# Raw TextStyle
grep -rn "TextStyle(fontSize:" lib/ --include="*.dart" | grep -v ".g.dart" | grep -v ".freezed.dart" | grep -v "// ignore-design"
```

### 3. Web Design Checks (Angular `src/app/`, React `src/**/*.tsx|jsx`)

These mirror the write-time hookify rules (`.claude/hookify.design-no-*-angular.local.md`). Tailwind 4 numeric utilities (`p-4`, `gap-2`, `mt-6`) **are** the spacing scale (multiples of `--spacing`), so they are allowed; arbitrary values are not.

| Check | Flags | Use instead |
|---|---|---|
| Literal colours | `bg-[#…]`, `text-[rgb(…)]`, `color: #…`, `background: oklch(…)` | daisyUI semantic tokens (`bg-primary`, `text-base-content`), `var(--color-…)` |
| Arbitrary spacing | `p-[13px]`, `gap-x-[1.1rem]`, `style="margin: 12px"` | The numeric scale (`p-3`) or daisyUI component spacing |
| Raw typography | `text-[14px]`, `font-[Arial]`, `font-size: 14px` | `text-sm`, `text-lg`, `font-sans` |
| Inline styles | `style="…"` in templates | Tailwind utilities |
| daisyUI 4 classes | `input-bordered`, `select-bordered`, `textarea-bordered`, `file-input-bordered`, `form-control`, `label-text`, `card-bordered`, `btn-group` | v5: `input`, `fieldset`/`fieldset-legend`, `label`, `card-border`, `join` (v4 names emit no CSS in daisyUI 5) |
| Spacing tokens that shadow `max-w-*` | `--spacing-xs/sm/md/lg/xl:` in `@theme` | The default `--spacing` multiplier; non-size names (`--spacing-gutter`) |
| Muted text below contrast floor | `text-base-content/10`…`/50` on text | `/60` minimum on `base-100`, `/70` on `base-200`/`base-300` (warn only; fine on decorative or disabled elements) |

Commands (POSIX ERE via `grep -E`, portable across BSD and GNU grep; no `\d`). Each excludes lines carrying `ignore-design: <reason>`; a bare `ignore-design` without a reason does not exempt:
```bash
# INC is an array: a string expanded as $INC stays ONE argument in zsh, so grep searches nothing (false PASS).
WEB="src/app"; INC=(--include='*.html' --include='*.ts' --include='*.tsx' --include='*.jsx' --include='*.css' --include='*.scss')
X='ignore-design:[[:space:]]*[^[:space:]]'
# Literal colours (token/theme stylesheets are where literals belong: exclude them)
grep -rnE "${INC[@]}" '(bg|text|border|ring|fill|stroke|from|via|to|outline)-\[(#|rgba?\(|hsla?\(|oklch\(|oklab\(|hwb\()|(background(-color)?|[^a-z-]color|border(-[a-z]+)?-color|fill|stroke|(background|border|outline)Color)[[:space:]]*:[[:space:]]*['"'"'"]?(#[0-9a-fA-F]{3,8}|(rgba?|hsla?|oklch|oklab|hwb)\()' "$WEB" \
  | grep -vE '(tokens?|theme)[^/]*\.s?css:|\.(spec|test)\.[jt]sx?:' | grep -vE "$X"
# Arbitrary spacing values and inline px spacing
grep -rnE "${INC[@]}" '(^|[[:space:]"'"'"'`:])-?([mp][xytrblse]?|gap(-[xy])?|space-[xy]|inset(-[xy])?)-\[[^]v][^]]*\]|style="[^"]*(margin|padding|gap)[a-z-]*[[:space:]]*:[[:space:]]*-?[0-9.]+px|style=\{\{[^}]*(margin|padding|gap)[A-Za-z]*[[:space:]]*:[[:space:]]*['"'"'"]?-?[0-9]' "$WEB" | grep -vE '\.(spec|test)\.[jt]sx?:' | grep -vE "$X"
# Raw typography
grep -rnE "${INC[@]}" 'text-\[[0-9.]+(px|rem|em)\]|font-\[[^]v][^]]*\]|font-size[[:space:]]*:[[:space:]]*[0-9]|fontSize[[:space:]]*:[[:space:]]*['"'"'"]?[0-9]' "$WEB" | grep -vE '(tokens?|theme)[^/]*\.s?css:|\.(spec|test)\.[jt]sx?:' | grep -vE "$X"
# Inline styles in templates
grep -rnE --include='*.html' 'style="' "$WEB" | grep -vE "$X"
# daisyUI 4 class names
grep -rnE "${INC[@]}" '\b(input|select|textarea|file-input)-bordered\b|\bform-control\b|\blabel-text(-alt)?\b|\bcard-bordered\b|\bbtn-group\b' "$WEB" | grep -vE "$X"
# Spacing tokens shadowing max-w-*
grep -rnE --include='*.css' --include='*.scss' -- '--spacing-(xs|sm|md|lg|xl|2xl)[[:space:]]*:' src/
# Muted text below the contrast floor (warn)
grep -rnE "${INC[@]}" 'text-base-content/(10|20|30|40|50)\b' "$WEB" | grep -vE "$X"
```
For React projects set `WEB=src`. Form-control labelling is an accessibility check, not a regex check: use `@angular-eslint/template` accessibility rules or `eslint-plugin-jsx-a11y-x` (React, ESLint 10), and the `accessibility-auditor` agent.

### 4. Report

Output results in this format:

```
## Design System Lint Report

### Flutter Violations
- [file:line] Hardcoded color: `Colors.blue` → use `Theme.of(context).colorScheme.primary`
- [file:line] Raw spacing: `EdgeInsets.all(16)` → use `EdgeInsets.all(AppSpacing.md)`

### Web Violations
- [file:line] Literal colour: `bg-[#3b82f6]` → use `bg-primary`
- [file:line] Arbitrary spacing: `p-[13px]` → use `p-3`
- [file:line] daisyUI 4 class: `input-bordered` → remove (v5 `input` is bordered by default)

### Summary
- Total violations: [N]
- Status: PASS (0 violations) / FAIL (1+ violations). Show each grep command's own exit status: 1 = no match, 2 = grep error (a broken pattern is FAIL, not PASS)
```

### 5. Exception Policy

Lines containing `// ignore-design: <reason>` or `<!-- ignore-design: <reason> -->` are excluded from checks. The reason is required; a bare marker does not exempt.

## Scope

- Flutter: `lib/` only (not `test/`, not generated files)
- Web: Angular `src/app/`, React `src/` (not `node_modules/`, not generated files, not `*.spec.ts`)
- Accessibility (labels, focus, contrast in context) is out of scope here: use the `accessibility-auditor` agent
- Run this before `/review-code` to catch design drift early

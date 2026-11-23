---
name: design-no-raw-typography-angular
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*(?:\.service\.ts|\.spec\.tsx?|\.test\.[jt]sx?|(?:^|/)[^/]*(?:tokens?|theme)[^/]*\.s?css)$)(?:.*(?:^|/)src/app/.*\.(?:html|scss|css|ts)|.*(?:^|/)src/(?!main/).*\.(?:css|scss)|.*\.(?:tsx|jsx))$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:\btext-\[[0-9.]+(?:px|rem|em)\]|\bfont-\[(?!var\()[^\]]+\]|\bleading-\[[0-9.]+(?:px|rem|em)?\]|font-size\s*:\s*['\"]?[0-9.]+|fontSize\s*:\s*['\"]?[0-9.]+)
---
Raw typography value detected in a web UI file (Angular `src/app/**`, React `*.tsx`/`*.jsx`, app stylesheets). Use Tailwind's typography scale or daisyUI text utilities:
- `text-sm`, `text-base`, `text-lg`, `text-xl` not `text-[14px]`
- `font-sans`, `font-mono` not `font-[Arial]`
- daisyUI component classes handle typography automatically
Reference: .claude/skills/angular-spa/reference/tailwind-v4-config.md
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.

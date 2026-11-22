---
name: design-no-raw-typography-angular
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: src/.*\.(html|scss|css|ts)$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:text-\[\d+px\]|text-\[\d+rem\]|text-\[\d+em\]|font-\[.*\]|font-size\s*:\s*\d+)
---
Raw typography value detected in Angular file. Use Tailwind's typography scale or daisyUI text utilities:
- `text-sm`, `text-base`, `text-lg`, `text-xl` not `text-[14px]`
- `font-sans`, `font-mono` not `font-[Arial]`
- daisyUI component classes handle typography automatically
Reference: .claude/skills/angular-spa/reference/tailwind-v4-config.md
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.

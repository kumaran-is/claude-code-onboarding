---
name: design-no-hex-angular
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: src/.*\.(html|scss|css|ts)$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:bg-\[#[0-9A-Fa-f]+\]|text-\[#[0-9A-Fa-f]+\]|border-\[#[0-9A-Fa-f]+\]|color\s*:\s*#[0-9A-Fa-f]{3,8}|\brgba?\s*\(|\bhsla?\s*\()
---
Hardcoded color detected in Angular file. Use daisyUI semantic tokens instead:
- `bg-primary` not `bg-[#3b82f6]`
- `text-base-content` not `text-[#333333]`
- `border-base-300` not `border-[#e5e7eb]`
- `text-primary` not `color: rgb(59, 130, 246)`
- `bg-accent` not `background: hsl(210, 80%, 55%)`
Reference: .claude/skills/angular-spa/reference/daisyui-v5-components.md lines 72-98
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.

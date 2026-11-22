---
name: design-no-raw-spacing-angular
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: src/.*\.html$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:\b(mt|mb|ml|mr|mx|my|pt|pb|pl|pr|px|py|gap|space-[xy])-\d+\b)
---
Raw numeric spacing utility detected in Angular template. Use semantic spacing tokens based on 4px base unit:
- `p-1` (4px), `p-2` (8px), `p-4` (16px), `p-6` (24px), `p-8` (32px), `p-12` (48px)
- Or use daisyUI component spacing which applies tokens automatically
Reference: .claude/skills/angular-spa/reference/angular-conventions.md lines 51-58
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.

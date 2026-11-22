---
name: design-no-raw-spacing-dart
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: lib/.*\.dart$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:EdgeInsets\.(all|symmetric|only|fromLTRB)\(\s*\d+\.?\d*\s*[,)]|SizedBox\(\s*(width|height)\s*:\s*\d+\.?\d*\s*[,)]|padding\s*:\s*\d+\.?\d*)
---
Raw spacing value detected in Dart file. Use semantic spacing tokens instead:
- `AppSpacing.xs` (4), `AppSpacing.sm` (8), `AppSpacing.md` (16), `AppSpacing.lg` (24), `AppSpacing.xl` (32), `AppSpacing.xxl` (48)
- Example: `EdgeInsets.all(AppSpacing.md)` not `EdgeInsets.all(16)`
Reference: .claude/skills/ui-standards-tokens/reference/ui-design-tokens.md lines 4-13
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.

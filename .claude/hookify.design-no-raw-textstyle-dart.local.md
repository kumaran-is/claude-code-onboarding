---
name: design-no-raw-textstyle-dart
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: lib/.*\.dart$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:TextStyle\(\s*fontSize\s*:)
---
Raw TextStyle with fontSize detected. Use theme typography instead:
- `Theme.of(context).textTheme.titleMedium`
- `Theme.of(context).textTheme.bodyLarge?.copyWith(...)` for customization
Reference: .claude/skills/ui-standards-tokens/reference/ui-design-tokens.md lines 53-63
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.

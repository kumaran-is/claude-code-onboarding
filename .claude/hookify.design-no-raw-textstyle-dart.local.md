---
name: design-no-raw-textstyle-dart
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*(?:_test|\.g|\.freezed|\.gr|\.mocks)\.dart$)(?!.*/(?:test|integration_test)/)(?!(?!.*/features/).*/(?:tokens|theme|themes|typography|foundations)/)(?!(?!.*/features/).*/(?:app_(?:colors?|color_scheme|theme\w*|spacing|radius|radii|motion|typography|text_styles?|text_theme|elevation|shadows?|icons|tokens|sizes|breakpoints)|\w+_tokens|\w+_theme(?:_extension)?)\.dart$).*(?:^|/)lib/.*\.dart$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:TextStyle\(\s*fontSize\s*:)
---
Raw TextStyle with fontSize detected. Use theme typography instead:
- `Theme.of(context).textTheme.titleMedium`
- `Theme.of(context).textTheme.bodyLarge?.copyWith(...)` for customization
Reference: .claude/skills/ui-standards-tokens/reference/ui-design-tokens.md lines 53-63
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.

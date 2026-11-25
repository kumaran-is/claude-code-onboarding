---
name: design-no-hardcoded-colors-dart
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*(?:_test|\.g|\.freezed|\.gr|\.mocks)\.dart$)(?!.*/(?:test|integration_test)/)(?!(?!.*/features/).*/(?:tokens|theme|themes|typography|foundations)/)(?!(?!.*/features/).*/(?:app_(?:colors?|color_scheme|theme\w*|spacing|radius|radii|motion|typography|text_styles?|text_theme|elevation|shadows?|icons|tokens|sizes|breakpoints)|\w+_tokens|\w+_theme(?:_extension)?)\.dart$).*(?:^|/)lib/.*\.dart$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:Color\(0x[0-9A-Fa-f]+\)|\bColors\.(?!transparent\b)\w+)
---
Hardcoded color detected in Dart file. Use theme tokens instead:
- `Theme.of(context).colorScheme.primary` (not `Colors.blue`)
- `Theme.of(context).colorScheme.onSurface` (not `Color(0xFF000000)`)
Reference: .claude/skills/ui-standards-tokens/reference/ui-design-tokens.md lines 41-51
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.

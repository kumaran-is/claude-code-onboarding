---
name: design-tier-comment-dart
enabled: true
event: file
action: warn
tool_matcher: Write
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*(?:_test|\.g|\.freezed|\.gr|\.mocks)\.dart$)(?!.*/(?:tokens|theme|themes|typography|foundations|utils|extensions|l10n|generated)/)(?!.*/index\.dart$)(?!.*/(?P<dir>[^/]+)/(?P=dir)\.dart$)(?:.*/packages/(?:shared_ui|ui|[a-z0-9_]+_ui)/lib/.+/[^/]+|.*/lib/design_system/components/.+)\.dart$
  - field: content
    operator: regex_match
    pattern: (?-i:\A(?!// Tier: (?:Atom|Molecule|Organism)[ \t]*(?:\r?\n|\Z)))
---
Shared-library Flutter widget without a line-1 tier marker. Line 1 must be exactly one of:
- `// Tier: Atom` (wraps one primitive, no child components)
- `// Tier: Molecule` (composes 2–3 atoms for one focused interaction)
- `// Tier: Organism` (composes molecules into a standalone section)
If none fits, it is a template or page: move it to `lib/features/<feature>/presentation/` (no tier comment there).
Decision tree: .claude/skills/design-system/reference/atomic-decision-tree.md
Checked on full-file writes only; `python3 .claude/scripts/check-design-system.py` checks edited files too (rule DS-TIER).

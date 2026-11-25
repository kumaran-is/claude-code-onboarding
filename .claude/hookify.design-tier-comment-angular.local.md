---
name: design-tier-comment-angular
enabled: true
event: file
action: warn
tool_matcher: Write
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*\.(?:spec|test|stories|model|models|types|tokens|constants|util|utils|d)\.ts$)(?!.*/index\.ts$).*(?:^|/)src/app/(?:.*/)?shared/components/.+\.ts$
  - field: content
    operator: regex_match
    pattern: (?-i:\A(?!// Tier: (?:Atom|Molecule|Organism)[ \t]*(?:\r?\n|\Z)))
---
Shared Angular component (`src/app/shared/components/`) without a line-1 tier marker. Line 1 must be exactly one of `// Tier: Atom`, `// Tier: Molecule`, `// Tier: Organism`.
- Templates, pages and route shells are not tiers: they live in `src/app/features/<feature>/`.
- Shared components are presentational: signal `input()`/`output()` only, no injected services, stores or HttpClient.
Decision tree: .claude/skills/design-system/reference/atomic-decision-tree.md
Checked on full-file writes only; `python3 .claude/scripts/check-design-system.py` checks edited files too (rule DS-TIER).

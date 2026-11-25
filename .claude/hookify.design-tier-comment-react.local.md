---
name: design-tier-comment-react
enabled: true
event: file
action: warn
tool_matcher: Write
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*\.(?:spec|test|stories)\.tsx$)(?!.*/index\.tsx$)(?!.*/[^/]*(?:provider|context)[^/]*\.tsx$).*(?:^|/)src/shared/ui/.+\.tsx$
  - field: content
    operator: regex_match
    pattern: (?-i:\A(?!// Tier: (?:Atom|Molecule|Organism)[ \t]*(?:\r?\n|\Z)))
---
Shared React component (`src/shared/ui/`) without a line-1 tier marker. Line 1 must be exactly one of `// Tier: Atom`, `// Tier: Molecule`, `// Tier: Organism`.
- Pages and route components are not tiers: they live in `src/features/<feature>/` or `src/app/`.
- `src/components/ui/` is CLI-owned shadcn code and is not tier-annotated.
Decision tree: .claude/skills/design-system/reference/atomic-decision-tree.md
Checked on full-file writes only; `python3 .claude/scripts/check-design-system.py` checks edited files too (rule DS-TIER).

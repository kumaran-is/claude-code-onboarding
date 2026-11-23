---
name: fixing-accessibility
description: Fix mode for known accessibility violations in web (Angular, React) or Flutter code — applies minimal, targeted fixes against the canonical WCAG 2.2 AA checklist in accessibility-audit. Use when a review, axe run or screen-reader test has already reported a specific violation to fix. For audits and test setup use accessibility-audit.
allowed-tools: Read, Grep, Glob, Bash, Edit
metadata:
  triggers: fix accessibility, fix a11y, fix aria, fix contrast, fix focus, fix target size, accessibility fix
  related-skills: accessibility-audit, angular-spa, flutter-mobile
  domain: accessibility
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-22"
---

## Iron Law

Fix only the reported violation. Never refactor unrelated code during an accessibility fix. Prefer native HTML or widget semantics over ARIA workarounds.

# Fixing Accessibility

Fix mode for the `accessibility-audit` skill. The checklist, severity scale, target-size policy and test tooling all live in `.claude/skills/accessibility-audit/reference/wcag22-checklist.md`. This skill does not keep a second copy.

## Process

1. Read the finding (file:line, criterion) and the file itself.
2. Look up the criterion row in the canonical checklist and apply its Web or Flutter column.
3. Make the smallest change that fixes it:
   - Prefer a native element (`<button>`, `<label for>`, `<dialog>` + `showModal()`, `fieldset/legend`) over ARIA.
   - Do not add ARIA when native semantics already solve the problem.
   - Do not migrate UI libraries unless asked.
4. Re-test the specific criterion: the axe rule in Playwright for web (tags include `wcag22aa`), the guideline matcher in `flutter test` for Flutter, or the manual check from checklist §4. Show the command and its output. If you cannot run it, mark it NOT RUN.
5. For a fresh review of the change, dispatch the `accessibility-auditor` agent (read-only).

## Output

```
## Accessibility Fix: <file>
| Finding | SC | Line | Change | Re-test (command → result, or NOT RUN) |
```

---
description: Review a file for WCAG 2.2 AA accessibility violations (web Angular/React or Flutter) and apply minimal fixes, or apply the accessibility checklist to all UI work in this session.
allowed-tools: Read, Grep, Glob, Bash, Edit, Agent
---

# /fixing-accessibility

Find accessibility violations and fix them with targeted, minimal changes.

## Usage

- `/fixing-accessibility <file>`: review the file, then fix its violations
- `/fixing-accessibility`: session mode. Apply the checklist to all UI work in this session

## Process

1. **Load skills.** Load `accessibility-audit` (canonical checklist: `reference/wcag22-checklist.md`) and `fixing-accessibility` (fix discipline).
2. **Detect the target.** `*.dart` means Flutter. `*.html`, `*.component.ts`, `*.tsx`, `*.jsx`, `*.css` or `*.scss` means web.
3. **File mode.** Dispatch the `accessibility-auditor` agent (read-only; it covers web and Flutter) on the file. Then fix each CRITICAL and HIGH finding following the `fixing-accessibility` skill. List MEDIUM and ADVISORY findings for the user to decide on.
4. **Session mode.** Before writing any interactive element, apply the checklist rows for: accessible names, keyboard access, focus (route change, dialogs, focus not obscured), forms and errors, contrast, and target size (≥ 24×24 CSS px is AA; 44 px web and 48 dp Android are house/platform recommendations), plus the 2.2 additions (dragging alternatives, redundant entry, accessible authentication).
5. **Re-test** with the tools for the target (`.claude/rules/testing-tool-selection.md`). Web: Playwright + `@axe-core/playwright` with `wcag22aa` included. Flutter: `flutter test` guideline matchers; Maestro for device flows. Show the command and its output, or mark the check NOT RUN.

## Report

```
## Accessibility: <file>
| Severity | SC | Line | Snippet | Fix | Re-test |
Manual checks M1–M7: PASS / FAIL / NOT RUN
Result: no automated violations; manual checks required | FINDINGS | BLOCK
```

Never report "compliant" from automated results.

## Related

- `accessibility-audit` skill: the checklist, automated test setup and CI
- `accessibility-auditor` agent: read-only WCAG 2.2 AA review with file:line findings
- `accessibility-audit` skill `SKILL.md` Process: the end-to-end audit (automated scan → manual checks → fix → CI gate)
- `/lint-design-system`: token compliance (run alongside for the full UI gate)

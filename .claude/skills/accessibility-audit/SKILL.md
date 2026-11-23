---
name: accessibility-audit
description: WCAG 2.2 AA accessibility audit and fix guidance for web (Angular 21.x, React) and Flutter 3.41.x. Use when auditing or fixing UI accessibility, identifying barriers, adding automated a11y tests, or preparing accessibility evidence. Owns the canonical WCAG 2.2 checklist. Covers axe-core with Playwright, flutter_test guidelines, Maestro flows for Flutter mobile, keyboard and screen-reader checks, contrast, target size, focus, forms, and CI integration.
allowed-tools: Read, Grep, Glob, Bash
agent: accessibility-auditor
context: fork
metadata:
  triggers: accessibility audit, WCAG, WCAG 2.2, a11y, screen reader, keyboard navigation, color contrast, focus management, ARIA, Semantics widget, axe, pa11y, target size, inclusive design, accessibility review
  related-skills: fixing-accessibility, angular-spa, flutter-mobile, ui-standards-tokens, design-system, browser-testing
  domain: quality
  role: specialist
  scope: review
  output-format: report
  source: "adapted from community (antigravity-awesome-skills)"
last-reviewed: "2026-11-22"
---

# Accessibility Audit

## Iron Law

Before auditing any component, READ the actual file first.
> Do not flag violations from memory. Verify at file:line and show evidence.

The bar is WCAG 2.2 Level AA for web (Angular, React) and Flutter (Android, iOS). The canonical checklist is [reference/wcag22-checklist.md](reference/wcag22-checklist.md). Every other skill, agent and workflow links to it.

**Automated results never prove conformance.** A clean axe or `flutter_test` run is reported as "no automated violations; manual checks required". The manual checks (keyboard walk, screen-reader smoke test, 200 %/400 % zoom, 320 px reflow) are listed in checklist §4. Each is recorded as PASS, FAIL or NOT RUN.

## When to Use

- Auditing web or Flutter UI against WCAG 2.2 AA
- Adding automated accessibility tests to a project or to CI
- Fixing reported accessibility barriers (fix discipline: `fixing-accessibility` skill)
- Reviewing a PR that adds or changes UI

## Do Not Use

- General design-token or theming review: use `design-system` and the `ui-standards-expert` agent
- Backend services with no UI

## Process

1. **Confirm scope:** the components, routes or screens and the target (web or Flutter mobile).
2. **Run the automated layer** (tool choice follows `.claude/rules/testing-tool-selection.md`):
   - Web: Playwright + `@axe-core/playwright` with the tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`.
   - Flutter: `flutter test` with the four guideline matchers. UI/E2E flows on a device use Maestro only, never a browser.
3. **Do the manual checks** in checklist §4. Anything not performed is NOT RUN.
4. **Map findings to criteria** with severity (CRITICAL / HIGH / MEDIUM / ADVISORY) and file:line.
5. **Give remediation** as exact code; prefer native semantics over ARIA.
6. **Re-test** each fix and show the command and its output.

## Reference Files

| File | Contents | Load when |
|------|----------|-----------|
| `reference/wcag22-checklist.md` | Canonical WCAG 2.2 AA checklist, target-size policy, manual checks, tooling by target | Every audit |
| `reference/angular-a11y-automated.md` | Playwright + axe, Vitest component checks, keyboard and dialog tests, forms markup (daisyUI 5) | Web automated tests (the patterns also apply to React) |
| `reference/flutter-a11y-automated.md` | `flutter_test` semantics and guideline matchers | Flutter automated tests |
| `reference/manual-testing-checklist.md` | Keyboard, screen-reader, zoom and reflow scripts | Manual session |
| `reference/cicd-integration.md` | GitHub Actions steps | CI integration |

Flutter widget-level depth: `.claude/skills/flutter-mobile/reference/accessibility-audit-checklist.md`, plus Flutter `Semantics` code patterns in `.claude/skills/ui-standards-tokens/reference/ui-accessibility-patterns.md`.

## Output Format

```markdown
## Accessibility Audit — [Component/Page/Screen]
Target: web (Angular|React) | Flutter (Android|iOS)

### Findings
- **[A11Y-001] [CRITICAL|HIGH|MEDIUM|ADVISORY]** [short description]
  - File: `path/to/file:line`
  - WCAG: [criterion, e.g. 2.5.8 Target Size (Minimum)]  (or "house standard" / "best practice")
  - Issue: [what is wrong]
  - Fix: [exact code]

### Evidence
- Automated: [command] → [exit code, violation ids], or NOT RUN
- Manual M1–M7: PASS / FAIL / NOT RUN for each

### Result
No automated violations; manual checks required | FINDINGS (N critical, N high) | BLOCK
```

Never write "WCAG compliant" or "conformant" on the strength of automated output.

## Agents

- `accessibility-auditor`: the one read-only WCAG 2.2 reviewer for web and Flutter
- `ui-standards-expert`: tokens, theming and consistency (no accessibility verdicts)

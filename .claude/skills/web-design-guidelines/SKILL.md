---
name: web-design-guidelines
description: "Audit UI code against Vercel's Web Interface Guidelines — fetches live rules, reads specified files, outputs findings as file:line violations. Use when asked to review UI, audit design, review UX, or verify a component against web interface standards. Complements /lint-design-system (tokens) and accessibility-auditor (WCAG) with web interaction pattern compliance."
allowed-tools: Read, Glob, Grep, WebFetch
metadata:
  triggers: review UI, audit design, review UX, web interface guidelines, Vercel guidelines, UI compliance, design audit, UX review, check my site, check my component
  related-skills: frontend-design, design-system, angular-spa, angular-ui-patterns, accessibility-audit
  domain: frontend
  role: specialist
  scope: review
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law

**FETCH THE LIVE GUIDELINES BEFORE REVIEWING ANY FILE. Never apply remembered or assumed rules — always fetch fresh from the source URL. If WebFetch fails, report the failure and do not proceed with guessed rules.**

# Web Interface Guidelines Review

> Audits UI code against Vercel's Web Interface Guidelines. Outputs structured `file:line` findings.

## When to Use This Skill

Load this skill when the user asks to:
- "Review my UI"
- "Check accessibility"
- "Audit design"
- "Review UX"
- "Check my site/component against guidelines"
- Run a design compliance check before a PR

## How It Works

1. **Fetch guidelines** — retrieve the latest rules from the source URL using WebFetch
2. **Read files** — read the specified files (or ask user which files/pattern to review)
3. **Apply rules** — check all files against every rule in the fetched guidelines
4. **Output findings** — report violations in `file:line: [rule violated]` format

## Guidelines Source

Fetch fresh guidelines before each review session:

```
https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md
```

Use `WebFetch` to retrieve the latest rules. The fetched content contains all rules and output format instructions. **Do not cache or remember rules across sessions** — always fetch fresh.

## Usage

### When user provides files or a path pattern:
1. Fetch guidelines from source URL
2. Read the specified files
3. Apply all rules from the fetched guidelines
4. Output findings using the format specified in the guidelines

### When no files are specified:
Ask the user: "Which files or directories should I review? (e.g. `src/app/features/dashboard/` or `*.component.html`)"

### Output format
Follow the format specified in the fetched guidelines exactly. Default structure:
```
file:line — [Rule name]: [Description of violation]
```

Example:
```
dashboard.component.html:34 — Empty State: No empty state defined for zero-data condition
dashboard.component.html:67 — Focus Management: Interactive element lacks visible focus indicator
order-list.component.ts:89 — Loading State: Async operation has no loading feedback
```

## Failure Handling

If `WebFetch` fails to retrieve the guidelines URL:
1. Report: "Could not fetch Web Interface Guidelines from source URL. Fetch failed: [error]"
2. Do NOT proceed with guessed or remembered rules
3. Suggest: "Try again, or check network access to raw.githubusercontent.com"

**Never fabricate rule findings if the fetch fails.**

## How This Fits the Review Stack

This skill is the third layer of UI review — run all three for complete coverage:

| Layer | Tool | What It Catches |
|---|---|---|
| **Layer 1 — Design tokens** | `/lint-design-system` | Hardcoded colors, raw spacing, inline typography, touch target violations |
| **Layer 2 — WCAG 2.2 AA accessibility** | `accessibility-auditor` agent | Contrast, names, keyboard, focus, target size, forms (verdicts on accessibility come only from this layer) |
| **Layer 3 — Web interface patterns** | `web-design-guidelines` (this skill) | Loading states, empty states, error handling, interaction patterns, focus management |

## Related Skills

- `frontend-design` — run BEFORE this skill to establish aesthetic direction and DFII score
- `design-system` — token compliance enforcement (Angular + Flutter)
- `angular-ui-patterns` — Angular-specific loading/error/empty state doctrine
- `accessibility-audit` — canonical WCAG 2.2 AA checklist (accessibility requests go there, not to this skill)

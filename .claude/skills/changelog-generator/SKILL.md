---
name: changelog-generator
description: This skill should be used when preparing releases, writing app store updates, or maintaining a CHANGELOG.md. It parses conventional commits and outputs polished release notes.
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: changelog, release notes, CHANGELOG.md, git log, release preparation, conventional commits, app store update, version release
  related-skills: pr-review, documentation-generation, verification-before-completion
  domain: workflow
  role: specialist
  scope: analysis
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law

Never generate a changelog without reading actual git history or diff; always base entries on verified commits, not assumptions.

# Changelog Generator Skill

Transform git commit history into polished, user-friendly changelogs. Works with any tech stack by auto-detecting the project structure.

## High-Level Process

1. **Detect project structure** - Scan repo for platform markers (Java, Node, Python, Angular, Flutter, etc.) and build a platform label map
2. **Determine commit range** - Use tags, dates, or commit count. Ask user if unclear
3. **Extract commits** - Pull structured log: `git log "$LAST_TAG"..HEAD --pretty=format:"%h|%ai|%an|%s" --no-merges`
4. **Categorize** - Map conventional commit prefixes to user-facing categories (feat -> New Features, fix -> Bug Fixes, perf -> Performance). Skip refactor/test/chore/ci/build/style
5. **Rewrite** - Translate technical commits to user-friendly language. Lead with user benefit, strip jargon
6. **Assemble** - Format changelog for the target destination
7. **Output** - Write to CHANGELOG.md, GitHub Release, App Store, Slack, or internal format

For detailed step-by-step workflow (project detection scripts, commit parsing, categorization table, rewriting rules, assembly format) -> Read [reference/changelog-workflow.md](reference/changelog-workflow.md)

For output format examples (App Store, Keep a Changelog, internal/technical, Slack/email) -> Read [reference/changelog-workflow.md](reference/changelog-workflow.md)

## Key Rules

- Read `CLAUDE.md` first if it exists -- it describes the project's tech stack and conventions
- Always include: `feat:`, `fix:`, `perf:`, `security:`, `BREAKING CHANGE`
- Always skip: `refactor:`, `test:`, `chore:`, `ci:`, `build:`, `style:`
- Non-conventional commits: categorize by intent, include under "Improvements" if ambiguous
- Multi-platform repos: prefix entries with platform label (e.g., **Mobile App**, **Web App**, **Backend**)
- Single-platform repos: skip the label entirely

## Output Destinations

| Destination | Action |
|-------------|--------|
| `CHANGELOG.md` | Prepend to existing file (newest on top) |
| GitHub Release | Output as Markdown block ready to paste |
| App Store | Shorter format, no emoji, plain language, max 4000 chars |
| Slack / Email | Condensed summary with highlights only |
| Internal | Include technical details and commit hashes |

## Automation Tip

Suggest to the user: add a `pre-release` hook or CI step that runs this skill automatically when tagging a new version. Pair with the `/changelog` command for quick manual runs.

For tool configuration (`cliff.toml`, `release.config.js`, GitHub Actions release workflow) -> Read [reference/changelog-automation-tools.md](reference/changelog-automation-tools.md)

## Anti-Patterns

> ❌ **Don't invent entries.** Never add changelog items that have no backing commit. Every line must map to a real commit hash.

> ❌ **Don't expose internals.** "Refactored UserService to use factory pattern" is not user-facing. Rewrite as the benefit, or skip it.

> ❌ **Don't copy commit messages verbatim.** Raw messages like `fix: typo in auth handler` become noise. Rewrite to user-facing language or drop it.

> ❌ **Don't include chore/ci/test/build commits** in user-facing changelogs. They belong in internal/technical format only.

## Error Handling

**Empty git log (no commits in range)**:
```bash
git log "$LAST_TAG"..HEAD --oneline
# returns nothing
```
Stop. Do not generate an empty changelog. Report: "No commits found between `$LAST_TAG` and HEAD. Confirm the tag name or provide a date range."

**`git log` command fails (no tags exist)**:
```bash
git describe --tags --abbrev=0
# fatal: No names found, cannot describe anything.
```
Fall back to full history: `git log --pretty=format:"%h|%ai|%an|%s" --no-merges`. Warn the user that the range is unbounded (all commits since repo init).

**No conventional commits found**: Verify commit messages follow `type:` prefix format. Fall back to manual changelog if history is inconsistent.

**Ambiguous scope**: When a commit touches multiple features, split the changelog entry by affected area.

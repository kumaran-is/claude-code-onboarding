#!/usr/bin/env bash
# PostToolUse → Write|Edit: Warn when a CHANGELOG.md is edited without a versioned section.
#
# Root cause this prevents: Services had all changes piled under ## [Unreleased] with no
# version bump ever applied — no semver, no date. The first change has a version; subsequent
# PRs never bump it because the step was undocumented. This hook catches that pattern and
# surfaces the exact format required so the author fixes it before committing.
#
# Works for both monorepo (multiple CHANGELOG.md files per service) and single-repo layouts.
# Always exits 0 — this is a warning hook, not a blocker.
set -o pipefail

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || file_path=""

# Only act on CHANGELOG.md files
if ! echo "$file_path" | grep -q "CHANGELOG\.md$"; then
  exit 0
fi

# Read the file and check for a versioned section (## [X.Y.Z] — YYYY-MM-DD pattern)
if [ ! -f "$file_path" ]; then
  exit 0
fi

# Check if there is ANY versioned release section (not just [Unreleased])
# Matches standard semver [X.Y.Z] AND build number format [X.Y.Z+N]
if grep -qE "^## \[[0-9]+\.[0-9]+\.[0-9]+(\+[0-9]+)?\]" "$file_path"; then
  # Good — at least one versioned section exists
  exit 0
fi

# No versioned section found — only [Unreleased] with no version bump
today=$(date +%Y-%m-%d)
msg="⚠️  CHANGELOG VERSION MISSING — ${file_path} has no versioned release section.

All changes are under ## [Unreleased] with no semver or date, so the change history cannot be read by release.

Required format:
## [Unreleased]

## [0.1.0] — ${today}
### Added
- ...

Before committing:
1. Move changes from ## [Unreleased] into ## [X.Y.Z] — ${today}
2. Leave ## [Unreleased] empty at the top for future changes
3. Follow semver: patch (0.0.x) = bug fix, minor (0.x.0) = new feature, major (x.0.0) = breaking change
4. Add comparison links at the bottom (https://keepachangelog.com/en/1.1.0/)"
command -v jq >/dev/null 2>&1 || exit 0
jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
exit 0

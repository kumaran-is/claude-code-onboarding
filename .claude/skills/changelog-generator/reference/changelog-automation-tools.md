# Changelog Automation Tools — Configuration Reference

CI/CD tool configs for automated release pipelines. Complements `changelog-workflow.md` (which covers how Claude generates changelogs on-demand).

## Tool Selection Guide

| Project type | Recommended tool |
|---|---|
| NestJS / Angular (npm) | semantic-release (full automation, integrates with npm ecosystem) |
| All stacks (zero npm deps) | git-cliff (just needs `cliff.toml`, works with any language) |
| Any stack with manual release | GitHub Actions + `workflow_dispatch` + standard-version or git-cliff |

---

## Section 1: git-cliff Configuration

Works with any stack. Reads conventional commits, produces a formatted `CHANGELOG.md`.

**File:** `cliff.toml` (place at repo root)

```toml
[changelog]
header = """
# Changelog

All notable changes to this project will be documented in this file.

"""
body = """
{% if version %}\
    ## [{{ version | trim_start_matches(pat="v") }}] - {{ timestamp | date(format="%Y-%m-%d") }}
{% else %}\
    ## [Unreleased]
{% endif %}\
{% for group, commits in commits | group_by(attribute="group") %}
    ### {{ group | upper_first }}
    {% for commit in commits %}
        - {% if commit.scope %}**{{ commit.scope }}:** {% endif %}\
            {{ commit.message | upper_first }}\
            {% if commit.github.pr_number %} ([#{{ commit.github.pr_number }}](https://github.com/${GITHUB_ORG}/${REPO_NAME}/pull/{{ commit.github.pr_number }})){% endif %}\
    {% endfor %}
{% endfor %}
"""
footer = """
{% for release in releases -%}
    {% if release.version -%}
        {% if release.previous.version -%}
            [{{ release.version | trim_start_matches(pat="v") }}]: \
                https://github.com/${GITHUB_ORG}/${REPO_NAME}/compare/{{ release.previous.version }}...{{ release.version }}
        {% endif -%}
    {% else -%}
        [unreleased]: https://github.com/${GITHUB_ORG}/${REPO_NAME}/compare/{{ release.previous.version }}...HEAD
    {% endif -%}
{% endfor %}
"""
trim = true

[git]
conventional_commits = true
filter_unconventional = true
split_commits = false
commit_parsers = [
    { message = "^feat",              group = "Features" },
    { message = "^fix",               group = "Bug Fixes" },
    { message = "^perf",              group = "Performance" },
    { message = "^refactor",          group = "Refactoring" },
    { message = "^docs",              group = "Documentation" },
    { message = "^test",              group = "Testing" },
    { message = "^chore\\(release\\)", skip = true },
    { message = "^chore",             group = "Miscellaneous" },
]
filter_commits = false
tag_pattern = "v[0-9]*"
topo_order = false
sort_commits = "oldest"

[github]
owner = "${GITHUB_ORG}"
repo  = "${REPO_NAME}"
```

**Replace** `${GITHUB_ORG}` and `${REPO_NAME}` with actual values before committing.

**CLI commands:**

```bash
# Generate full changelog
git cliff -o CHANGELOG.md

# Generate release notes for a specific range
git cliff v1.0.0..v2.0.0 -o RELEASE_NOTES.md

# Preview without writing
git cliff --unreleased --dry-run
```

---

## Section 2: semantic-release Configuration

Best for NestJS / Angular (npm ecosystem). Fully automates version bump, changelog, GitHub release, and git tag.

**Branch behaviour (matches `feature/* → develop → main` workflow):**

| Push to | Produces | Purpose |
|---|---|---|
| `develop` | `1.2.0-beta.1` pre-release tag | QA / staging validation |
| `main` | `1.2.0` stable release + CHANGELOG update | Production |

**File:** `release.config.js` (place at repo root)

```javascript
module.exports = {
  branches: [
    'main',
    { name: 'develop', channel: 'beta', prerelease: true },
  ],
  plugins: [
    '@semantic-release/commit-analyzer',
    '@semantic-release/release-notes-generator',
    [
      '@semantic-release/changelog',
      {
        changelogFile: 'CHANGELOG.md',
      },
    ],
    [
      '@semantic-release/npm',
      {
        npmPublish: false,   // Internal services — not published to npm registry
      },
    ],
    [
      '@semantic-release/github',
      {
        assets: ['dist/**/*.js', 'dist/**/*.css'],
      },
    ],
    [
      '@semantic-release/git',
      {
        assets: ['CHANGELOG.md', 'package.json'],
        message: 'chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}',
      },
    ],
  ],
};
```

**Note:** `NPM_TOKEN` secret is NOT required when `npmPublish: false`. Only `GITHUB_TOKEN` is needed.

---

## Section 3: GitHub Actions Release Workflow

**File:** `.github/workflows/release.yml`

```yaml
name: Release

on:
  push:
    branches: [main, develop]   # develop → beta release; main → stable release
  workflow_dispatch:
    inputs:
      release_type:
        description: 'Release type (manual release only)'
        required: true
        default: 'patch'
        type: choice
        options:
          - patch
          - minor
          - major

permissions:
  contents: write
  pull-requests: write

jobs:
  semantic-release:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: '26'   # Matches workspace Node.js 26.13.x
          cache: 'npm'

      - run: npm ci

      - name: Configure Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Run semantic-release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          # NPM_TOKEN not required — npmPublish is false in release.config.js
        run: npx semantic-release

  manual-release:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0

      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: '24'
          cache: 'npm'

      - run: npm ci

      - name: Configure Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Bump version and generate changelog
        run: npx standard-version --release-as ${{ inputs.release_type }}

      - name: Push changes
        run: git push --follow-tags origin main

      - name: Create GitHub Release
        uses: softprops/action-gh-release@8a0cd651e5b2365bd640854a3fa5dfc70e4875f3 # v3.0.4
        with:
          generate_release_notes: true
```

---

## Section 4: Installation Commands

```bash
# git-cliff (language-agnostic, no npm required)
brew install git-cliff            # macOS
cargo install git-cliff           # any platform with Rust

# semantic-release (NestJS / Angular projects)
npm install --save-dev \
  semantic-release \
  @semantic-release/changelog \
  @semantic-release/git \
  @semantic-release/github \
  @semantic-release/npm

# standard-version (manual release fallback)
npm install --save-dev standard-version
```

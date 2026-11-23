---
name: asc-testflight-orchestration
description: "TestFlight groups, testers, build distribution and What to Test notes with the asc CLI. Use when rolling out an iOS beta or managing testers."
allowed-tools: Bash, Read
metadata:
  triggers: TestFlight, beta testers, beta group, distribute beta, testflight group, add tester, invite tester, What to Test, beta distribution, asc testflight, roll out beta
  related-skills: asc-cli-usage, asc-id-resolver, asc-release-flow, asc-build-lifecycle
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# asc TestFlight orchestration

Use this skill when managing TestFlight testers, groups, and build distribution.

## Iron Law

**NEVER ADD TESTERS OR DISTRIBUTE BUILDS WITHOUT FIRST CONFIRMING GROUP AND BUILD IDS — RUN `asc-id-resolver` FIRST**

Use `--paginate` on all list commands for accounts with many testers or groups to avoid incomplete results.

## Export current config
- `asc testflight sync pull --app "APP_ID" --output "./testflight.yaml"`
- Include builds/testers:
  - `asc testflight sync pull --app "APP_ID" --output "./testflight.yaml" --include-builds --include-testers`

## Manage groups and testers
- Groups:
  - `asc testflight beta-groups list --app "APP_ID" --paginate`
  - `asc testflight beta-groups create --app "APP_ID" --name "Beta Testers"`
- Testers:
  - `asc testflight beta-testers list --app "APP_ID" --paginate`
  - `asc testflight beta-testers add --app "APP_ID" --email "tester@example.com" --group "Beta Testers"`
  - `asc testflight beta-testers invite --app "APP_ID" --email "tester@example.com"`

## Distribute builds
- `asc builds add-groups --build "BUILD_ID" --group "GROUP_ID"`
- Remove from group:
  - `asc builds remove-groups --build "BUILD_ID" --group "GROUP_ID"`

## What to Test notes
- `asc builds test-notes create --build "BUILD_ID" --locale "en-US" --whats-new "Test instructions"`
- `asc builds test-notes update --id "LOCALIZATION_ID" --whats-new "Updated notes"`

## Notes
- Use `--paginate` on large groups/tester lists.
- Prefer IDs for deterministic operations; use the ID resolver skill when needed.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| asc CLI help | `asc testflight --help`, `asc builds --help` | Current TestFlight distribution flags |
| asc-id-resolver skill | Load skill | Resolve group IDs, build IDs, tester emails to IDs |

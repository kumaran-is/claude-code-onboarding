---
name: asc-submission-health
description: "Preflight, submit and monitor App Store review with the asc CLI: encryption compliance, version metadata, review status, \"Version is not in valid state\". Use before or after an App Store submission."
allowed-tools: Bash, Read
metadata:
  triggers: App Store submission, submit for review, submission health, preflight check, review status, encryption compliance, submission failed, version not valid state, asc submit, review rejection, content rights
  related-skills: asc-cli-usage, asc-id-resolver, asc-release-flow, asc-xcode-build
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# asc Submission Health

## Iron Law

**NEVER SUBMIT TO APP STORE REVIEW WITHOUT COMPLETING ALL 7 PREFLIGHT CHECKS — A FAILED SUBMISSION WASTES REVIEW QUEUE TIME**

Read `reference/submission-preflight-checklist.md` and complete every item before running any submit command.

## Preconditions
- Auth is configured (`asc auth login` or `ASC_*` env vars set)
- App, version, and build IDs resolved (use `asc-id-resolver` skill)
- Build is processed (not in `PROCESSING` state)
- All required metadata is complete

## Pre-submission Checklist

The full 7-step checklist with commands is in `reference/submission-preflight-checklist.md`.

**Quick reference — all 7 steps must pass before submitting:**
1. Verify build status — build must be `VALID`, not `PROCESSING`
2. Encryption compliance — declaration must exist and be assigned to build
3. Content rights declaration — must be set on the app
4. Version metadata — copyright, release type must be set
5. Localizations complete — all required locales have content
6. Screenshots present — all required device sizes uploaded
7. App info localizations — privacy policy URL set for all locales

> For full commands for each step: Read `reference/submission-preflight-checklist.md`

## Submit

### Using Review Submissions API (Recommended)
```bash
asc review submissions-create --app "APP_ID" --platform IOS
asc review items-add --submission "SUBMISSION_ID" --item-type appStoreVersions --item-id "VERSION_ID"
asc review submissions-submit --id "SUBMISSION_ID" --confirm
```

### Using Submit Command
```bash
asc submit create --app "APP_ID" --version "1.2.3" --build "BUILD_ID" --confirm
asc submit status --id "SUBMISSION_ID"
asc submit status --version-id "VERSION_ID"
```

## Monitor
```bash
asc review submissions-list --app "APP_ID" --paginate
asc submit status --id "SUBMISSION_ID"
```

## Cancel / Retry
```bash
asc submit cancel --id "SUBMISSION_ID" --confirm
asc review submissions-cancel --id "SUBMISSION_ID" --confirm
```

## Common Submission Errors

### "Version is not in valid state"
The version is in a state that does not allow submission. Check:
```bash
asc versions get --version-id "VERSION_ID" --include-build
```
Common causes: build not attached, metadata incomplete, prior submission not cancelled.

### "Export compliance must be approved"
```bash
asc encryption declarations list --app "APP_ID"
asc encryption declarations assign-builds --id "DECLARATION_ID" --build "BUILD_ID"
```

### "Multiple app infos found"
```bash
asc app-infos list --app "APP_ID"
```
Use the app info ID with `--app-info` flag on localizations commands.

## Notes
- Build must be processed before submission — poll `asc builds info` until state is `VALID`
- Encryption declaration must be assigned to the specific build, not just created
- Use Review Submissions API for more control; `asc submit create` is a shorthand

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| asc CLI help | `asc submit --help`, `asc review --help` | Current submission and review flags |
| Preflight checklist | Read `reference/submission-preflight-checklist.md` | Full 7-step pre-submission commands |
| asc-id-resolver skill | Load skill | Resolve app/version/build IDs before submitting |

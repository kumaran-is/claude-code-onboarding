---
name: asc-release-flow
description: "End-to-end iOS/macOS/tvOS/visionOS release with the asc CLI: upload IPA/PKG, TestFlight distribution, App Store submission. Use when shipping an Apple build. Not for Google Play (gpd-release-flow)."
allowed-tools: Bash, Read
metadata:
  triggers: upload build, distribute TestFlight, submit to App Store, asc publish, release flow, App Store submission, TestFlight distribute, upload IPA, upload PKG, iOS release, macOS release
  related-skills: asc-cli-usage, asc-id-resolver, asc-submission-health, asc-testflight-orchestration, asc-build-lifecycle
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# Release flow (TestFlight and App Store)

Use this skill when you need to get a new build into TestFlight or submit to the App Store.

## Iron Law

**NEVER UPLOAD A BUILD WITHOUT VERIFYING ENCRYPTION COMPLIANCE IS RESOLVED AND BUILD NUMBER IS UNIQUE**

Run `asc-submission-health` preflight checks before any App Store submission. Use `asc-id-resolver` to resolve all IDs before running release commands.

## Preconditions
- Ensure credentials are set (`asc auth login` or `ASC_*` env vars).
- Use a new build number for each upload.
- Prefer `ASC_APP_ID` or pass `--app` explicitly.
- Build must have encryption compliance resolved (see asc-submission-health skill).

## iOS Release

### Build gate (Flutter apps)
Build the IPA with the export options Xcode produced (Distribute App writes an `ExportOptions.plist` next to the IPA):
`flutter build ipa --release --export-options-plist=<path/to/ExportOptions.plist>` must exit 0 before any upload.

### Preferred end-to-end commands
- TestFlight:
  - `asc publish testflight --app <APP_ID> --ipa <PATH> --group <GROUP_ID>[,<GROUP_ID>]`
  - Optional: `--wait`, `--notify`, `--platform`, `--poll-interval`, `--timeout`
- App Store:
  - `asc publish appstore --app <APP_ID> --ipa <PATH> --version <VERSION>`
  - Optional: `--wait`, `--submit --confirm`, `--platform`, `--poll-interval`, `--timeout`

### Manual sequence (when you need more control)
1. Upload the build:
   - `asc builds upload --app <APP_ID> --ipa <PATH>`
2. Find the build ID if needed:
   - `asc builds latest --app <APP_ID> [--version <VERSION>] [--platform <PLATFORM>]`
3. TestFlight distribution:
   - `asc builds add-groups --build <BUILD_ID> --group <GROUP_ID>[,<GROUP_ID>]`
4. App Store attach + submit:
   - `asc versions attach-build --version-id <VERSION_ID> --build <BUILD_ID>`
   - `asc submit create --app <APP_ID> --version <VERSION> --build <BUILD_ID> --confirm`
5. Check or cancel submission:
   - `asc submit status --id <SUBMISSION_ID>` or `--version-id <VERSION_ID>`
   - `asc submit cancel --id <SUBMISSION_ID> --confirm`

## macOS Release

macOS apps are distributed as `.pkg` files, not `.ipa`.

### Build and Export
See `asc-xcode-build` skill for full build/archive/export workflow.

### Upload PKG
Upload the exported `.pkg` using `asc`:
```bash
asc builds upload \
  --app <APP_ID> \
  --pkg <PATH_TO_PKG> \
  --version <VERSION> \
  --build-number <BUILD_NUMBER> \
  --wait
```

Notes:
- `--pkg` automatically sets platform to `MAC_OS`.
- `asc publish appstore` currently supports `--ipa` workflows; for macOS `.pkg`, use `asc builds upload --pkg` + attach/submit steps below.

### Attach and Submit
Same as iOS, but use `--platform MAC_OS`:
```bash
# Wait for build to process
asc builds list --app <APP_ID> --platform MAC_OS --limit 5

# Attach to version
asc versions attach-build --version-id <VERSION_ID> --build <BUILD_ID>

# Create submission
asc review submissions-create --app <APP_ID> --platform MAC_OS

# Add version item
asc review items-add \
  --submission <SUBMISSION_ID> \
  --item-type appStoreVersions \
  --item-id <VERSION_ID>

# Submit
asc review submissions-submit --id <SUBMISSION_ID> --confirm
```

## visionOS / tvOS Release

Same as iOS flow, use appropriate `--platform`:
- `VISION_OS`
- `TV_OS`

## Multi-Platform Release

When releasing the same version across platforms:
1. Upload each platform's build separately
2. Create version for each platform if not exists
3. Attach builds to respective versions
4. Submit each platform separately (or together via reviewSubmissions API)

## Pre-submission Checklist
Before submitting, verify:
- [ ] Build status is `VALID` (not processing)
- [ ] Encryption compliance resolved
- [ ] Content rights declaration set
- [ ] Copyright field populated
- [ ] All localizations complete
- [ ] Screenshots present

See `asc-submission-health` skill for detailed preflight checks.

## Post-release monitoring gate

Team defaults (ADAPT per app): watch crashes for 48h after release, using the `asc-crash-triage` skill scoped to the released build plus your crash reporter. If a P0 crash affects >1% of users, stop the rollout and prepare a fix (`bugfix/` branch, new build number).
- Release with **Phased Release for Automatic Updates** (7 days: 1% → 2% → 5% → 10% → 20% → 50% → 100%) so there is a rollout to stop.
- To stop it: App Store Connect → the version under Ready for Distribution → Phased Release for Automatic Updates → **Pause Phased Release** → Save. Pauses total at most 30 days; resume the same way. Pausing affects only automatic updates: anyone can still download the version manually.
- The native asc skills expose no phased-release command; do this step in App Store Connect.

## Notes
- Always use `--help` to verify flags for the exact command.
- Use `--output table` / `--output markdown` for human-readable output; default is JSON.
- macOS builds require `ITSAppUsesNonExemptEncryption` in Info.plist to avoid encryption issues.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| asc CLI help | `asc publish --help`, `asc builds --help`, `asc submit --help` | Current flags for upload and submission commands |
| asc-submission-health skill | Load skill | Preflight checklist before any App Store submission |
| XcodeBuildMCP | `build_sim`, `build_run_sim` tools | Build and export IPA before upload |

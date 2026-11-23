---
name: asc-crash-triage
description: "Triage TestFlight crashes, beta feedback and performance diagnostics (hangs, disk writes, launch time) with the asc CLI. Use when investigating iOS beta crash reports or tester feedback."
allowed-tools: Bash, Read
metadata:
  triggers: TestFlight crashes, crash report, beta feedback, app hangs, performance diagnostics, crash triage, disk writes, launch diagnostics, asc crashes, asc feedback, crash summary
  related-skills: asc-cli-usage, asc-id-resolver, asc-build-lifecycle
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# asc Crash Triage

## Iron Law

**NEVER TRIAGE CRASHES WITHOUT FIRST IDENTIFYING THE BUILD AND APP IDS — USE `asc-id-resolver` TO RESOLVE THEM**

Crash data from App Store Connect may have a 24-48 hour delay. Always specify `--build` to scope results to a specific release.

## Workflow

1. Resolve the app ID if not provided (use `asc apps list`).
2. Fetch data with the appropriate command.
3. Parse JSON output and present a human-readable summary.

## TestFlight crash reports

List recent crashes (newest first):

- `asc crashes --app "APP_ID" --sort -createdDate --limit 10`
- Filter by build: `asc crashes --app "APP_ID" --build "BUILD_ID" --sort -createdDate --limit 10`
- Filter by device/OS: `asc crashes --app "APP_ID" --device-model "iPhone16,2" --os-version "18.0"`
- All crashes: `asc crashes --app "APP_ID" --paginate`
- Table view: `asc crashes --app "APP_ID" --sort -createdDate --limit 10 --output table`

## TestFlight beta feedback

List recent feedback (newest first):

- `asc feedback --app "APP_ID" --sort -createdDate --limit 10`
- With screenshots: `asc feedback --app "APP_ID" --sort -createdDate --limit 10 --include-screenshots`
- Filter by build: `asc feedback --app "APP_ID" --build "BUILD_ID" --sort -createdDate`
- All feedback: `asc feedback --app "APP_ID" --paginate`

## Performance diagnostics (hangs, disk writes, launches)

Requires a build ID. Resolve via `asc builds latest --app "APP_ID" --platform IOS` or `asc builds list --app "APP_ID" --sort -uploadedDate --limit 5`.

- List diagnostic signatures: `asc performance diagnostics list --build "BUILD_ID"`
- Filter by type: `asc performance diagnostics list --build "BUILD_ID" --diagnostic-type "HANGS"`
  - Types: `HANGS`, `DISK_WRITES`, `LAUNCHES`
- Get logs for a signature: `asc performance diagnostics get --id "SIGNATURE_ID"`
- Download all metrics: `asc performance download --build "BUILD_ID" --output ./metrics.json`

## Resolving IDs

- App ID from name: `asc apps list --name "AppName"` or `asc apps list --bundle-id "com.example.app"`
- Latest build ID: `asc builds latest --app "APP_ID" --platform IOS`
- Recent builds: `asc builds list --app "APP_ID" --sort -uploadedDate --limit 5`
- Set default: `export ASC_APP_ID="APP_ID"`

## Summary format

When presenting results, organize by severity and frequency:

1. **Total count** — how many crashes/feedbacks in the result set.
2. **Top crash signatures** — group by exception type or crash reason, ranked by count.
3. **Affected builds** — which build versions are impacted.
4. **Device & OS breakdown** — most affected device models and OS versions.
5. **Timeline** — when crashes started or spiked.

For performance diagnostics, highlight the highest-weight signatures first.

## Anti-Patterns

- **Don't triage crashes without scoping to a build.** Running `asc crashes --app "APP_ID"` without `--build` returns data across all builds — noise overwhelms signal. Always filter with `--build` once the build ID is known.
- **Don't assume crash data is real-time.** App Store Connect has a 24–48 hour delay; a zero-crash result right after release does not mean the release is clean.
- **Don't report "no crashes found" without using `--paginate`.** Default pagination may truncate results — use `--paginate` for a full analysis.

## Verify

After fetching crash or diagnostic data:
- Confirm result set is not truncated: check if response includes a `nextCursor` or pagination field — if so, re-run with `--paginate`.
- For performance diagnostics, verify the correct `--diagnostic-type` was passed (`HANGS`, `DISK_WRITES`, or `LAUNCHES`) — an empty result may mean the wrong type was specified, not that there are no issues.
- Run `asc crashes --app "APP_ID" --build "BUILD_ID" --output table` to visually confirm you are scoped to the correct build before summarizing.

## Notes

- Default output is JSON; use `--output table` or `--output markdown` for quick human review.
- Use `--paginate` to fetch all pages when doing a full analysis.
- Use `--pretty` with JSON for debugging command output.
- Crash data from App Store Connect may have 24-48h delay.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| asc CLI help | `asc crashes --help`, `asc feedback --help`, `asc performance --help` | Current flags for crash and diagnostic commands |
| asc-id-resolver skill | Load skill | Resolve app ID and build ID before querying crashes |

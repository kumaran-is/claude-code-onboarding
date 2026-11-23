---
name: gpd-release-flow
description: "End-to-end Google Play release with the gpd CLI: AAB upload, edit lifecycle, track publishing, staged rollout, promotion, halt and rollback. Use when shipping an Android build. Not for App Store (asc-release-flow)."
allowed-tools: Bash, Read
metadata:
  triggers: Google Play release, upload AAB, gpd publish, staged rollout, production release, promote track, edit lifecycle, Play Store release, internal track, beta to production
  related-skills: gpd-cli-usage, gpd-id-resolver, gpd-submission-health, gpd-betagroups, gpd-build-lifecycle
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# Release Flow (Google Play)

## Iron Law

**NEVER RELEASE TO PRODUCTION WITHOUT RUNNING `gpd-submission-health` PREFLIGHT CHECKS AND VALIDATING THE EDIT FIRST**

Always use a new version code per upload. Use `--dry-run` before destructive operations. Run `gpd publish edit validate` before committing.

## Preconditions
- Ensure credentials are set (`GPD_SERVICE_ACCOUNT_KEY`).
- Use a new version code for each upload.
- Always pass `--package` explicitly.

## Preferred end-to-end commands

### Upload and release to a track
```bash
gpd publish upload app.aab --package com.example.app
gpd publish release --package com.example.app --track internal --status completed
```

### Promote between tracks
```bash
gpd publish promote --package com.example.app --from-track beta --to-track production
```

## Manual sequence with edit lifecycle
Use when you need precise control or multiple changes in one commit.

```bash
# 1. Create edit
EDIT_ID=$(gpd publish edit create --package com.example.app | jq -r '.data.editId')

# 2. Upload build without auto-commit
gpd publish upload app.aab --package com.example.app --edit-id $EDIT_ID --no-auto-commit

# 3. Configure release
gpd publish release --package com.example.app --track internal --status draft --edit-id $EDIT_ID

# 4. Validate and commit
gpd publish edit validate $EDIT_ID --package com.example.app
gpd publish edit commit $EDIT_ID --package com.example.app
```

## Staged rollout
```bash
gpd publish release --package com.example.app --track production --status inProgress --version-code 123
gpd publish rollout --package com.example.app --track production --percentage 5
gpd publish rollout --package com.example.app --track production --percentage 50
gpd publish rollout --package com.example.app --track production --percentage 100
```

## Halt or rollback
```bash
gpd publish halt --package com.example.app --track production --confirm
gpd publish rollback --package com.example.app --track production --confirm
```

## Track status
```bash
gpd publish status --package com.example.app --track production
gpd publish tracks --package com.example.app
```

## Anti-Patterns

- **Don't commit an edit without running `gpd publish edit validate` first.** A committed edit with validation errors cannot be reverted — the release will be rejected or published in a broken state.
- **Don't skip staged rollout for production releases.** Releasing directly at 100% leaves no window to catch regressions; always start at 5–10% and monitor before escalating.
- **Don't use `--status completed` on production without running the `gpd-submission-health` preflight.** Skipping the preflight check risks publishing a build that fails Google Play policy review post-release.

## Verify

After each release step:
- Run `gpd publish status --package com.example.app --track <track>` to confirm the release state matches the intended status (`completed`, `inProgress`, `draft`, or `halted`).
- After staged rollout percentage changes, re-run `gpd publish status` and confirm the `userFraction` field reflects the new percentage before moving to the next increment.

## Notes
- Use `--status draft` first for risky releases.
- Use `--confirm` only after reviewing `gpd publish status` output.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| gpd CLI help | `gpd publish --help`, `gpd publish release --help` | Current release and rollout flags |
| gpd-submission-health skill | Load skill | Preflight checklist before any production release |
| gpd-id-resolver skill | Load skill | Resolve track names and version codes |
| Maestro MCP | `maestro` MCP server | Android E2E test flows before releasing |

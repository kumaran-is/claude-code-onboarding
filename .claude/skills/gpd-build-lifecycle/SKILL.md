---
name: gpd-build-lifecycle
description: "Google Play AAB upload, build processing, track status, internal app sharing, rollout halt and rollback with the gpd CLI. Use when tracking an Android build after upload."
allowed-tools: Bash, Read
metadata:
  triggers: upload AAB, build lifecycle, gpd upload, release status, internal app sharing, halt rollout, rollback release, gpd build, track status, build processing
  related-skills: gpd-cli-usage, gpd-id-resolver, gpd-release-flow, gpd-submission-health
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# GPD Build Lifecycle

## Iron Law

**NEVER UPLOAD THE SAME VERSION CODE TWICE — USE A NEW VERSION CODE FOR EVERY BUILD UPLOAD**

Use `gpd publish status` to check the current version code before uploading.

## Upload and validate
```bash
gpd publish upload app.aab --package com.example.app
```

## Inspect release status
```bash
gpd publish status --package com.example.app --track internal
gpd publish status --package com.example.app --track production
```

## Recent tracks and releases
```bash
gpd publish tracks --package com.example.app
```

## Internal app sharing
Use for fast distribution of a build without a full track release.

```bash
gpd publish internal-share upload app.aab --package com.example.app
```

## Cleanup and rollback
```bash
gpd publish halt --package com.example.app --track production --confirm
gpd publish rollback --package com.example.app --track production --confirm
```

## Anti-Patterns

- **Don't upload an AAB without checking the current version code first.** Re-uploading the same version code will be rejected by Google Play; run `gpd publish status --package com.example.app --track internal` before uploading.
- **Don't halt a rollout without reviewing the release status first.** Running `gpd publish halt --confirm` without checking `gpd publish status` risks halting the wrong track or a fully-rolled-out release.
- **Don't use internal app sharing as a substitute for a proper track release.** Internal app sharing bypasses review and track promotion history — use it for smoke tests only, not for beta distribution.

## Verify

After uploading a build:
- Run `gpd publish status --package com.example.app --track internal` and confirm the new version code appears with status `completed` or `draft`.
- After a halt or rollback, run `gpd publish status --package com.example.app --track production` to confirm the release state reflects the change before notifying stakeholders.

## Notes
- Prefer `gpd publish release` for end-to-end flow instead of manual steps.
- Use a new version code for each uploaded build.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| gpd CLI help | `gpd publish upload --help`, `gpd publish status --help` | Current upload and status flags |
| gpd-id-resolver skill | Load skill | Resolve track names and version codes before operating |

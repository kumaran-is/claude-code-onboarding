---
name: gpd-betagroups
description: "Google Play testers, tester groups and internal/alpha/beta track distribution with the gpd CLI. Use when managing Android beta testers or promoting between testing tracks."
allowed-tools: Bash, Read
metadata:
  triggers: beta testers, internal testing, testing track, gpd testers, beta rollout, promote track, internal track, beta group, add tester, Google Play beta, distribute build
  related-skills: gpd-cli-usage, gpd-id-resolver, gpd-release-flow, gpd-build-lifecycle
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# GPD Beta Groups

## Iron Law

**NEVER DISTRIBUTE A BUILD TO BETA WITHOUT FIRST CONFIRMING THE VERSION CODE IS UPLOADED AND THE TRACK IS CORRECT — USE `gpd-id-resolver` FIRST**

Use `--track internal` for fast internal distribution. Prefer IDs for deterministic operations.

## List and manage testers
```bash
gpd publish testers list --package com.example.app --track internal
gpd publish testers list --package com.example.app --track beta
gpd publish testers add --package com.example.app --track internal --group testers@example.com
```

## Distribute builds to testing tracks
```bash
gpd publish release --package com.example.app --track internal --status completed
gpd publish release --package com.example.app --track beta --status completed
```

## Promote between testing tracks
```bash
gpd publish promote --package com.example.app --from-track internal --to-track beta
gpd publish promote --package com.example.app --from-track beta --to-track production
```

## Anti-Patterns

- **Don't promote directly from internal to production.** Always go `internal → beta → production` to gate quality at each stage; skipping beta bypasses external tester validation.
- **Don't use `--track production` when distributing an unvalidated build.** Use `--track internal` or `--track beta` first; a bad production release requires a halt and rollback.
- **Don't add testers without confirming the track name first.** Run `gpd publish tracks --package com.example.app` to verify available tracks — using an incorrect track name silently fails on some versions.

## Verify

After distributing a build or modifying testers:
- Run `gpd publish testers list --package com.example.app --track <track>` to confirm the tester group is present.
- Run `gpd publish status --package com.example.app --track <track>` to confirm the build is visible on the target track.

## Notes
- Use `--track internal` for fast internal distribution.
- Prefer IDs for deterministic operations; use the ID resolver skill when needed.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| gpd CLI help | `gpd publish testers --help`, `gpd publish promote --help` | Current tester and promotion flags |
| gpd-id-resolver skill | Load skill | Resolve track names and package identifiers |

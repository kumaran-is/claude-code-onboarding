---
name: gpd-submission-health
description: "Preflight Google Play releases with the gpd CLI: edit validation, version code, listing and screenshot completeness, deobfuscation mapping, policy declarations. Use before a production release or after a failed one."
allowed-tools: Bash, Read
metadata:
  triggers: Play Store submission, production release check, gpd preflight, submission health, edit validate, release not valid, missing screenshots, policy declaration, deobfuscation mapping, gpd submit
  related-skills: gpd-cli-usage, gpd-id-resolver, gpd-release-flow, gpd-metadata-sync
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# GPD Submission Health

## Iron Law

**NEVER SUBMIT TO PRODUCTION WITHOUT COMPLETING ALL 5 PREFLIGHT CHECKS — A FAILED RELEASE BLOCKS ALL USERS ON THAT TRACK**

Read `reference/submission-preflight-checklist.md` and complete every item before running any production release command.

## Preconditions
- Auth configured and package name resolved.
- Build uploaded and available for the target track.
- Store listing metadata and assets updated.

## Pre-submission Checklist

The full 6-step checklist with commands is in `reference/submission-preflight-checklist.md`.

**Quick reference — all 6 steps must pass before releasing to production:**
1. Validate edit — `gpd publish edit validate` must return no errors
2. Confirm release status — version code matches uploaded build
3. Verify store listing metadata — title, description, contact email present
4. Verify screenshots and assets — required device types uploaded per locale
5. Upload deobfuscation mapping — required if ProGuard/R8 is enabled
6. Build and policy requirements — not debuggable, target API level current, Play App Signing, privacy policy URL, content rating

> For full commands for each step: Read `reference/submission-preflight-checklist.md`

## Submit to production
```bash
gpd publish release --package com.example.app --track production --status inProgress --version-code 123
```

## Common submission issues

### Release not in valid state
Check:
1. Version code uploaded and attached to the track.
2. Edit validation passes.
3. Required store listing fields present for all locales.

### Missing screenshots or assets
```bash
gpd publish images list phoneScreenshots --package com.example.app --locale en-US
gpd publish images upload icon icon.png --package com.example.app --locale en-US
```

### Policy declarations not complete
Some policy/compliance items must be completed in Play Console UI. Confirm in the console if CLI operations pass but submission is blocked.

## Notes
- Use `gpd publish edit validate` before committing large changes.
- Use `--dry-run` where available before destructive actions.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| gpd CLI help | `gpd publish edit --help`, `gpd publish release --help` | Current validation and release flags |
| Preflight checklist | Read `reference/submission-preflight-checklist.md` | Full 6-step pre-release checklist |
| gpd-id-resolver skill | Load skill | Resolve package name and track before submitting |

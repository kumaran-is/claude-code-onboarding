# Android Google Play release pipeline

Moved from the public README so the landing page stays short. Content is unchanged except where noted.

## 17. Android Google Play Release Pipeline

Flutter developers build Android apps — but the journey doesn't end at the AAB. This section covers the full pipeline from Android build to Google Play production, powered by the GPD skills in this kit.

### How the Tools Fit Together

```
Flutter Development          flutter CLI / Maestro MCP       GPD Skills
──────────────────           ──────────────────────────      ────────────────────────────────
Write Dart/Flutter code  →   Build Android AAB           →   Upload AAB to Google Play
flutter build appbundle  →   Run E2E tests (Maestro)     →   Release to internal/beta track
Riverpod + Freezed       →   Inspect on emulator         →   Staged rollout to production
Widget tests             →   Cross-platform E2E flows     →   Monitor vitals and reviews
```

**Flutter CLI** handles the Android build: `flutter build appbundle` produces the `.aab` file.

**Maestro MCP** (`maestro` in `.mcp.json`) runs cross-platform E2E test flows on Android emulator before release.

**GPD Skills** handle everything after the AAB is built: uploading to Google Play, track management, staged rollouts, submission health checks, and post-release monitoring.

### Step 1 — Build the AAB (Flutter CLI)

```bash
# Build release AAB
flutter build appbundle --release

# Output: build/app/outputs/bundle/release/app-release.aab
```

Then run E2E flows on Android emulator via Maestro MCP before uploading.

### Step 2 — Resolve IDs (gpd-id-resolver skill)

Before running any release commands, resolve your package name and track names:

```bash
gpd publish tracks --package com.example.app
gpd publish status --package com.example.app --track production
```

Load skill: `.claude/skills/gpd-id-resolver/`

### Step 3 — Upload & Release (gpd-release-flow skill)

```bash
# Upload AAB to Google Play
gpd publish upload app.aab --package com.example.app

# Release to internal track
gpd publish release --package com.example.app --track internal --status completed

# Promote to beta
gpd publish promote --package com.example.app --from-track internal --to-track beta

# Staged rollout to production: 5% → 50% → 100%
gpd publish release --package com.example.app --track production --status inProgress --version-code 123
gpd publish rollout --package com.example.app --track production --percentage 5
gpd publish rollout --package com.example.app --track production --percentage 50
gpd publish rollout --package com.example.app --track production --percentage 100
```

Load skill: `.claude/skills/gpd-release-flow/`

### Step 4 — Manage Beta Testers (gpd-betagroups skill)

```bash
gpd publish testers list --package com.example.app --track internal
gpd publish testers add --package com.example.app --track internal --group testers@example.com
gpd publish release --package com.example.app --track beta --status completed
```

Load skill: `.claude/skills/gpd-betagroups/`

### Step 5 — Preflight Before Production (gpd-submission-health skill)

Run all 5 preflight checks before releasing to production. See `reference/submission-preflight-checklist.md` for full commands.

```bash
gpd publish edit validate EDIT_ID --package com.example.app   # Must pass
gpd publish status --package com.example.app --track production
gpd publish listing get --package com.example.app             # Metadata complete
gpd publish images list phoneScreenshots --package com.example.app --locale en-US
```

Load skill: `.claude/skills/gpd-submission-health/`

### Step 6 — Monitor Build State (gpd-build-lifecycle skill)

```bash
gpd publish status --package com.example.app --track production
gpd publish tracks --package com.example.app

# Emergency: halt bad rollout
gpd publish halt --package com.example.app --track production --confirm
gpd publish rollback --package com.example.app --track production --confirm
```

Load skill: `.claude/skills/gpd-build-lifecycle/`

### GPD Skills in This Kit

These skills were adapted from the open-source [gpd-cli-skills](https://github.com/rudrankriyam/gpd-cli-skills) repository by [@rudrankriyam](https://github.com/rudrankriyam), and enhanced to match this kit's skill standards (Iron Law, progressive disclosure, metadata blocks, Documentation Sources).

| Skill | Directory | When to Load |
|-------|-----------|-------------|
| `gpd-cli-usage` | `.claude/skills/gpd-cli-usage/` | Before running any `gpd` command |
| `gpd-id-resolver` | `.claude/skills/gpd-id-resolver/` | When you need package name, track, version code, or product ID |
| `gpd-release-flow` | `.claude/skills/gpd-release-flow/` | Uploading AAB, track releases, staged rollout |
| `gpd-betagroups` | `.claude/skills/gpd-betagroups/` | Managing internal/beta testers and track promotion |
| `gpd-submission-health` | `.claude/skills/gpd-submission-health/` | Preflight checks before production release |
| `gpd-build-lifecycle` | `.claude/skills/gpd-build-lifecycle/` | Build upload status, internal sharing, halt/rollback |

### Prerequisites

```bash
# Install the gpd CLI
brew install rudrankriyam/tap/google-play-developer-cli

# Set service account credentials
export GPD_SERVICE_ACCOUNT_KEY="/path/to/service-account.json"

# Validate access
gpd auth check --package com.example.app
```

### Example Prompts

Copy any of these directly into Claude Code to trigger the Android release skills:

**Upload AAB and release to internal track**
```
Upload ./build/app/outputs/bundle/release/app-release.aab to Google Play for package com.example.myapp and release it to the internal testing track.
```

**Staged rollout to production**
```
Promote my app com.example.myapp from beta to production with a staged rollout — start at 5%, then 50%, then 100%.
```

**Full preflight check before production**
```
Run all preflight submission checks for com.example.myapp version code 123 before I release to the production track.
```

**Add beta testers**
```
Add tester@example.com to the internal testing track for com.example.myapp and distribute the latest build to them.
```

**Check release status**
```
What is the current release status of com.example.myapp on the production track? Show version code and rollout percentage.
```

**Halt a bad rollout**
```
Halt the production rollout for com.example.myapp immediately — there's a critical crash in the latest release.
```

**Resolve IDs before release**
```
List all available tracks and the current version codes for com.example.myapp on Google Play.
```

**Manage store listing**
```
Export the current Play Store listing for com.example.myapp to a local Fastlane metadata folder, then validate it.
```

> Skills used by these prompts: `gpd-cli-usage` → `gpd-id-resolver` → `gpd-build-lifecycle` → `gpd-release-flow` → `gpd-betagroups` → `gpd-submission-health`
>
> Source: [github.com/rudrankriyam/gpd-cli-skills](https://github.com/rudrankriyam/gpd-cli-skills)

---

# iOS App Store release pipeline

Moved from the public README so the landing page stays short. Content is unchanged except where noted.

## 16. iOS App Store Release Pipeline

Flutter developers build the app — but the journey doesn't end at the IPA. This section covers the full pipeline from Xcode build to App Store review, powered by two complementary tools in this kit.

### How the Tools Fit Together

```
Flutter Development          XcodeBuildMCP                  ASC Skills
──────────────────           ──────────────────             ───────────────────────────
Write Dart/Flutter code  ->  Build iOS project         ->  Upload IPA to App Store Connect
flutter build ios        ->  Archive & export IPA       ->  Distribute to TestFlight groups
Riverpod + Freezed       ->  Debug on simulator         ->  Submit to App Store review
Widget tests             ->  Capture screenshots        ->  Monitor review status
                         ->  Inspect signing config     ->  Triage crash reports
```

**XcodeBuildMCP** (`xcodebuild` in `.mcp.json`) handles everything that requires a live Xcode environment: building, archiving, running on simulator, attaching a debugger, and capturing logs.

**ASC Skills** handle everything that happens after the IPA is built: uploading, TestFlight distribution, signing asset management, App Store submission, and post-release monitoring.

### Step 1 — Build the IPA (XcodeBuildMCP)

The `xcodebuild` MCP server executes these steps natively. Load the `flutter-mobile` skill and use XcodeBuildMCP tools:

```
1. discover_projs -> finds ios/Runner.xcworkspace
2. list_schemes   -> identifies the Runner scheme
3. build_sim      -> builds for simulator (development)
4. build_run_sim  -> builds + launches on simulator
5. show_build_settings -> verifies signing config
```

For a release build that produces an IPA for upload:

```bash
# Run once to generate Xcode project and Pods
flutter build ios --release

# XcodeBuildMCP then handles archive + export
# (or use xcodebuild directly via asc-xcode-build skill)
```

### Step 2 — Set Up Signing (asc-signing-setup skill)

Before uploading, ensure signing assets are in place:

```bash
asc bundle-ids list --paginate
asc certificates list --certificate-type IOS_DISTRIBUTION
asc profiles create --name "AppStore Profile" --profile-type IOS_APP_STORE \
  --bundle "BUNDLE_ID" --certificate "CERT_ID"
asc profiles download --id "PROFILE_ID" --output "./profiles/"
```

Load skill: `.claude/skills/asc-signing-setup/`

### Step 3 — Upload & Distribute (asc-release-flow skill)

```bash
# Preferred: single command for TestFlight
asc publish testflight --app APP_ID --ipa ./build/ios/ipa/MyApp.ipa --group GROUP_ID --wait

# Preferred: single command for App Store
asc publish appstore --app APP_ID --ipa ./build/ios/ipa/MyApp.ipa --version 1.2.3 --wait --submit --confirm
```

Load skill: `.claude/skills/asc-release-flow/`

### Step 4 — Manage Beta (asc-testflight-orchestration skill)

```bash
asc testflight beta-groups list --app APP_ID --paginate
asc testflight beta-testers add --app APP_ID --email tester@example.com --group "Beta"
asc builds add-groups --build BUILD_ID --group GROUP_ID
asc builds test-notes create --build BUILD_ID --locale en-US --whats-new "Bug fixes"
```

Load skill: `.claude/skills/asc-testflight-orchestration/`

### Step 5 — Preflight & Submit (asc-submission-health skill)

Run all 7 preflight checks before submitting. See `reference/submission-preflight-checklist.md` for the full checklist.

```bash
asc builds info --build BUILD_ID                        # Must be VALID
asc encryption declarations list --app APP_ID           # Must exist + assigned
asc submit create --app APP_ID --version 1.2.3 --build BUILD_ID --confirm
asc submit status --id SUBMISSION_ID
```

Load skill: `.claude/skills/asc-submission-health/`

### Step 6 — Monitor & Triage (asc-crash-triage skill)

After release, monitor crashes and beta feedback:

```bash
asc crashes --app APP_ID --sort -createdDate --limit 10
asc feedback --app APP_ID --sort -createdDate --limit 10
asc performance diagnostics list --build BUILD_ID
```

Load skill: `.claude/skills/asc-crash-triage/`

### ASC Skills in This Kit

These skills were adapted from the open-source [app-store-connect-cli-skills](https://github.com/rudrankriyam/app-store-connect-cli-skills) repository by [@rudrankriyam](https://github.com/rudrankriyam), and enhanced to match this kit's skill standards (Iron Law, progressive disclosure, metadata blocks, Documentation Sources).

| Skill | Directory | When to Load |
|-------|-----------|-------------|
| `asc-cli-usage` | `.claude/skills/asc-cli-usage/` | Before running any `asc` command |
| `asc-id-resolver` | `.claude/skills/asc-id-resolver/` | When you need APP_ID, BUILD_ID, GROUP_ID |
| `asc-signing-setup` | `.claude/skills/asc-signing-setup/` | Setting up or rotating signing assets |
| `asc-release-flow` | `.claude/skills/asc-release-flow/` | Uploading IPA, TestFlight or App Store release |
| `asc-testflight-orchestration` | `.claude/skills/asc-testflight-orchestration/` | Managing beta groups, testers, build notes |
| `asc-submission-health` | `.claude/skills/asc-submission-health/` | Preflight checks and App Store submission |
| `asc-crash-triage` | `.claude/skills/asc-crash-triage/` | Crash reports, beta feedback, performance |

### Prerequisites

```bash
# Install the asc CLI
brew install rudrankriyam/tap/app-store-connect-cli

# Authenticate (keychain — recommended)
asc auth login

# Or set environment variables
export ASC_KEY_ID="your-key-id"
export ASC_ISSUER_ID="your-issuer-id"
export ASC_PRIVATE_KEY_PATH="/path/to/AuthKey.p8"
```

### Example Prompts

Copy any of these directly into Claude Code to trigger the iOS release skills:

**Upload & TestFlight distribution**
```
Upload the IPA at ./build/ios/ipa/MyApp.ipa to TestFlight for app APP_ID and distribute it to the "Internal Testers" group.
```

**Full App Store release**
```
Run all preflight submission checks for my iOS app APP_ID version 2.1.0, then submit it to App Store review.
```

**Signing setup**
```
Create a new App Store distribution certificate and provisioning profile for bundle ID com.example.myapp on iOS.
```

**Check review status**
```
What is the current App Store review status for my app APP_ID? Show me if there are any active submissions.
```

**Crash triage**
```
Show me the top 10 TestFlight crash reports for app APP_ID sorted by most recent, grouped by crash signature.
```

**Resolve IDs**
```
Find the app ID, latest build ID, and Internal Testers group ID for my app with bundle ID com.example.myapp.
```

**Rotate expired certificate**
```
My iOS distribution certificate is expiring. Check what exists, revoke the old one, and create a new certificate and provisioning profile for com.example.myapp.
```

**TestFlight What to Test notes**
```
Set the What to Test notes for build BUILD_ID in en-US locale to "Fixed login crash on iOS 18. Please test the onboarding flow."
```

> Skills used by these prompts: `asc-cli-usage` → `asc-id-resolver` → `asc-signing-setup` → `asc-release-flow` → `asc-testflight-orchestration` → `asc-submission-health` → `asc-crash-triage`
>
> Source: [github.com/rudrankriyam/app-store-connect-cli-skills](https://github.com/rudrankriyam/app-store-connect-cli-skills)

---

# Submission Preflight Checklist

Complete all 8 steps before submitting to App Store review.

## Step 1: Verify Build Status

Build must be in `VALID` state (not `PROCESSING`).

```bash
asc builds info --build "BUILD_ID"
```

Expected: `"processingState": "VALID"` in output.

## Step 2: Encryption Compliance

Every build needs an encryption compliance declaration.

```bash
# Check if declaration exists
asc encryption declarations list --app "APP_ID"

# Create if missing
asc encryption declarations create \
  --app "APP_ID" \
  --app-description "Uses standard HTTPS/TLS" \
  --contains-proprietary-cryptography=false \
  --contains-third-party-cryptography=true \
  --available-on-french-store=true

# Assign to build
asc encryption declarations assign-builds --id "DECLARATION_ID" --build "BUILD_ID"
```

## Step 3: Content Rights Declaration

```bash
# Check current value
asc apps get --id "APP_ID" --output json | jq '.data.attributes.contentRightsDeclaration'

# Set if missing
asc apps update --id "APP_ID" --content-rights "DOES_NOT_USE_THIRD_PARTY_CONTENT"
```

Values: `DOES_NOT_USE_THIRD_PARTY_CONTENT`, `USES_THIRD_PARTY_CONTENT`

## Step 4: Version Metadata

```bash
# Check version
asc versions get --version-id "VERSION_ID" --include-build

# Set copyright and release type
asc versions update --version-id "VERSION_ID" --copyright "2026 Your Company"
asc versions update --version-id "VERSION_ID" --release-type AFTER_APPROVAL
```

Release types: `AFTER_APPROVAL`, `MANUAL`, `SCHEDULED`

## Step 5: Localizations Complete

```bash
asc localizations list --version "VERSION_ID"
```

All required locales must have: name, description, keywords, support URL, what's new (for updates).

## Step 6: Screenshots Present

```bash
asc localizations list --version "VERSION_ID"
```

Each localization must have screenshots for required device sizes. Upload via `asc screenshots upload` if missing.

## Step 7: App Info Localizations (Privacy Policy)

```bash
asc app-infos list --app "APP_ID"
asc localizations list --app "APP_ID" --type app-info --app-info "APP_INFO_ID"
```

Each locale must have a privacy policy URL set.

## Step 8: Privacy Manifest

The app bundle must include a `PrivacyInfo.xcprivacy` (Flutter: `ios/Runner/PrivacyInfo.xcprivacy`, added to the Runner target) that declares an approved reason for every required-reason API the app's code uses (for example UserDefaults, file timestamp, system boot time, disk space), any tracking domains, and collected data types. Since 1 May 2024 App Store Connect rejects uploads of new or updated apps that use a listed API without an approved reason. Third-party SDKs on Apple's commonly used SDK list must ship their own privacy manifest (and a signature when added as a binary dependency): use a version that does. Keep the manifest consistent with the App Privacy details in App Store Connect.

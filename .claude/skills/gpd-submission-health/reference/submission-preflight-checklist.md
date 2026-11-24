# Google Play Submission Preflight Checklist

Complete all 6 steps before releasing to production track.

## Step 1: Validate Edit (if using edit lifecycle)

Edit must validate without errors before commit.

```bash
gpd publish edit validate EDIT_ID --package com.example.app
```

Expected: no validation errors in output. If errors exist — fix before proceeding.

## Step 2: Confirm Release Status

Release status and version code must match the intended build.

```bash
gpd publish status --package com.example.app --track production
```

Check:
- Release status is expected (`draft`, `inProgress`, or `completed`)
- Version code matches the uploaded build
- No unexpected releases on the track

## Step 3: Verify Store Listing Metadata

All required metadata fields must be present for all active locales.

```bash
gpd publish listing get --package com.example.app
gpd publish details get --package com.example.app
```

Required fields per locale:
- Title (≤ 30 characters)
- Short description (≤ 80 characters)
- Full description (≤ 4000 characters)
- Contact email

## Step 4: Verify Screenshots and Assets

All required screenshot types must be uploaded for each active locale.

```bash
gpd publish images list phoneScreenshots --package com.example.app --locale en-US
gpd publish assets spec
```

Required asset types:
- Phone screenshots (minimum 2, maximum 8)
- Feature graphic (1024 × 500 px)
- App icon (512 × 512 px)

Upload missing assets:
```bash
gpd publish images upload icon icon.png --package com.example.app --locale en-US
gpd publish assets upload ./assets --package com.example.app
```

## Step 5: Upload Deobfuscation Mapping (if applicable)

Required if your build uses ProGuard or R8 obfuscation.

```bash
gpd publish deobfuscation upload mapping.txt \
  --package com.example.app \
  --type proguard \
  --version-code 123
```

Only needed if obfuscation is enabled. Skip if your build does not use ProGuard/R8.

## Step 6: Build and Policy Requirements

Confirm in the release build and Play Console (no single gpd command covers these):
- Release build is not debuggable: `flutter build appbundle --release` (never `--debug`); no `android:debuggable="true"` in the merged manifest.
- Target API level meets Play's current requirement. Checked 2026-11-24 (developer.android.com/google/play/requirements/target-sdk): since 31 Aug 2026, new apps and updates must target Android 16 (API 36) or higher (Wear OS / Automotive: API 35; TV / XR: API 34); extension available to 1 Nov 2026. Re-check the page before each release; the requirement moves yearly.
- Play App Signing enrolled (upload key separate from the app signing key).
- Privacy policy URL set (App content).
- Content rating questionnaire completed.
- The AAB was built once with `--obfuscate --split-debug-info=build/symbols`, the symbols are kept with that artifact for reading stack traces, and the R8 mapping is uploaded (Step 5); see `deployment-ci-cd/reference/flutter-ci.md`.

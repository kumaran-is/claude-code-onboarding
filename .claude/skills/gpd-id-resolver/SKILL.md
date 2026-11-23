---
name: gpd-id-resolver
description: "Resolve Google Play identifiers (package, track, version code, product, subscription, base plan, offer) with the gpd CLI. Use when a gpd command needs an exact ID or value."
allowed-tools: Bash, Read
metadata:
  triggers: resolve ID, package name, track name, version code, product ID, subscription ID, Google Play ID, gpd identifier, tester group, offer ID, base plan ID
  related-skills: gpd-cli-usage, gpd-release-flow, gpd-betagroups, gpd-submission-health, gpd-build-lifecycle
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# GPD ID Resolver

## Iron Law

**NEVER PASS A HUMAN-READABLE NAME TO A GPD COMMAND THAT REQUIRES AN EXACT ID OR PACKAGE NAME — RESOLVE IT FIRST**

Always pass `--package` explicitly. Use `--all` on list commands to avoid missing items.

## Package name (app ID)
- Package name is the primary identifier: `com.example.app`.
- Always pass `--package` explicitly for deterministic results.

## Track names
- Common tracks: `internal`, `alpha`, `beta`, `production`.
- List tracks:
  - `gpd publish tracks --package com.example.app`

## Version codes and release status
- Use release status to find version codes on a track:
  - `gpd publish status --package com.example.app --track production`

## Tester groups
- List testers by track:
  - `gpd publish testers list --package com.example.app --track internal`

## Monetization IDs
- Products:
  - `gpd monetization products list --package com.example.app`
  - `gpd monetization products get sku123 --package com.example.app`
- One-time products:
  - `gpd monetization onetimeproducts list --package com.example.app`
- Subscriptions:
  - `gpd monetization subscriptions list --package com.example.app`
  - `gpd monetization subscriptions get sub123 --package com.example.app`
- Base plans and offers:
  - `gpd monetization baseplans migrate-prices --package com.example.app sub123 plan456 --region-code US --price-micros 9990000`
  - `gpd monetization offers list --package com.example.app sub123 plan456`

## Permissions IDs
- Developer users:
  - `gpd permissions users list --developer-id DEV_ID`
- App grants:
  - `gpd permissions grants create --package com.example.app --email user@example.com --app-permissions CAN_REPLY_TO_REVIEWS`

## Anti-Patterns

- **Don't pass a human-readable app name where a package name is required.** Google Play commands require the exact package identifier (e.g. `com.example.app`), not the display name — using a display name silently fails or matches the wrong app.
- **Don't rely on default pagination when listing monetization products or subscriptions.** Use `--all` to avoid missing items; a truncated list means resolving the wrong or incomplete ID set.
- **Don't hard-code version codes across sessions.** Version codes change with each upload; always resolve the current version code via `gpd publish status` before operating on a specific release.

## Verify

After resolving any ID:
- Echo the resolved value and confirm it matches the expected pattern before passing it to a subsequent command (e.g. package names must match `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`).
- For monetization IDs, run `gpd monetization products get <sku> --package com.example.app` to confirm the ID is active and not archived before using it in pricing or offer operations.

## Output tips
- JSON is default; use `--pretty` for debugging.
- Use `--all` on list commands to avoid missing items.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| gpd CLI help | `gpd publish --help`, `gpd monetization --help` | Discover list/filter flags for each entity type |
| gpd output formats | `--pretty` for debugging, default JSON for scripting | Machine-parseable ID extraction |

---
name: revenuecat
description: Use when integrating RevenueCat in-app subscriptions in Flutter apps — entitlements, offerings, paywalls, purchases_flutter SDK, or Stripe backend sync. Load before writing any RevenueCat or IAP code. Query the RevenueCat MCP server for API verification.
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: RevenueCat, in-app purchase, IAP, entitlement, offering, paywall, subscription, StoreKit, Google Play Billing, purchases_flutter
  related-skills: stripe, flutter-mobile
  domain: payments
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-03-30"
---

## Iron Law

**NO ENTITLEMENT CHECK WITHOUT REVENUECAT SDK — never roll your own subscription validation; always delegate to RevenueCat's server-side receipt verification**

# RevenueCat In-App Subscription Skill

## MCP Server

The RevenueCat MCP server is configured in `.mcp.json` as a remote HTTP MCP at `https://mcp.revenuecat.ai/mcp`.

**Setup command (already configured in .mcp.json):**
```bash
claude mcp add --transport http revenuecat https://mcp.revenuecat.ai/mcp --header "Authorization: Bearer ${REVENUECAT_API_V2_SECRET_KEY}"
```

**Authentication options:**
- **OAuth (recommended for Claude)** — seamless browser-based auth, no API key management
- **API v2 Secret Key** — pass via `Authorization: Bearer <key>` header (configured in .mcp.json)

**Claude Code Plugin (alternative):**
```bash
curl -fsSL https://raw.githubusercontent.com/RevenueCat/rc-claude-code-plugin/main/install.sh | bash
```
Provides slash commands: `/rc:status`, `/rc:apikey`, `/rc:create-product`, `/rc:create-app`
Plus agents: Project Bootstrap Agent, Troubleshooting Agent

**Recommended:** Create a dedicated API v2 secret key for the MCP server to keep credentials organized.

**Fallback:** `context7` MCP → resolve `purchases_flutter` library docs.

### Available MCP Tools (26 total)

**Project Management (1 tool):**

| Tool | Description |
|------|-------------|
| `get_project` | Retrieve RevenueCat project details |

**App Management (6 tools):**

| Tool | Description |
|------|-------------|
| `list_apps` | List all apps in a project (with pagination) |
| `get_app` | Retrieve details for a specific app |
| `create_app` | Create a new app in the project |
| `update_app` | Update an existing app's details |
| `delete_app` | Delete an app from the project |
| `list_app_api_keys` | List public API keys for an app |

**Product Management (2 tools):**

| Tool | Description |
|------|-------------|
| `list_products` | List all products in a project |
| `create_product` | Create a new product |

**Entitlement Management (7 tools):**

| Tool | Description |
|------|-------------|
| `list_entitlements` | List all entitlements in a project |
| `get_entitlement` | Retrieve details for a specific entitlement |
| `create_entitlement` | Create a new entitlement |
| `update_entitlement` | Update an existing entitlement |
| `delete_entitlement` | Delete an entitlement |
| `list_entitlement_products` | List products attached to an entitlement |
| `attach_products_to_entitlement` | Attach products to an entitlement |
| `detach_products_from_entitlement` | Detach products from an entitlement |

**Offering & Package Management (5 tools):**

| Tool | Description |
|------|-------------|
| `list_offerings` | List all offerings in a project |
| `create_offering` | Create a new offering |
| `update_offering` | Update an existing offering |
| `list_packages` | List packages for an offering |
| `create_package` | Create a new package for an offering |

**Customer Management (additional tools):**

| Tool | Description |
|------|-------------|
| `get_customer` | Retrieve subscriber/customer info |
| `list_customer_active_entitlements` | List active entitlements for a customer |

## Context

RevenueCat manages mobile subscription entitlements for Flutter apps. A typical setup might include:
- **Primary app** — Pro and Growth subscription tiers
- **Companion app** — Free tier (included with primary subscription)
- **Partner app** — Free tier with optional premium features

Stripe is the payment processor; RevenueCat sits on top as the entitlement/subscription management layer. RevenueCat handles App Store and Google Play receipt validation, cross-platform entitlement sync, and subscription analytics.

## Architecture Constraints

- **RevenueCat SDK in Flutter only** — `purchases_flutter` package in all 3 apps
- **Stripe as backend processor** — RevenueCat connects to Stripe for web subscriptions; App Store/Google Play for mobile
- **Server-side entitlement checks** — backend services verify entitlements via RevenueCat REST API, not client claims
- **Single source of truth** — RevenueCat is the canonical source for "does this user have access to X?"
- **No direct StoreKit/BillingClient code** — RevenueCat SDK abstracts all store interactions
- **API v2 Secret Key** — use `REVENUECAT_API_V2_SECRET_KEY` for MCP server and server-side API calls
- **Environment variables** — `REVENUECAT_API_KEY_IOS`, `REVENUECAT_API_KEY_ANDROID`, `REVENUECAT_API_V2_SECRET_KEY` (server-side)

## Entitlement Model

| Entitlement ID | Grants Access To | Tiers |
|----------------|------------------|-------|
| `pro` | All premium features of the primary app | Pro, Growth |
| `partner_premium` | Premium features of the partner app | Partner Premium |
| `basic_access` | Core features with usage limits | Free (default) |

## Offerings Structure

```
default_offering/
├── $rc_monthly/
│   ├── pro_monthly               (price set in the stores)
│   └── growth_monthly
├── $rc_annual/
│   ├── pro_annual                (annual discount set in the stores)
│   └── growth_annual
└── partner_premium/
    └── partner_premium_monthly
```

## Code Conventions

### Flutter (Client-Side)

`purchases_flutter` 11.0.4 (pub floor Flutter >= 3.22; Android `minSdk 24`, iOS 13.0 from the plugin sources). Compiled with `flutter analyze` at zero issues on Flutter 3.50.1 / Dart 3.14.0 together with the FlutterFire family and `flutter_stripe` 15.0.0; store purchases themselves are NOT RUN (they need store sandbox accounts). `purchasePackage`, `purchaseProduct` and `purchaseStoreProduct` are deprecated in favour of `purchase(PurchaseParams)`.

```dart
import 'dart:io' show Platform;

import 'package:flutter/services.dart';
import 'package:logging/logging.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

final _log = Logger('RevenueCat');

/// Public SDK keys (appl_/goog_) are client keys; the v2 secret key stays on the server.
Future<void> initRevenueCat() => Purchases.configure(
  PurchasesConfiguration(
    Platform.isIOS
        ? const String.fromEnvironment('REVENUECAT_API_KEY_IOS')
        : const String.fromEnvironment('REVENUECAT_API_KEY_ANDROID'),
  ),
);

/// Call after sign-in with the same stable id the backend uses.
Future<void> identifyUser(String userId) => Purchases.logIn(userId);

/// Call from the sign-out coordinator so entitlements do not leak to the next user.
Future<void> resetUser() => Purchases.logOut();

sealed class PurchaseOutcome {
  const PurchaseOutcome();
}

final class Purchased extends PurchaseOutcome {
  const Purchased({required this.hasPro});
  final bool hasPro;
}

final class PurchaseCancelled extends PurchaseOutcome {
  const PurchaseCancelled();
}

final class PurchaseFailed extends PurchaseOutcome {
  const PurchaseFailed(this.code);
  final PurchasesErrorCode code;
}

Future<PurchaseOutcome> buy(Package package) async {
  try {
    final result = await Purchases.purchase(PurchaseParams.package(package));
    return Purchased(
      hasPro: result.customerInfo.entitlements.active.containsKey('pro'),
    );
  } on PlatformException catch (e) {
    // The SDK throws PlatformException; map it to a PurchasesErrorCode.
    final code = PurchasesErrorHelper.getErrorCode(e);
    if (code == PurchasesErrorCode.purchaseCancelledError) {
      return const PurchaseCancelled();
    }
    _log.warning('purchase failed (${code.name})');
    return PurchaseFailed(code);
  }
}
```

The paywall reads `Purchases.getOfferings()`; a `null` `offerings.current` is a visible "plans unavailable" state with a retry, never an empty screen.

### Riverpod Provider Pattern

```dart
/// Entitlement for UX gating only; the backend re-checks before granting access.
/// Errors stay AsyncError: the paywall shows "could not verify", never "free".
@riverpod
Future<bool> hasPro(Ref ref) async {
  final info = await Purchases.getCustomerInfo();
  return info.entitlements.active.containsKey('pro');
}
```

After a purchase, `ref.invalidate(hasProProvider)`. Riverpod 3 passes a plain `Ref` (no generated `HasProEntitlementRef`), and a `whenOrNull(...) ?? false` that turns an error into "not entitled" is a silent failure.

### Python (Server-Side Verification)

```python
# Backend entitlement verification via RevenueCat REST API v2
import httpx

REVENUECAT_API_SECRET = settings.REVENUECAT_API_V2_SECRET_KEY
REVENUECAT_BASE_URL = "https://api.revenuecat.com/v2"

async def verify_entitlement(user_id: str, entitlement_id: str) -> bool:
    """Server-side entitlement check — never trust client claims."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{REVENUECAT_BASE_URL}/projects/{PROJECT_ID}/subscribers/{user_id}",
            headers={
                "Authorization": f"Bearer {REVENUECAT_API_SECRET}",
                "Content-Type": "application/json",
            },
        )
        if response.status_code != 200:
            logger.error(f"RevenueCat API error: {response.status_code}")
            return False

        subscriber = response.json()["subscriber"]
        entitlement = subscriber.get("entitlements", {}).get(entitlement_id)
        if not entitlement:
            return False

        # Check expiration
        expires = entitlement.get("expires_date")
        if expires and datetime.fromisoformat(expires) < datetime.now(UTC):
            return False

        return True
```

## Webhook Integration (RevenueCat → Backend)

RevenueCat sends server-to-server webhooks for subscription events:

| Event | Action |
|-------|--------|
| `INITIAL_PURCHASE` | Create/upgrade user tier in Cloud SQL |
| `RENEWAL` | Extend subscription, log payment |
| `CANCELLATION` | Schedule downgrade at period end |
| `EXPIRATION` | Downgrade to Free tier |
| `BILLING_ISSUE` | Flag account, trigger dunning email |
| `PRODUCT_CHANGE` | Update tier (Pro ↔ Growth) |
| `TRANSFER` | Handle family sharing / account transfer |

```python
@router.post("/webhooks/revenuecat")
async def revenuecat_webhook(request: Request):
    payload = await request.json()
    # Verify webhook authorization header
    auth = request.headers.get("Authorization")
    if auth != f"Bearer {settings.REVENUECAT_WEBHOOK_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    event_type = payload.get("event", {}).get("type")
    app_user_id = payload.get("event", {}).get("app_user_id")

    match event_type:
        case "INITIAL_PURCHASE" | "RENEWAL":
            await activate_subscription(app_user_id, payload)
        case "EXPIRATION" | "CANCELLATION":
            await deactivate_subscription(app_user_id, payload)
        case "BILLING_ISSUE":
            await flag_billing_issue(app_user_id, payload)

    return {"status": "ok"}
```

## Testing

```dart
// Mock RevenueCat in Flutter widget tests
class MockPurchases extends Mock implements Purchases {}

// Use RevenueCat sandbox for integration tests
// iOS: App Store Sandbox accounts
// Android: Google Play test tracks
```

```python
# Mock RevenueCat API in Python tests
@pytest.fixture
def mock_revenuecat(httpx_mock):
    httpx_mock.add_response(
        url="https://api.revenuecat.com/v2/projects/test-project/subscribers/test-user",
        json={
            "subscriber": {
                "entitlements": {
                    "pro": {
                        "expires_date": "2027-01-01T00:00:00Z",
                        "purchase_date": "2026-01-01T00:00:00Z",
                    }
                }
            }
        },
    )
```

## Security Checklist

- [ ] RevenueCat API keys stored in environment variables only
- [ ] Dedicated API v2 secret key created for MCP server (not shared with other services)
- [ ] Server-side entitlement verification for all gated features (never trust client)
- [ ] Webhook authorization header verified on all RevenueCat webhook endpoints
- [ ] User identification via `Purchases.logIn()` after authentication
- [ ] `Purchases.logOut()` on user sign-out to prevent entitlement leaking
- [ ] Sandbox/test keys in dev/staging, production keys in production only
- [ ] No direct StoreKit or Google Play Billing API calls — use RevenueCat SDK only

## Reference Files

**Paywall UI patterns**: See `reference/revenuecat-paywalls.md` (when populated) for paywall screen templates, A/B testing configuration, promotional offer setup, and conversion tracking. Until then, query the `revenuecat` MCP or `context7` MCP for `purchases_flutter` docs.

**Stripe + RevenueCat sync**: See `reference/revenuecat-stripe-sync.md` (when populated) for cross-platform subscription management, web-to-mobile migration, and entitlement reconciliation patterns. Until then, query the `revenuecat` MCP for current entitlement/offering configuration.

## Process

1. **Query RevenueCat MCP** for current API and SDK signatures before writing any integration code — use `list_entitlements`, `list_offerings` etc. to verify current state
2. **Configure offerings/entitlements** via MCP tools (`create_entitlement`, `create_offering`, `create_package`) or RevenueCat dashboard
3. **Implement server-side verification** before client-side feature gates
4. **Test with sandbox accounts** — never use production credentials in development
5. **Webhook handler** for subscription lifecycle events → sync to Cloud SQL
6. **Use API v2** — all server-side code should use RevenueCat REST API v2, not v1

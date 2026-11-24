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
last-reviewed: "2026-11-23"
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

REST API v2 (`GET /v2/projects/{project_id}/customers/{customer_id}`, response `active_entitlements.items[]` with `entitlement_id` and `expires_at` in ms; RevenueCat API v2 docs, 2026-11-23). Executed against an `httpx.MockTransport` (Python 3.14.10, httpx 0.28.1): active, lifetime (`expires_at: null`), expired, other entitlement, unknown customer -> False, and a 503 raises instead of returning "not entitled". Mocked: not live-provider validation.

```python
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request, status

logger = structlog.get_logger(__name__)
router = APIRouter()
RC_V2 = "https://api.revenuecat.com/v2"


class EntitlementLookupError(RuntimeError):
    """RevenueCat unreachable or refused: the caller decides (fail closed), never 'not entitled'."""


async def has_active_entitlement(http: httpx.AsyncClient, *, project_id: str, customer_id: str,
                                 entitlement_id: str, api_key: str) -> bool:
    """entitlement_id is RevenueCat's entitlement id (entl...), not the lookup key shown in the app."""
    response = await http.get(
        f"{RC_V2}/projects/{project_id}/customers/{customer_id}",
        headers={"Authorization": f"Bearer {api_key}"},  # v2 secret key, customer_information:customers:read
        timeout=5.0,
    )
    if response.status_code == 404:
        return False  # unknown customer: genuinely no entitlement
    if response.status_code != 200:
        logger.error("revenuecat_lookup_failed", status=response.status_code)
        raise EntitlementLookupError(f"RevenueCat returned {response.status_code}")
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    page = response.json()["active_entitlements"]  # first page; follow next_page for many entitlements
    return any(
        item["entitlement_id"] == entitlement_id
        and (item["expires_at"] is None or item["expires_at"] > now_ms)
        for item in page["items"]
    )
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

Scheme (RevenueCat webhook docs, re-read 2026-11-23): with HMAC signing enabled on the integration, each delivery carries `X-RevenueCat-Webhook-Signature: t=<unix_timestamp>,v1=<hmac_sha256_hex>`, computed over `"<timestamp>.<raw_json_body>"` with the integration's signing secret; verify the raw bytes before parsing. The page states neither the secret's length nor the hex case of `v1` (its examples use `hexdigest()`), so the code requires only a 16-character minimum and accepts either case. Enable HMAC signing before deploying this handler; this skill ships no `Authorization`-header-only variant.

Executed (FastAPI 0.165.0 via `httpx.ASGITransport`, pydantic-settings 2.16.3, SQLAlchemy 2.1.9 async on SQLite/aiosqlite; the same `INSERT ... ON CONFLICT DO NOTHING RETURNING` runs on PostgreSQL), 14 tests: valid HMAC -> processed; same event id again -> duplicate; wrong secret, missing header, a `t` 301 s old, a body changed after signing, a non-ASCII `v1` -> 401 (not 500); an empty or 15-character secret fails at boot (`ValidationError`) and a 16-character one boots; an upper-case `v1` is accepted and the secret never appears in `repr`; handler failure -> 500 with its writes rolled back, then the retry processes it; a request cancelled mid-handler leaves no event row and the redelivery processes it. Controls (each turned the matching test red): no `min_length` -> an empty secret boots; no `.lower()` -> an upper-case `v1` is rejected; `compare_digest` on `str` without the format check -> 500 on a non-ASCII `v1`; committing the event-id insert in its own transaction -> the retry answers "duplicate" and the event is lost (a claim released in `except Exception` has the same hole: `CancelledError` is not an `Exception`). Engine: `create_async_engine(..., hide_parameters=True)`; external calls go through an outbox row in the same transaction (`python-dev/reference/reliability-idempotency-retries-outbox.md` §1, §4).

```python
# same module as has_active_entitlement, plus:
import re

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class WebhookSettings(BaseSettings):
    # SecretStr: never printed in reprs/logs. RevenueCat does not document the secret's length, so
    # min_length=16 only rejects empty/placeholder values (with an empty HMAC key anyone can sign
    # INITIAL_PURCHASE events, and no SDK refuses it for you)
    revenuecat_webhook_signing_secret: SecretStr = Field(min_length=16)


_HEX64 = re.compile(r"[0-9a-fA-F]{64}")  # hex case is not documented: accept both


def verify_signature(raw_body: bytes, header: str | None, secret: SecretStr, tolerance_s: int = 300) -> None:
    """Header `t=<unix>,v1=<hex HMAC-SHA256 of f"{t}.{raw body}">` (RevenueCat webhook docs)."""
    if not header:
        raise ValueError("missing signature")
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    t, v1 = parts.get("t", ""), parts.get("v1", "")
    if not t.isdigit() or abs(time.time() - int(t)) > tolerance_s:
        raise ValueError("stale or malformed timestamp")
    if not _HEX64.fullmatch(v1):  # rejects non-ASCII / wrong length before comparing
        raise ValueError("malformed signature")
    key = secret.get_secret_value().encode()  # unwrapped only here
    expected = hmac.new(key, f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode(), v1.lower().encode()):  # bytes on both sides
        raise ValueError("bad signature")


CLAIM = text(
    "INSERT INTO revenuecat_events (event_id) VALUES (:id) ON CONFLICT DO NOTHING RETURNING event_id"
)


@router.post("/webhooks/revenuecat")
async def revenuecat_webhook(request: Request) -> dict[str, str]:
    raw = await request.body()  # verify the raw bytes before parsing
    try:
        verify_signature(raw, request.headers.get("X-RevenueCat-Webhook-Signature"),
                         request.app.state.settings.revenuecat_webhook_signing_secret)  # WebhookSettings
    except ValueError as exc:
        logger.warning("revenuecat_signature_rejected")  # no payload, no header in logs
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized") from exc
    event = json.loads(raw)["event"]
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    try:
        # ONE transaction: event-id insert + the handler's writes (+ outbox rows for external calls).
        # Error, cancellation or kill rolls all of it back, so the redelivery (same id) is processed.
        async with sessions.begin() as session:
            if (await session.execute(CLAIM, {"id": event["id"]})).first() is None:
                return {"status": "duplicate"}  # 200: RevenueCat stops retrying
            await request.app.state.entitlements.apply(session, event)
    except Exception as exc:
        logger.error("revenuecat_event_failed", event_id=event["id"], error_type=type(exc).__name__)
        raise  # non-200: RevenueCat retries up to 5 times over ~80 minutes
    return {"status": "processed"}
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
# Python tests: inject an httpx.AsyncClient with a MockTransport (no extra plugin)
def client_for(status: int, items: list[dict[str, object]]) -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v2/projects/proj1/customers/u1"
        return httpx.Response(status, json={"active_entitlements": {"items": items, "next_page": None}})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
```

## Security Checklist

- [ ] RevenueCat API keys stored in environment variables only
- [ ] Dedicated API v2 secret key created for MCP server (not shared with other services)
- [ ] Server-side entitlement verification for all gated features (never trust client)
- [ ] HMAC signing enabled; `X-RevenueCat-Webhook-Signature` verified on the raw body (bytes `compare_digest`, 5 min tolerance); signing secret is `SecretStr` with `min_length=16`
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

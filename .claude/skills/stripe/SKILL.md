---
name: stripe
description: Use when integrating Stripe payments — subscription billing, customer management, payment links, webhooks, Stripe Connect vendor payouts, or invoicing. Load before writing any Stripe API code. Query the Stripe MCP server for API verification.
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: Stripe, payment, billing, subscription, checkout, invoice, payout, payment link, pricing, Stripe Connect, webhook
  related-skills: revenuecat, python-dev, flutter-mobile
  domain: payments
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

**NO STRIPE API CALL WITHOUT WEBHOOK VERIFICATION — every payment mutation must have a corresponding webhook handler; never trust client-side payment confirmation alone**

# Stripe Payment Integration Skill

## MCP Server

`.mcp.json` runs the official `@stripe/mcp@0.3.4` package (stdio). Stripe has deprecated it in favour of the hosted server, so prefer that when you can:

```bash
claude mcp add --transport http stripe https://mcp.stripe.com   # OAuth, no key in config
```

**Accepted arguments (0.3.4 package source):** `--api-key` and `--stripe-account` only. `--tools` has been removed: it prints a warning and has no effect, and any other argument is an error. Pass the key through the `STRIPE_SECRET_KEY` env var, never `--api-key` (argv shows up in the process list).

**The key is the tool allowlist.** What the server can do is set by a Restricted API Key (`rk_test_…`) that grants only the resources the task needs: Dashboard → Developers → API keys → Restricted keys. Use test mode for development.

**Tools exposed (check `/mcp` for the current list):** `search_stripe_documentation`, `get_stripe_account_info`, `stripe_api_search`, `stripe_api_details`, `stripe_api_read`, `stripe_implementation_planner`, `stripe_analytics`, `stripe_api_write`, `send_stripe_feedback`.

**Claude Code permissions (`.claude/settings.json`):** the read-only tools are allowed. `stripe_api_write` and `send_stripe_feedback` are always **ask**. `stripe_analytics` falls through to the default prompt.

**Fallback:** `context7` MCP → resolve `stripe` library docs.

## Context

Stripe is used for:
- **Subscription billing** — multiple tiers (e.g., Free, Pro, Growth)
- **Vendor payouts** — Stripe Connect (Express accounts) for paying service vendors
- **One-time charges** — service invoicing
- RevenueCat handles mobile in-app subscription entitlements; Stripe is the backend payment processor

## Architecture Constraints

- **Backend only** — all Stripe API calls happen in backend services (e.g., Python/FastAPI), never from Flutter clients
- **Webhook-first** — use Stripe webhooks as the source of truth for payment state, not API polling
- **Idempotency keys** — every mutating call passes a deterministic key from business ids in `options={"idempotency_key": ...}`. The SDK generates a random key per call and reuses it only across its OWN retries, so an application-level retry (queue redelivery, Temporal activity retry) without your key creates a second object
- **Stripe Connect Express** — vendors onboard via Express accounts; your app is the platform
- **No PCI data in your DB** — never store card numbers, CVVs, or raw payment tokens in Cloud SQL
- **Restricted API Keys** — use `rk_*` keys scoped to minimum required permissions, not `sk_*` root keys
- **Environment variables** — `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_CLIENT_ID`

## Code Conventions

### Python (FastAPI backend)

Pin: `uv add "stripe==17.1.0"` (PyPI, 2026-11-23; exact pin + lockfile). Client (executed against a local fake API): one `StripeClient` per process, built from settings.

```python
client = stripe.StripeClient(
    settings.stripe_secret_key.get_secret_value(),  # restricted rk_* key
    max_network_retries=2,  # StripeClient default is 0: one attempt, no retry (the module-level global's 2 does not apply)
)
customer = client.v1.customers.create(
    params={"email": user.email, "metadata": {"user_id": str(user.id)}},
    options={"idempotency_key": f"customer-create-{user.id}"},
)
```

- Resources live under `client.v1.*` / `client.v2.*`; `client.customers` and the other un-versioned accessors emit `DeprecationWarning`. Do not use the module-level `stripe.Customer.create(...)` / `stripe.api_key` style in new code.
- API version: stripe 17.1.0 pins `2026-11-18.endive` (`stripe.api_version`). Upgrade the SDK and the webhook endpoint's API version together; pass `stripe_version=` only to hold an older version during a migration.
- SDK retries (409, 5xx, `Stripe-Should-Retry`) reuse the call's idempotency key; executed: a 503 on `/v1/transfers` retried with the same caller key.


Webhook endpoint (stripe 17.1.0, Python 3.14.10, FastAPI 0.165.0, SQLAlchemy 2.1.9 + asyncpg 0.32.0
on PostgreSQL 18.7; 12 tests, each check with a mutation that turns it red). Verify on the **raw**
body, then record the event id **and** apply the effects in one database transaction, so an error, a
cancelled request or a killed process rolls both back and Stripe's redelivery runs them again:

```python
from typing import Annotated

import stripe
import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy.dialects.postgresql import insert

log = structlog.get_logger(__name__)
router = APIRouter()
# client: the single StripeClient built above. Engine: create_async_engine(dsn, hide_parameters=True)
# so a DBAPIError's text never carries bound values. StripeEvent: table with id (primary key), type.


def verify_event(payload: bytes, sig: str | None, secrets: list[str]) -> stripe.Event:
    """secrets: current first, then the previous one while a rolled secret is still active."""
    for secret in secrets[:-1]:
        try:
            return client.construct_event(payload, sig, secret, tolerance=300)
        except stripe.SignatureVerificationError:
            continue
    return client.construct_event(payload, sig, secrets[-1], tolerance=300)  # its error propagates


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request, stripe_signature: Annotated[str | None, Header()] = None
) -> dict[str, str]:
    payload = await request.body()          # raw bytes; parsing and re-serialising breaks the HMAC
    secrets = [s.get_secret_value() for s in settings.stripe_webhook_secrets]
    try:
        event = verify_event(payload, stripe_signature, secrets)
    except stripe.SignatureVerificationError as exc:
        log.warning("stripe_signature_rejected")          # never log the payload or the header
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from exc
    handler = HANDLERS.get(event.type)       # subscribe the endpoint only to these types
    if handler is None:
        return {"status": "ignored"}
    try:
        async with sessions() as session, session.begin():
            claimed = await session.scalar(
                insert(StripeEvent).values(id=event.id, type=event.type)
                .on_conflict_do_nothing(index_elements=[StripeEvent.id]).returning(StripeEvent.id))
            if claimed is None:
                return {"status": "duplicate"}           # 200 stops Stripe's retries
            # database writes only; an email or API call is an outbox row written here
            await handler(event, session)
    except Exception as exc:
        # the type only: exception text and tracebacks can carry SQL parameters or request data
        log.error("stripe_event_failed", event_id=event.id, event_type=event.type,
                  error_type=type(exc).__qualname__)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Event not processed") from exc
    return {"status": "processed"}
```

Executed: valid event processed once across two deliveries (one event row, one effect row); wrong
secret, missing header, a body changed after signing and a timestamp 301 s old → 400; an event
signed with the previous secret → processed; a handler failing **after** writing its effect → 500
with neither row left, then the redelivery processed it; a request cancelled mid-handler left no rows
and the redelivery processed it; the failure log carried `error_type` only, no message or traceback;
with `hide_parameters=True` a failing INSERT's error omitted the bound values. Mutations: claim
committed in its own transaction (the pattern of claim, then effects, then release on `Exception`) →
the cancellation and rollback tests red — `CancelledError` is not an `Exception`, so the claim stayed
and every redelivery answered "duplicate"; `log.exception` → red; no `hide_parameters` → red.
`tolerance=0` **disables** the replay check (the SDK tests `if tolerance and ...`): a year-old
signature verified. The signature window bounds replays to 5 minutes; the event-id row closes that
window (table design: `python-dev/reference/reliability-idempotency-retries-outbox.md` §1). For
heavy or external work, store the verified event and return 200, then process it from a queue
(outbox: same file; queue-consumer dedupe: §7a). Re-read amounts and status from the API
(`client.v1.*.retrieve`) before fulfilment when the event could be stale.

### Python (Agent Toolkit / agents)

`stripe-agent-toolkit` 0.7.1 (Python >= 3.11, PyPI 2026-11-23) ships adapters for OpenAI Agents SDK, LangChain, CrewAI and Strands only (e.g. `from stripe_agent_toolkit.langchain.toolkit import create_stripe_agent_toolkit`, async); the top-level package does not export the factory and there is **no ADK adapter**. For a Google ADK agent, connect the Stripe MCP server through ADK's MCP toolset (`google-adk` skill) with a restricted key. Either way: the key is the tool allowlist, money-moving tools need human approval (`agentic-ai-dev/reference/tool-execution-safety.md`), and the agent proposes while your backend executes with idempotency keys.

### Flutter (client-side)

Flutter never calls the Stripe API directly: Flutter → your backend (creates the PaymentIntent/SetupIntent, returns `client_secret`) → Payment Sheet → webhook confirms on the backend. `flutter_stripe` 15.0.0 needs Flutter >= 3.47; Android `minSdk 21`/`compileSdk 36`, iOS 15.0 (plugin sources). Compiled with `flutter analyze` at zero issues on Flutter 3.50.1 / Dart 3.14.0, and `flutter build apk --debug` plus an iOS simulator build passed with it in the dependency set; presenting a real sheet is NOT RUN (needs a test-mode backend).

```dart
import 'package:flutter_stripe/flutter_stripe.dart';
import 'package:logging/logging.dart';

final _log = Logger('StripeCheckout');

/// Publishable key only (pk_...). Secret/restricted keys never ship in the app.
Future<void> initStripe() async {
  Stripe.publishableKey = const String.fromEnvironment('STRIPE_PUBLISHABLE_KEY');
  Stripe.merchantIdentifier = 'merchant.com.example.app'; // Apple Pay only
  await Stripe.instance.applySettings();
}

sealed class CheckoutResult {
  const CheckoutResult();
}

final class CheckoutCompleted extends CheckoutResult {
  const CheckoutCompleted();
}

final class CheckoutCancelled extends CheckoutResult {
  const CheckoutCancelled();
}

final class CheckoutFailed extends CheckoutResult {
  const CheckoutFailed(this.code);
  final FailureCode code;
}

/// [clientSecret] comes from YOUR backend, which created the PaymentIntent.
/// "Completed" here is UX only: fulfil the order from the webhook.
Future<CheckoutResult> presentCheckout(String clientSecret) async {
  try {
    await Stripe.instance.initPaymentSheet(
      paymentSheetParameters: SetupPaymentSheetParameters(
        paymentIntentClientSecret: clientSecret,
        merchantDisplayName: 'Example',
      ),
    );
    await Stripe.instance.presentPaymentSheet();
    return const CheckoutCompleted();
  } on StripeException catch (e) {
    if (e.error.code == FailureCode.Canceled) return const CheckoutCancelled();
    _log.warning('payment sheet failed (${e.error.code.name})');
    return CheckoutFailed(e.error.code);
  }
}
```

Android setup (flutter_stripe README): `MainActivity` extends `FlutterFragmentActivity`, and the launch/normal themes descend from `Theme.AppCompat` (the Payment Sheet uses AppCompat and the support fragment manager). Never put a `sk_`/`rk_` key behind `String.fromEnvironment`: defines are compiled into the binary.

## Webhook Events to Handle

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Activate subscription, update user tier in Cloud SQL |
| `invoice.paid` | Record payment, extend subscription period |
| `invoice.payment_failed` | Flag account, send dunning notification |
| `customer.subscription.updated` | Sync plan changes to Cloud SQL + RevenueCat |
| `customer.subscription.deleted` | Downgrade to Free tier, revoke entitlements |
| `account.updated` (Connect) | Update vendor payout account status |
| `transfer.created` (Connect) | Record vendor payout in Cloud SQL |

## Stripe Connect (Vendor Payouts)

New Connect integrations use Accounts v2 (Stripe docs, 2026-11-23). Executed with stripe 17.1.0 against a local fake API (`mypy --strict` clean): requests hit `/v2/core/accounts` with the caller key, `/v2/core/account_links`, and `/v1/transfers`, whose 503 was retried with the same key.

```python
def onboard_vendor(client: stripe.StripeClient, *, vendor_id: str, email: str, base_url: str) -> str:
    account = client.v2.core.accounts.create(
        params={
            "contact_email": email,
            "dashboard": "express",
            "identity": {"country": "US"},
            "defaults": {"responsibilities": {"fees_collector": "application", "losses_collector": "application"}},
            "configuration": {
                "recipient": {"capabilities": {"stripe_balance": {"stripe_transfers": {"requested": True}}}}
            },
            "metadata": {"vendor_id": vendor_id},
        },
        options={"idempotency_key": f"vendor-onboard-{vendor_id}"},
    )
    link = client.v2.core.account_links.create(
        params={
            "account": account.id,
            "use_case": {
                "type": "account_onboarding",
                "account_onboarding": {
                    "refresh_url": f"{base_url}/vendors/stripe/refresh",
                    "return_url": f"{base_url}/vendors/stripe/return",
                },
            },
        }
    )
    return link.url  # short-lived: create a fresh link on every refresh_url hit


def pay_vendor(client: stripe.StripeClient, *, ticket_id: str, vendor_id: str, account_id: str, amount_cents: int) -> str:
    transfer = client.v1.transfers.create(
        params={"amount": amount_cents, "currency": "usd", "destination": account_id, "transfer_group": f"ticket-{ticket_id}"},
        options={"idempotency_key": f"payout-ticket-{ticket_id}-vendor-{vendor_id}"},
    )
    return transfer.id
```

Store `account.id` against the vendor and read onboarding state from the account (or its webhook events), never from the return URL.

## Testing

```python
# Use Stripe test mode keys in development/CI
# STRIPE_SECRET_KEY=sk_test_... or rk_test_...

# Use Stripe CLI for local webhook testing:
# stripe listen --forward-to localhost:8000/webhooks/stripe

# Unit tests: inject a fake with the same shape instead of patching module globals
class FakeCustomers:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, object], dict[str, object]]] = []

    def create(self, *, params: dict[str, object], options: dict[str, object]) -> SimpleNamespace:
        self.calls.append((params, options))
        return SimpleNamespace(id="cus_test123")


@pytest.fixture
def stripe_client() -> SimpleNamespace:
    return SimpleNamespace(v1=SimpleNamespace(customers=FakeCustomers()))  # passed where StripeClient is

# assert the idempotency key, not just the call: options["idempotency_key"] == f"customer-create-{user.id}"
# integration tier: stripe-mock or test-mode keys; a mocked client is never live-provider validation
```

## Security Checklist

- [ ] Webhook signature verification on ALL Stripe webhook endpoints, on the raw body, via `client.construct_event`; `tolerance` > 0 (never 0)
- [ ] Event-id row (unique constraint) and the handler's writes in ONE transaction; external calls via outbox rows; duplicates answer 200
- [ ] Failure logs carry the exception type, never `log.exception`/`str(exc)`; engine uses `hide_parameters=True`
- [ ] Signature failures answer 400 and log no payload/header; endpoint subscribed only to handled event types
- [ ] Never log or return `str(SignatureVerificationError)`: in stripe 17.1.0 (`_webhook.py`, `_signature_error_message`) the message can include your secret's length and last 4 characters
- [ ] Webhook secrets are `SecretStr` settings with the previous secret kept only for the roll window
- [ ] Idempotency keys on ALL mutating Stripe API calls
- [ ] No PCI data (card numbers, CVV) stored in Cloud SQL
- [ ] Restricted API Keys (`rk_*`) used instead of root secret keys (`sk_*`)
- [ ] Test mode keys (`sk_test_` / `rk_test_`) in dev/staging, live keys in production only
- [ ] Connect onboarding uses Express-dashboard accounts, not Custom: Accounts v2 `dashboard: "express"` (preferred; `none` replaces Custom); v1 only via controller properties `controller.stripe_dashboard.type="express"`; legacy `type="express"` only for existing integrations
- [ ] All amounts in cents (integer), never floating point dollars
- [ ] MCP server scoped by its Restricted API Key (resources each service needs), key passed via `STRIPE_SECRET_KEY`, not `--api-key`; `--tools` no longer restricts anything

## Reference Files

**Subscription setup and pricing**: See `reference/stripe-subscriptions.md` (when populated) for product/price creation, checkout session flow, subscription lifecycle, dunning configuration, and plan migration patterns. Until then, query the `stripe` MCP `search_stripe_documentation` tool.

**Stripe Connect and vendor payouts**: See `reference/stripe-connect.md` (when populated) for Express account onboarding, transfer creation, payout scheduling, and platform fee configuration. Until then, query the `stripe` MCP `search_stripe_documentation` tool.

## Process

1. **Query Stripe MCP** for current API signatures before writing any Stripe code — use `search_stripe_documentation` tool for API questions
2. **Webhook handler first** — implement the webhook before the API call that triggers it
3. **Idempotency keys** on every mutating call
4. **Test with Stripe CLI** — `stripe listen --forward-to` for local development
5. **Never bypass PCI compliance** — use Payment Sheet / Checkout, never raw card collection
6. **Use Restricted API Keys** — scope permissions to minimum required per service

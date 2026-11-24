# Stripe Payment Integration

> **When to use**: Adding Stripe payments — subscription billing, one-time charges, payment links, Stripe Connect vendor payouts, or webhook handlers
> **Time estimate**: 2–4 hours per integration
> **Prerequisites**: Stripe account, Restricted API Key (`rk_*`), `.env` with `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`

## Overview

Full Stripe payment lifecycle from MCP setup through webhook-first implementation to security-reviewed PR. Backend-only Stripe calls (Python/FastAPI), Flutter Payment Sheet for client UI, webhook as source of truth.

## Phases

### Phase 1 — Load Skill & Verify MCP

**Trigger**: Any task involving Stripe payments
**Action**: Load `stripe` skill (`skills/stripe/SKILL.md`)
**MCP**: `stripe` MCP server (27 tools via `@stripe/mcp`)

**Verify MCP is working**:
```
Use `search_stripe_documentation` tool to query the specific API you need
Use `list_products` / `list_customers` to verify connection
```

**Iron Law**: NO STRIPE API CALL WITHOUT WEBHOOK VERIFICATION

**Gate**: MCP responds, skill loaded, API signatures verified

---

### Phase 2 — Webhook Handler First

**Trigger**: Before implementing any payment mutation
**Principle**: Implement the webhook handler BEFORE the API call that triggers it

**Steps**:
1. Create webhook endpoint in Python/FastAPI
2. Verify the signature on the RAW body with `client.construct_event(payload, sig, secret, tolerance=300)` (`StripeClient`, stripe 17.1.0); 400 on failure, no payload logged
3. Insert the event id (unique key) and apply the handler's database writes in one transaction; a duplicate insert answers 200
4. On any failure the transaction rolls back and the endpoint returns 5xx so Stripe retries; external calls go through an outbox row (a release-in-`except Exception` design strands the claim on cancellation, since `CancelledError` is not an `Exception`)
5. Log event id, type and `error_type` only, never the payload or the exception text (stripe skill: Python webhook endpoint, executed on PostgreSQL)

**Key events**:

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Activate subscription |
| `invoice.paid` | Record payment |
| `invoice.payment_failed` | Trigger dunning |
| `customer.subscription.updated` | Sync plan changes |
| `customer.subscription.deleted` | Downgrade tier |

**Gate**: Webhook handler passes unit test with mocked Stripe events

---

### Phase 3 — Backend API Implementation

**Trigger**: Webhook handlers are in place
**Skill**: `python-dev` (for FastAPI patterns)

**Rules**:
- All Stripe API calls in Python/FastAPI services, never from Flutter
- Idempotency key on every mutating call
- Restricted API Key (`rk_*`), not root secret key
- All amounts in cents (integer), never floating-point dollars
- No PCI data stored in your database

**Steps**:
1. Create customer on signup (`client.v1.customers.create(params=..., options={"idempotency_key": f"customer-create-{user.id}"})`)
2. Create checkout session or payment intent
3. Return `client_secret` to Flutter
4. Stripe processes payment
5. Webhook confirms → update database

**Gate**: API endpoints work end-to-end with Stripe test mode keys

---

### Phase 4 — Flutter Client Integration (if applicable)

**Trigger**: App needs payment UI
**Skill**: `flutter-mobile`

**Pattern**: Flutter → Your Backend → Stripe (never Flutter → Stripe directly)

**Steps**:
1. Call backend to create PaymentIntent/SetupIntent
2. Receive `client_secret` from backend
3. Present Stripe Payment Sheet with `client_secret`
4. Stripe handles PCI-compliant card collection
5. Backend webhook confirms payment

**Gate**: Payment Sheet renders, test payment completes in sandbox

---

### Phase 5 — Stripe Connect (vendor payouts, if applicable)

**Trigger**: Need to pay vendors/contractors
**Skill**: `stripe` (Connect section)

**Steps**:
1. Create the vendor account with Accounts v2 (`client.v2.core.accounts.create`, `dashboard="express"`, recipient `stripe_transfers` capability, deterministic idempotency key)
2. Generate an onboarding link (`client.v2.core.account_links.create`, `use_case.type="account_onboarding"`)
3. Vendor completes onboarding in Stripe-hosted UI; read status from the account, not the return URL
4. Create the transfer after job completion (`client.v1.transfers.create`, key `payout-ticket-{ticket_id}-vendor-{vendor_id}`)
5. Handle `account.updated` and `transfer.created` webhooks

**Gate**: Vendor onboarding flow works, test transfer completes

---

### Phase 6 — Testing

**Local webhook testing**:
```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

**Unit tests**:
- Mock Stripe API calls with `monkeypatch`
- Test webhook signature verification (valid + invalid)
- Test each event handler independently
- Test idempotency (duplicate events handled gracefully)

**Gate**: All tests pass, webhook handler handles duplicate events

---

### Phase 7 — Security Review

**Dispatch**: `security-reviewer` agent
**Checklist** (from `skills/stripe/SKILL.md`):
- [ ] Webhook signature verification on ALL endpoints
- [ ] Idempotency keys on ALL mutating API calls
- [ ] No PCI data in database
- [ ] Restricted API Keys used
- [ ] Test mode keys in dev/staging only
- [ ] All amounts in cents
- [ ] MCP `--tools` flag restricts to needed tools

**Gate**: Security reviewer verdict = no CRITICAL or HIGH findings

---

## Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| Trusting client-side payment confirmation | Always verify via webhook |
| Storing card numbers in database | Use Stripe Payment Sheet / Checkout |
| Using root `sk_*` key | Create Restricted API Key with minimum permissions |
| Floating-point dollar amounts | Always use integer cents |
| Missing idempotency key | `options={"idempotency_key": <business-id key>}` on every mutating call; the SDK's own random key does not survive an application-level retry |
| `StripeClient` without `max_network_retries` | Default is 0 retries: set it explicitly (e.g. 2) |
| Legacy `stripe.Customer.create` / `client.customers` | `client.v1.customers.create` (un-versioned accessors emit `DeprecationWarning`) |
| Not handling webhook retries | Event-id row (unique constraint) and the handler's writes in ONE transaction; duplicates answer 200 |

## Related Workflows

- [revenuecat-subscription-integration.md](revenuecat-subscription-integration.md) — Mobile IAP entitlements (pairs with Stripe)
- [feature-python-fastapi.md](feature-python-fastapi.md) — Backend service patterns
- [feature-flutter-mobile.md](feature-flutter-mobile.md) — Flutter client patterns
- [security-audit.md](security-audit.md) — Full security review

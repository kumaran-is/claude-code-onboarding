# RevenueCat Subscription Integration

> **When to use**: Adding in-app purchases, subscription entitlements, paywalls, or mobile subscription management via RevenueCat
> **Time estimate**: 2–4 hours per integration
> **Prerequisites**: RevenueCat project, API v2 Secret Key, App Store / Google Play app configured in RevenueCat dashboard

## Overview

Full RevenueCat subscription lifecycle from MCP setup through Flutter SDK integration to server-side entitlement verification. RevenueCat is the single source of truth for "does this user have access to X?" — Stripe handles payment processing, RevenueCat handles entitlement management.

## Phases

### Phase 1 — Load Skill & Verify MCP

**Trigger**: Any task involving in-app purchases or subscription entitlements
**Action**: Load `revenuecat` skill (`skills/revenuecat/SKILL.md`)
**MCP**: `revenuecat` MCP server (26 tools at `mcp.revenuecat.ai`)

**Verify MCP is working**:
```
Use `get_project` to verify connection
Use `list_entitlements` to see current entitlement configuration
Use `list_offerings` to see current offerings
```

**Iron Law**: NO ENTITLEMENT CHECK WITHOUT REVENUECAT SDK

**Gate**: MCP responds, skill loaded, project/entitlement state verified

---

### Phase 2 — Configure Entitlements & Offerings (via MCP)

**Trigger**: Setting up subscription products for the first time
**Tools**: RevenueCat MCP tools

**Steps**:
1. Create entitlements via `create_entitlement` (e.g., `pro_access`, `premium_features`)
2. Create products via `create_product` — map to App Store / Google Play product IDs
3. Attach products to entitlements via `attach_products_to_entitlement`
4. Create offerings via `create_offering` — group packages for paywall display
5. Create packages via `create_package` — monthly, annual, etc.

**Verify**: `list_entitlements` and `list_offerings` show correct configuration

**Gate**: Entitlements, products, offerings, and packages all configured and linked

---

### Phase 3 — Flutter Client SDK Integration

**Trigger**: App needs subscription UI and entitlement checks
**Skill**: `flutter-mobile` + `revenuecat`

**Steps**:
1. Add `purchases_flutter` to `pubspec.yaml` (pin exact version)
2. Initialize SDK in app startup with platform-specific API key
3. Identify user after authentication (`Purchases.logIn(userId)`)
4. Check entitlements (`Purchases.getCustomerInfo()`)
5. Build paywall screen from `Purchases.getOfferings()`
6. Handle purchase flow (`Purchases.purchase(PurchaseParams.package(package))`; `purchasePackage` is deprecated in purchases_flutter 11.x)
7. Log out on sign-out (`Purchases.logOut()`)

**Riverpod pattern**:
```dart
@riverpod
class SubscriptionState extends _$SubscriptionState {
  @override
  Future<CustomerInfo> build() async {
    return Purchases.getCustomerInfo();
  }
}
```

**Gate**: SDK initializes, entitlement check works, test purchase completes in sandbox

---

### Phase 4 — Server-Side Entitlement Verification

**Trigger**: Backend needs to gate features based on subscription status
**Skill**: `python-dev` + `revenuecat`

**Principle**: Never trust client claims — always verify server-side

**Steps**:
1. Create entitlement verification function using RevenueCat REST API v2
2. Call `GET /v2/projects/{project_id}/subscribers/{user_id}` with API v2 Secret Key
3. Check entitlement active status and expiration date
4. Use this in API middleware / dependency injection for gated endpoints

**Gate**: Server-side verification works for active, expired, and non-existent entitlements

---

### Phase 5 — Webhook Handlers

**Trigger**: Need to sync subscription state to your database
**Skill**: `python-dev`

**Steps**:
1. Create webhook endpoint in FastAPI
2. Verify the HMAC signature (`X-RevenueCat-Webhook-Signature`) on the raw body
3. Handle subscription lifecycle events:

| Event | Action |
|-------|--------|
| `INITIAL_PURCHASE` | Activate subscription tier |
| `RENEWAL` | Extend period, log payment |
| `CANCELLATION` | Schedule downgrade at period end |
| `EXPIRATION` | Downgrade to free tier |
| `BILLING_ISSUE` | Flag account, trigger dunning |
| `PRODUCT_CHANGE` | Update tier |

4. Sync subscription state to database

**Gate**: Webhook handler processes all event types; HMAC signature (X-RevenueCat-Webhook-Signature) verified on the raw body

---

### Phase 6 — Testing

**Flutter tests**:
- Mock `Purchases` class in widget tests
- Use App Store Sandbox / Google Play test tracks for integration tests

**Python tests**:
- Mock RevenueCat API responses by injecting an `httpx.AsyncClient` with `httpx.MockTransport` (no plugin; see `revenuecat` skill)
- Test entitlement verification (active, expired, missing)
- Test webhook handler for each event type
- Test HMAC signature verification (valid, tampered body, empty secret refused at boot)

**Gate**: All tests pass across Flutter and Python

---

### Phase 7 — Security Review

**Dispatch**: `security-reviewer` agent
**Checklist** (from `skills/revenuecat/SKILL.md`):
- [ ] API keys in environment variables only
- [ ] Dedicated API v2 secret key for MCP server
- [ ] Server-side entitlement verification for all gated features
- [ ] HMAC signing enabled; X-RevenueCat-Webhook-Signature verified on the raw body; signing secret is SecretStr with min_length=16 (rejects empty or placeholder values)
- [ ] `Purchases.logIn()` after authentication
- [ ] `Purchases.logOut()` on sign-out
- [ ] Sandbox keys in dev/staging, production keys in production only
- [ ] No direct StoreKit/BillingClient API calls

**Gate**: Security reviewer verdict = no CRITICAL or HIGH findings

---

## Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| Trusting client entitlement claims | Always verify server-side via REST API v2 |
| Forgetting `Purchases.logOut()` | Entitlements leak to next user on same device |
| Direct StoreKit/BillingClient calls | Use RevenueCat SDK — it handles receipt validation |
| Hardcoded API keys | Use `String.fromEnvironment()` in Flutter, env vars in Python |
| Not testing with sandbox accounts | Always use App Store Sandbox / Google Play test tracks |
| Ignoring `BILLING_ISSUE` webhook | Users lose access silently — always handle dunning |

## Related Workflows

- [stripe-payment-integration.md](stripe-payment-integration.md) — Backend payment processing (pairs with RevenueCat)
- [feature-flutter-mobile.md](feature-flutter-mobile.md) — Flutter client patterns
- [feature-python-fastapi.md](feature-python-fastapi.md) — Backend service patterns
- [security-audit.md](security-audit.md) — Full security review

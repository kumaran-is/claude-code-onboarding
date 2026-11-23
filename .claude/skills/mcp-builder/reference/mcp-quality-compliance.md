## Compliance Flags (SOC2 / GDPR / PCI)

Production MCP servers in regulated environments must support compliance mode toggles that modify behavior at runtime without code changes. These are boolean env var flags, not code branches.

### Standard Flags

```typescript
// In your config schema (Zod)
const complianceSchema = z.object({
  SOC2_COMPLIANCE_MODE: z.coerce.boolean().default(false),
  GDPR_COMPLIANCE_MODE: z.coerce.boolean().default(false),
  PCI_COMPLIANCE_MODE: z.coerce.boolean().default(false),
});
```

### What Each Flag Enforces

| Flag | Behavioral Changes |
|------|--------------------|
| `SOC2_COMPLIANCE_MODE` | Force audit trail for every tool call (even if audit logging is otherwise optional); enforce minimum log retention; disable debug endpoints |
| `GDPR_COMPLIANCE_MODE` | Strip or hash all PII fields from logs and audit trail (email, phone, name, address, IP address); reject requests that include PII in tool inputs unless explicitly needed; honor data subject access/erasure requests via admin API |
| `PCI_COMPLIANCE_MODE` | Redact all payment-adjacent fields (card number, CVV, expiry, bank account); disable response caching for payment-related tools; enforce TLS 1.2+ only; log all access to payment data with full correlation trail |

### Implementation Pattern

```typescript
// Apply compliance modifications after base config is loaded
if (config.SOC2_COMPLIANCE_MODE) {
  // Ensure audit trail cannot be disabled
  config.auditTrailEnabled = true;
  config.debugEndpointsEnabled = false;
}

if (config.GDPR_COMPLIANCE_MODE) {
  // Override PII fields list to add project-specific PII
  config.piiFields = new Set([
    ...DEFAULT_PII_FIELDS,
    'customer_email', 'account_holder_name', 'shipping_address',
  ]);
}

if (config.PCI_COMPLIANCE_MODE) {
  config.cacheEnabled = false; // Never cache payment data
  config.responseFields.blocklist.add('card_number');
  config.responseFields.blocklist.add('cvv');
}
```

### When to Enable

- `SOC2_COMPLIANCE_MODE=true` — all production deployments
- `GDPR_COMPLIANCE_MODE=true` — any deployment handling EU user data
- `PCI_COMPLIANCE_MODE=true` — any deployment handling payment card data

**Never enable compliance flags selectively in staging only** — if prod needs them, staging must run identical flags or your staging tests are not representative.

---

## Canonical Scorer / Business Logic Delegation

**MCP tools are API entry points, not business logic layers.** Any scoring, ranking, matching, or classification logic belongs in a dedicated upstream service — not in MCP tool handlers.

### The Rule

```
❌ WRONG — scoring logic in the MCP layer
async function handleProductSearch(args) {
  const products = await fetchProducts(args);
  return products
    .filter(v => v.rating > 3.5)               // ← business rule
    .sort((a, b) => b.score - a.score)          // ← ranking logic
    .slice(0, args.top_k);                       // ← trimming with business rule
}

✅ CORRECT — delegate to canonical scorer
async function handleProductSearch(args) {
  // Pass raw args to the upstream scorer; it owns all business logic
  const result = await canonicalScorerClient.match({
    ...args,
    top_k: args.top_k,
  });
  return result; // pre-ranked, pre-filtered by the scorer
}
```

### Why This Matters

- **Single source of truth** — if scoring logic lives in both the MCP layer and the scorer service, they will drift
- **Testability** — scorer service has its own eval suite and accuracy gates; MCP tool tests are integration tests only
- **Auditability** — every ranking decision traces to one service with its own audit log
- **Independence** — the scorer can be updated, A/B tested, and rolled back without touching the MCP server

### What MCP Tools ARE Responsible For

- Input validation + sanitization (Zod schema, attack pattern detection)
- Authentication + rate limiting
- Calling the canonical scorer via HTTP with the validated input
- Transforming the scorer response into the MCP tool response format
- Error handling + fallback when the scorer is unavailable
- Logging + metrics + audit trail for the tool call

### What MCP Tools Are NOT Responsible For

- Implementing scoring formulas, ranking weights, or matching algorithms
- Filtering results based on business rules (that is the scorer's job)
- Caching scorer inputs/outputs in a way that bypasses scorer logic
- Re-implementing any logic that already exists in an upstream service

---

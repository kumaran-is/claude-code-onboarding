# API Testing

> **When to use**: Verifying API contracts, integration behavior, and service boundaries before claiming a feature complete
> **Time estimate**: 30 min for a single endpoint; 2–4 hours for a full service
> **Prerequisites**: Service running locally or on test environment; stack-specific test framework configured

## Overview

API testing covers three layers: unit tests for business logic, integration tests against real infrastructure (DB, queues, downstream services), and contract tests for API consumers. Uses the `verification-before-completion` skill Iron Law — no "done" claim without running verification commands.

---

## Iron Law (from `skills/verification-before-completion/SKILL.md`)

> **NO COMPLETION CLAIM WITHOUT RUNNING VERIFICATION COMMANDS AND CONFIRMING OUTPUT**
> "Tests pass" is not a claim — it's evidence. Show the command and output.

---

## Testing Layers

| Layer | What it tests | When to write |
|-------|--------------|---------------|
| **Unit** | Business logic, validators, transformers, error mapping | Always — for every function with logic |
| **Integration** | DB queries, cache, message queue, external API | When touching infrastructure |
| **Contract** | API response shape matches consumer expectations | When API is consumed by another team/service |
| **E2E** | Full user journey through UI to DB | Critical paths only — see browser-e2e-testing.md |

---

## Phases

### Phase 1 — Define What to Test

For each API endpoint, document:
- Request contract: method, path, headers, body schema
- Response contract: status code, body schema, error shape
- Side effects: what changes in the DB / emits to queue / calls downstream
- Error cases: what 4xx/5xx should be returned and when

**Test matrix** (minimum per endpoint):

| Scenario | Expected Status |
|----------|----------------|
| Valid request, authenticated | 200 / 201 |
| Missing required field | 400 |
| Invalid field type/value | 400 |
| Unauthenticated | 401 |
| Authorized but forbidden resource | 403 |
| Resource not found | 404 |
| Duplicate / conflict | 409 |
| Downstream service unavailable | 502 or 503 |

---

### Phase 2 — Integration Tests by Stack

#### Java / Spring WebFlux

```java
// Skill: java-spring-api — WebTestClient against real DB
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderControllerIT {

    @Autowired WebTestClient webTestClient;

    @Test
    void createOrder_withValidBody_returns201AndPersists() {
        webTestClient.post().uri("/api/orders")
            .header("Authorization", "Bearer " + validToken())
            .bodyValue(Map.of("itemId", "item-1", "quantity", 2))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").isNotEmpty()
            .jsonPath("$.status").isEqualTo("PENDING");
    }

    @Test
    void createOrder_withMissingItem_returns400() {
        webTestClient.post().uri("/api/orders")
            .header("Authorization", "Bearer " + validToken())
            .bodyValue(Map.of("quantity", 2))  // missing itemId
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.error").isEqualTo("VALIDATION_ERROR");
    }
}
```

**Run**:
```bash
./mvnw test -Dtest="*IT"           # Integration tests only
./mvnw verify                      # Full suite
```

#### NestJS / TypeScript

```typescript
// Skill: nestjs-api — supertest against running app
describe('POST /orders', () => {
  it('returns 201 with order id for valid request', async () => {
    const res = await request(app.getHttpServer())
      .post('/orders')
      .set('Authorization', `Bearer ${validToken}`)
      .send({ itemId: 'item-1', quantity: 2 })
      .expect(201);

    expect(res.body).toMatchObject({
      id: expect.any(String),
      status: 'PENDING',
    });
  });

  it('returns 400 when itemId is missing', async () => {
    await request(app.getHttpServer())
      .post('/orders')
      .set('Authorization', `Bearer ${validToken}`)
      .send({ quantity: 2 })
      .expect(400);
  });

  it('returns 401 without auth header', async () => {
    await request(app.getHttpServer())
      .post('/orders')
      .send({ itemId: 'item-1', quantity: 2 })
      .expect(401);
  });
});
```

**Run**:
```bash
npx vitest run src/**/*.integration.spec.ts
npx vitest run                      # Full suite
```

#### Python / FastAPI

```python
# Skill: python-dev — pytest + httpx2 AsyncClient + real DB (asyncio_mode = "auto": no marker needed)
async def test_create_order_returns_201(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/orders",
        json={"item_id": "item-1", "quantity": 2},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "pending"

async def test_create_order_missing_field_returns_422(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/orders",
        json={"quantity": 2},  # missing item_id
        headers=auth_headers,
    )
    assert response.status_code == 422

async def test_create_order_unauthorized_returns_401(client: AsyncClient):
    response = await client.post("/orders", json={"item_id": "item-1", "quantity": 2})
    assert response.status_code == 401
```

**Run**:
```bash
uv run pytest tests/integration/ -v
uv run pytest                       # Full suite
```

---

### Phase 3 — /status-check Verification

After implementing and testing an endpoint, run `/status-check` to get binary verification:

```
/status-check
```

Returns:
```
What WORKS:
- POST /orders: ✅ Creates order, returns 201, persists to DB
- GET /orders/:id: ✅ Returns order by ID, 404 when not found

What's BROKEN:
- DELETE /orders/:id: ❌ Returns 200 instead of 204
```

No claim of "done" without this binary status output shown.

---

### Phase 4 — Contract Testing (for shared APIs)

When an API is consumed by another team, frontend, or mobile app:

**OpenAPI spec validation** (from `openapi-spec-generation` skill):
```bash
# Generate/update OpenAPI spec
npx @redocly/cli lint openapi.yaml      # Validate spec
npx @redocly/cli bundle openapi.yaml    # Bundle for distribution
```

**Contract snapshot test**:
```typescript
// Lock response shape so breaking changes are caught
it('GET /orders response matches OpenAPI schema', async () => {
  const res = await request(app).get('/orders/order-1').expect(200);
  expect(res.body).toMatchSchema(orderResponseSchema);
});
```

**Breaking change detection**:
- Adding required request fields = BREAKING
- Removing response fields = BREAKING
- Changing field types = BREAKING
- Adding optional fields = safe
- Adding optional query params = safe

If breaking: version the API (`/v2/orders`) or negotiate a migration window.

---

### Phase 5 — Evidence Format (Required Before "Done")

Every API testing session must produce this evidence block:

```
## API Testing Evidence — [endpoint or feature]

### Tests Run:
- Command: `uv run pytest tests/integration/ -v`
- Output: 12 passed, 0 failed in 4.2s

### Scenarios Covered:
- ✅ POST /orders — valid request → 201 + DB record
- ✅ POST /orders — missing itemId → 400 + error body
- ✅ POST /orders — no auth → 401
- ✅ POST /orders — duplicate → 409
- ✅ GET /orders/:id — exists → 200
- ✅ GET /orders/:id — not found → 404
- ✅ GET /orders/:id — wrong user → 403

### NOT Covered (with reason):
- ⏳ Downstream service timeout → pending mock infrastructure
```

This format satisfies `verification-and-reporting.md` requirements.

---

## Quick Reference

| Phase | What to Do | Gate |
|-------|-----------|------|
| 1 — Define | Document request/response contract + error cases | Test matrix written |
| 2 — Write tests | Integration tests per stack (happy path + all error codes) | Tests exist and fail first |
| 3 — Implement | Make tests pass | All tests green |
| 4 — Contract | OpenAPI spec validation (if shared API) | Spec valid, no breaking changes |
| 5 — Evidence | Run full suite, paste output | Test output in response |

---

## Common Pitfalls

- **Only testing happy path** — 60% of bugs are in error handling; test all 4xx/5xx cases
- **Mocking the database** — mock tests can pass while real DB queries fail; use real DB in integration tests
- **Not testing auth** — every protected endpoint needs an "unauthorized" and "forbidden" test
- **Testing implementation, not contract** — assert on response shape, not on internal method calls
- **No evidence output** — "tests pass" is not evidence; paste the actual command and output
- **Skipping 422 vs 400 distinction** — Pydantic/FastAPI returns 422 for body validation, 400 for business logic errors; test both explicitly

## Related Workflows

- [`test-driven-development.md`](test-driven-development.md) — TDD cycle before integration tests
- [`browser-e2e-testing.md`](browser-e2e-testing.md) — E2E layer above integration tests
- [`code-review.md`](code-review.md) — review includes test coverage check
- [`pre-commit-validation.md`](pre-commit-validation.md) — validation gate before commit

# Test-Driven Development

> **When to use**: Writing any new feature, business logic, or bug fix — TDD is the default development mode, not an optional add-on
> **Time estimate**: 20–40% slower per feature, but 60–80% fewer bugs in review
> **Prerequisites**: Test framework configured for the target stack

## Overview

Red-Green-Refactor cycle enforced by the TDD skill Iron Law: no implementation without a failing test first. Covers stack-specific test patterns, when to write unit vs integration vs E2E tests, and how to use the Three-Pass Development pattern inside TDD.

---

## Iron Law (from `skills/tdd/SKILL.md`)

> **NO IMPLEMENTATION WITHOUT A FAILING TEST FIRST**
> If you cannot show a failing test, you have not started yet.

This applies even to "obvious" code. The test defines the contract. The implementation fulfills it.

---

## The Red-Green-Refactor Cycle

```
RED   → Write a test that fails (does not compile = red too)
GREEN → Write the minimum code to make the test pass
REFACTOR → Clean up without breaking the test
```

**Rules:**
- RED: The test must actually fail, not just exist
- GREEN: Write the **minimum** code. No extra logic. No "while I'm here" additions
- REFACTOR: Only rename, extract, simplify — no behavior changes; test must still pass

---

## Phases

### Phase 1 — Identify What to Test

**Before writing any test**, answer:
1. What is the unit of behavior? (A method, endpoint, or UI action — not an implementation detail)
2. What are the inputs and outputs?
3. What are the edge cases? (null, empty, zero, negative, concurrent, error state)
4. What is the happy path?
5. What are the failure modes?

**Test pyramid** (from TDD skill reference):

| Layer | What to test | Volume |
|-------|-------------|--------|
| Unit | Pure functions, domain logic, validators, transformers | 70% |
| Integration | DB queries, external APIs, message queues | 20% |
| E2E | Critical user journeys (login, checkout, core workflow) | 10% |

---

### Phase 2 — Write the Failing Test (RED)

**Stack-specific test patterns**:

#### Java / Spring Boot (WebFlux)
```java
// Skill: java-spring-api — WebTestClient for reactive controllers
@Test
void createOrder_withValidRequest_returns201() {
    webTestClient.post().uri("/api/orders")
        .bodyValue(new CreateOrderRequest("item-1", 2))
        .exchange()
        .expectStatus().isCreated()
        .expectBody(OrderResponse.class)
        .value(r -> assertThat(r.id()).isNotNull());
}
```
**Command**: `/scaffold-spring-api` sets up test structure
**Agent**: `spring-reactive-reviewer` after implementation

#### NestJS / TypeScript
```typescript
// Skill: nestjs-api — Vitest + supertest
it('POST /orders returns 201 with order id', async () => {
  const res = await request(app.getHttpServer())
    .post('/orders')
    .send({ itemId: 'item-1', quantity: 2 })
    .expect(201);
  expect(res.body.id).toBeDefined();
});
```
**Command**: `/scaffold-nestjs-api` sets up Vitest config
**Agent**: `nestjs-reviewer` after implementation

#### Python / FastAPI
```python
# Skill: python-dev — pytest + httpx AsyncClient
async def test_create_order_returns_201(client: AsyncClient):
    response = await client.post("/orders", json={"item_id": "item-1", "quantity": 2})
    assert response.status_code == 201
    assert "id" in response.json()
```
**Command**: `/scaffold-python-api` sets up pytest + AsyncClient fixture
**Agent**: `python-dev` skill covers pytest patterns

#### Flutter / Dart
```dart
// Skill: flutter-mobile — flutter_test + Riverpod 3 ProviderContainer.test (auto-disposed after the test)
// @riverpod class OrderNotifier generates `orderProvider` (the Notifier suffix is dropped)
test('OrderNotifier creates order successfully', () async {
  final container = ProviderContainer.test(
    overrides: [
      orderRepositoryProvider.overrideWithValue(FakeOrderRepository()),
    ],
  );
  await container.read(orderProvider.notifier).createOrder('item-1', 2);
  expect(container.read(orderProvider).value?.id, isNotNull);
});
```
**Agent**: `riverpod-reviewer` after implementation

#### Angular / TypeScript
```typescript
// Skill: angular-spa — ng test (Vitest via @angular/build:unit-test) + TestBed
it('should display order confirmation after submit', async () => {
  const fixture = TestBed.createComponent(OrderFormComponent);
  fixture.componentInstance.form.setValue({ itemId: 'item-1', quantity: 2 });
  fixture.componentInstance.submit();
  await fixture.whenStable();
  expect(fixture.nativeElement.querySelector('[data-testid="confirmation"]')).toBeTruthy();
});
```

**Verify the test is actually RED**: Run it. If it passes immediately, the test is wrong.

```bash
# Java
./mvnw test -Dtest=OrderControllerTest#createOrder_withValidRequest_returns201

# NestJS
npx vitest run src/orders/orders.controller.spec.ts

# Python
uv run pytest tests/test_orders.py::test_create_order_returns_201 -v

# Flutter
flutter test test/order_notifier_test.dart
```

---

### Phase 3 — Implement (GREEN)

Write the **minimum** code to make the test pass. No extra logic.

**Three-Pass inside GREEN**:
1. Make it work (naive, verbose, inline — just make the test pass)
2. Make it clear (rename, extract — only after GREEN is solid)
3. Make it efficient (only with profiling evidence)

**Test after every small change**: Don't write 100 lines then run tests. Write 10 lines, run, verify still green.

**Command sequence** (example: NestJS feature):
```
/scaffold-nestjs-api orders          # Generate module skeleton
# Write failing test
# Implement schema → DTO → repository → service → controller
# Run tests after each layer
npx vitest run                       # All tests must pass
```

---

### Phase 4 — Refactor

Only after GREEN:

- Extract repeated logic (Rule of Three applies: 3+ uses → extract)
- Rename variables to reflect intent
- Remove dead code YOUR implementation created
- Simplify conditionals

**Gate**: Tests must pass identically after every refactor step. If a test breaks, you changed behavior — undo.

---

### Phase 5 — Edge Cases

After the happy path is green, add tests for:

| Edge Case | Example |
|-----------|---------|
| Null / None inputs | `createOrder(null, 2)` |
| Empty collections | `processItems([])` |
| Zero / negative numbers | `createOrder('item', -1)` |
| Boundary values | Max quantity, min price |
| Concurrent calls | Two simultaneous creates with same ID |
| External API failure | Repository throws, what does service return? |
| Auth edge cases | Expired token, insufficient permissions |

Each edge case = its own test. Tests are documentation.

---

### Phase 6 — Verify and Report

Before declaring done:

```bash
# Run full test suite — not just your new tests
# Java
./mvnw test

# NestJS
npx vitest run

# Python
uv run pytest

# Flutter
flutter test
```

**Gate**: All existing tests pass (not just your new ones).

**Report format**:
```
Tests written: [N] new tests
Tests passing: [N+existing] / [total]
Coverage added: [what behavior is now tested]
Edge cases covered: [list]
```

---

## Quick Reference

| Phase | Action | Gate |
|-------|--------|------|
| 1 — Identify | List behaviors, inputs, outputs, edge cases | Written checklist |
| 2 — RED | Write failing test; run it; confirm it fails | Test output shows FAIL |
| 3 — GREEN | Implement minimum code; run test | Test output shows PASS |
| 4 — REFACTOR | Clean up; run test | Test still PASS, diff = structure only |
| 5 — Edge cases | Add tests for each edge case | All edge case tests pass |
| 6 — Verify | Run full suite | All tests pass |

---

## Common Pitfalls

- **Testing implementation, not behavior** — test what the code does for the user, not which methods it calls internally
- **Skipping RED** — writing code first, test second = not TDD; the test always passes and tells you nothing
- **Too-large RED-GREEN cycles** — write one test, make it pass; not 10 tests then implement everything
- **Mock everything** — over-mocking hides real integration bugs; mock only at system boundaries
- **No edge case tests** — happy path coverage gives false confidence; 40% of bugs live in edge cases
- **Brittle tests** — asserting on UI text instead of behavior; tests that break on refactor aren't useful

## Related Workflows

- [`feature-java-spring.md`](feature-java-spring.md) — TDD in Spring WebFlux context
- [`feature-nestjs.md`](feature-nestjs.md) — TDD in NestJS context
- [`feature-flutter-mobile.md`](feature-flutter-mobile.md) — TDD with Riverpod
- [`api-testing.md`](api-testing.md) — integration and contract testing
- [`browser-e2e-testing.md`](browser-e2e-testing.md) — E2E test layer

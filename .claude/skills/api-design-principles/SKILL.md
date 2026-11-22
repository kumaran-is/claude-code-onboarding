---
name: api-design-principles
description: Use before designing any REST API endpoint — covers URL structure, HTTP method semantics, pagination, caching, idempotency, and bulk operations across Python FastAPI, NestJS 11.x, and Spring Boot WebFlux 3.5.x. Complements openapi-spec-generation (spec format) and stack-specific implementation skills (code patterns).
allowed-tools: Read
metadata:
  triggers: REST API design, API versioning, idempotency key, ETag caching, bulk operations, pagination pattern, API checklist, URL design, HTTP methods, REST principles, CORS, rate limiting header
  related-skills: openapi-spec-generation, java-spring-api, nestjs-api, python-dev, architecture-design
  domain: api-architecture
  role: specialist
  scope: design
  output-format: specification
last-reviewed: "2026-03-14"
---

## Iron Law

**NO API ENDPOINT DESIGN WITHOUT READING `reference/rest-design-principles.md` FIRST — HTTP semantics, status codes, idempotency, and caching strategies must be agreed before writing implementation code**

# API Design Principles

Stack-agnostic REST design principles for APIs built with Python FastAPI, NestJS 11.x, or Spring Boot WebFlux 3.5.x. Use this skill during the design phase — before writing controllers or route handlers.

## When to Use

- Designing new REST endpoints from scratch
- Reviewing whether existing endpoints follow REST conventions
- Choosing a pagination strategy (offset vs cursor)
- Adding idempotency keys to mutation endpoints
- Designing caching strategy (ETags, Cache-Control)
- Designing bulk/batch endpoints with partial failure handling
- Running the pre-implementation API design checklist

## How This Skill Relates to Others

| Skill | Scope |
|-------|-------|
| **api-design-principles** (this skill) | Design phase — REST semantics, patterns, checklist |
| **openapi-spec-generation** | Documentation phase — OpenAPI 3.1 spec, developer guide |
| **java-spring-api** | Implementation — Spring WebFlux controllers, services |
| **nestjs-api** | Implementation — NestJS modules, controllers, DTOs |
| **python-dev** | Implementation — FastAPI routes, Pydantic models |

## Process

### Step 1: Run the Pre-Implementation Checklist

Read `assets/api-design-checklist.md` before designing any endpoint. Focus on:
- Resource naming and URL structure
- HTTP method assignment
- Status codes per operation
- Pagination strategy choice
- Versioning strategy

### Step 2: Apply REST Design Principles

Read `reference/rest-design-principles.md` for detailed patterns covering:
- URL structure and resource naming (plural nouns, shallow nesting)
- HTTP methods and correct status codes per operation type
- Pagination — offset-based vs cursor-based, with examples for all 3 stacks
- Versioning strategies (URL path recommended)
- Rate limiting headers (X-RateLimit-*)
- Authentication (Bearer token, 401 vs 403 distinction)
- Error response format (consistent structure across all 3 stacks)
- **Caching** — Cache-Control, ETags, conditional GET (304) — all 3 stacks
- **Idempotency keys** — mutation safety for payment and order endpoints — all 3 stacks
- **Bulk operations** — batch endpoints with 207 Multi-Status partial failure — all 3 stacks
- CORS configuration — all 3 stacks
- Health and monitoring endpoints

For FastAPI implementation of what the design decides, load `python-dev/reference/`: `fastapi-authorization-boundaries.md` (actor vs subject, object scope, service-only endpoints), `fastapi-rate-limiting.md`, `fastapi-error-handling.md`, and `fastapi-architecture-and-config.md` §7 (atomic idempotency). Two design decisions to settle up front: the **wire type** of money/decimal fields (`Decimal` serialises as a string, `float` as a number: changing it later breaks clients), and what **queue-replaying clients** receive (a 4xx makes them drop the queued operation).

### Step 3: Document with OpenAPI

Once the design is finalized, hand off to `openapi-spec-generation` to generate the OpenAPI 3.1 spec.

## Reference Files

| File | Content | Load When |
|------|---------|-----------|
| `reference/rest-design-principles.md` | URL structure, HTTP methods, pagination, caching, idempotency, bulk ops, CORS — examples for FastAPI, NestJS, Spring WebFlux | Designing new endpoints or reviewing REST compliance |
| `assets/api-design-checklist.md` | 60-item pre-implementation checklist (REST only) with stack-specific items for all 3 backends | Before starting any new endpoint or reviewing an existing API |

## Error Handling

**Inconsistent status codes across endpoints**: Follow the status code reference in `reference/rest-design-principles.md` section "HTTP Methods and Status Codes". All endpoints in a service must be consistent.

**Pagination strategy mismatch**: Choose offset-based for admin/report endpoints, cursor-based for real-time/feed endpoints. Document the choice — do not mix strategies within the same resource collection.

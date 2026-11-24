# API Design Checklist

Pre-implementation checklist for REST APIs. Run before writing any controller or route handler. Covers all 3 backend stacks: Python FastAPI, NestJS 11.x, Spring Boot 4.2 (MVC default, WebFlux when justified).

---

## Resource Design

- [ ] Resources are nouns, not verbs (`/users` not `/getUsers`)
- [ ] Plural names for collections (`/users`, `/orders`)
- [ ] Consistent naming convention across all endpoints (kebab-case)
- [ ] No deep nesting beyond 2 levels (`/users/{id}/orders` is max)
- [ ] All CRUD operations mapped to correct HTTP methods

## HTTP Methods

- [ ] GET for retrieval (safe and idempotent — no side effects)
- [ ] POST for creation (returns 201 + Location header)
- [ ] PUT for full replacement (idempotent — requires all fields)
- [ ] PATCH for partial updates (only changed fields)
- [ ] DELETE for removal (idempotent — returns 204)

## Status Codes

- [ ] 200 OK for successful GET, PATCH, PUT
- [ ] 201 Created for POST (+ Location header set)
- [ ] 204 No Content for DELETE (no response body)
- [ ] 304 Not Modified for conditional GET when ETag matches
- [ ] 207 Multi-Status for bulk/batch with partial failures
- [ ] 400 Bad Request for malformed request syntax
- [ ] 401 Unauthorized for missing or invalid auth token
- [ ] 403 Forbidden for valid token with insufficient permissions (never 403 for missing token)
- [ ] 404 Not Found for missing resources
- [ ] 409 Conflict for duplicate unique fields or referential integrity violations
- [ ] 422 Unprocessable Entity for validation errors (well-formed but semantically invalid)
- [ ] 429 Too Many Requests for rate limiting (+ Retry-After header)
- [ ] 500 Internal Server Error for unhandled server errors

## Pagination

- [ ] All collection endpoints paginated (no unbounded list responses)
- [ ] Default page size defined (20 recommended)
- [ ] Maximum page size enforced (100 recommended)
- [ ] Pagination strategy chosen: offset-based (admin/report) or cursor-based (feed/real-time)
- [ ] Bounds enforced: `page >= 1`, `1 <= page_size <= MAX_PAGE_SIZE` (shared constant); deterministic `ORDER BY` with a unique tiebreak
- [ ] Pagination metadata included in response (`total`, `pages`, `has_more`)
- [ ] **FastAPI**: `page_size: int = Query(default=20, le=100)`
- [ ] **NestJS**: `@Max(100) @Type(() => Number) pageSize: number = 20`
- [ ] **Spring Boot**: `@RequestParam(defaultValue = "20") @Max(100) int size`

## Filtering and Sorting

- [ ] Query parameters used for filtering (not request body)
- [ ] Sort parameter supported (`?sort=created_at` or `?sort=-created_at` for desc)
- [ ] Search parameter for full-text (`?search=` or `?q=`)
- [ ] Field selection supported for large resources (`?fields=id,name,email`)

## Versioning

- [ ] Versioning strategy decided: URL path (`/api/v1/`) recommended
- [ ] Version prefix consistent across all endpoints in the service
- [ ] Deprecation policy defined (Sunset header for old versions)
- [ ] Deprecated routes marked in the spec (`deprecated=True`), emit `Deprecation`/`Sunset` headers, and a check fails once a removal date has passed (mark each with `REMOVE-BY: YYYY-MM-DD`; `python3 .claude/scripts/check_deprecations.py` fails on a passed or malformed date, warns 30 days ahead)
- [ ] Breaking vs non-breaking changes understood (removing/renaming fields = breaking)

## Error Handling

- [ ] Consistent error response format across all endpoints (code, message, details, timestamp, path, requestId)
- [ ] Field-level validation errors in `details` array
- [ ] Machine-readable error codes (e.g., `VALIDATION_ERROR`, `ORDER_NOT_FOUND`); never a code or status that reveals whether an account exists (`EMAIL_EXISTS` on sign-up is an enumeration oracle)
- [ ] `requestId` included for log correlation
- [ ] **FastAPI**: one envelope for domain errors, `RequestValidationError` (422 without echoing `input`), `HTTPException` and a catch-all 500 — `python-dev/reference/fastapi-error-handling.md`
- [ ] **NestJS**: `HttpException` subclasses or `@Catch()` filter returning `ProblemDetail`
- [ ] **Spring Boot**: `@ControllerAdvice` returning `ProblemDetail` (RFC 9457)

## Authentication and Authorization

- [ ] Auth method defined: Bearer token (JWT) recommended
- [ ] Authorization checks present on every protected endpoint
- [ ] 401 used for missing/invalid token (not 403)
- [ ] 403 used for valid token with insufficient permissions (not 401)
- [ ] Token expiration handled with 401 and `WWW-Authenticate` header
- [ ] The caller's own id comes from the verified token, never the request body; fetch-by-id carries the caller's scope (404 for missing and foreign)
- [ ] Endpoints with third-party side effects (send, charge, metered call) require a service credential, not an end-user token — `python-dev/reference/fastapi-authorization-boundaries.md`

## Rate Limiting

- [ ] Rate limits defined (per user, per IP, or per API key)
- [ ] `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers set
- [ ] `Retry-After` header set on 429 responses
- [ ] **FastAPI**: `slowapi` or `fastapi-limiter`; routes with path parameters use a constant shared scope; enumeration/spend limits keyed on user id; shared storage wired — `python-dev/reference/fastapi-rate-limiting.md`
- [ ] **NestJS**: `@nestjs/throttler` with `ThrottlerGuard`
- [ ] **Spring Boot**: Bucket4j, or a custom servlet `Filter` (MVC) / `WebFilter` (WebFlux)

## Caching (new endpoints serving GET responses)

- [ ] Cache-Control header set appropriately (public/private, max-age)
- [ ] ETags implemented for resource responses (enables 304 Not Modified)
- [ ] Conditional GET (`If-None-Match`) handled and returns 304 when ETag matches
- [ ] Mutations (POST/PUT/PATCH/DELETE) set `Cache-Control: no-cache, no-store`

## Idempotency (mutation endpoints)

- [ ] Payment, order, and notification endpoints accept `Idempotency-Key` header
- [ ] Duplicate requests with same key return cached response (not reprocessed)
- [ ] Idempotency cache TTL defined (24 hours recommended)
- [ ] Idempotency key format documented (UUID v4 recommended)

## Replayed / queued clients (offline-capable apps)

- [ ] Endpoints that a queue-replaying client calls accept suspicious-but-processable payloads and flag them on a server-set column; a 4xx there makes the client drop the queued operation (permanent data loss)
- [ ] 4xx only for unprocessable bodies, failed authorization or state-machine violations; the flag is never set inside a validator (that would be a 422)
- [ ] Mutations are idempotent (`Idempotency-Key`), since a replay can arrive twice

## Bulk Operations (if batch endpoints exist)

- [ ] Batch endpoint uses `POST /resource/batch` pattern
- [ ] Returns 207 Multi-Status (not 200 or 201)
- [ ] Response includes per-item success/failure with index reference
- [ ] `succeeded` and `failed` counts in response
- [ ] Partial success handled (some items can fail without failing whole batch)

## CORS

- [ ] CORS configured for allowed origins (no wildcard `*` in production); origins come from per-environment config with an empty default
- [ ] `Idempotency-Key` included in `allowedHeaders`
- [ ] Credentials mode (`allowCredentials`) matched to frontend requirements

## Documentation

- [ ] OpenAPI spec will be generated after design is complete (use `openapi-spec-generation` skill)
- [ ] All endpoints will be documented with request/response examples
- [ ] Error responses documented for each endpoint
- [ ] Authentication flow documented

## Testing

- [ ] Happy path test for each endpoint
- [ ] 400/422 validation error scenarios tested
- [ ] 401/403 auth failure scenarios tested
- [ ] 404 not-found scenario tested
- [ ] Pagination boundary conditions tested (page=0, page > total)
- [ ] Idempotency: duplicate key returns cached response (not reprocessed); a concurrent-duplicate test proves exactly one write; same key + different body is rejected
- [ ] Bulk: mixed success/failure batch returns 207 with correct counts

## Security Baseline

- [ ] Input validation on all fields (Pydantic / class-validator / `@Valid`)
- [ ] No raw SQL concatenation (use ORM or parameterized queries)
- [ ] Sensitive data absent from URLs (tokens, passwords, PII)
- [ ] No secrets in response bodies
- [ ] HTTPS enforced in production (HTTP → 301 redirect)

## Health and Monitoring

- [ ] `GET /health` endpoint returns 200 with status and version (no auth required)
- [ ] `GET /health/detailed` checks database and dependencies (returns 503 if degraded)
- [ ] Request logging includes method, path, status, and duration
- [ ] Error tracking configured (Sentry or equivalent)

## OWASP API Security Top 10 (2023)

> Reference: [owasp.org/www-project-api-security](https://owasp.org/www-project-api-security/)
> These are API-specific attack categories — distinct from the general OWASP Web Top 10.

- [ ] **API1 — Broken Object Level Authorization**: every endpoint verifies the caller owns or has access to the requested object (no IDOR)
- [ ] **API2 — Broken Authentication**: strong auth enforced; token expiry, rotation, and revocation implemented
- [ ] **API3 — Field-level authorization (mass assignment / excessive data exposure)**: restrict which fields the caller can read or write (no mass assignment)
- [ ] **API4 — Unrestricted Resource Consumption**: rate limiting and payload size limits enforced on all endpoints
- [ ] **API5 — Broken Function Level Authorization**: role/scope verified on every function, not just at collection level
- [ ] **API6 — Unrestricted Access to Sensitive Business Flows**: critical workflows (payments, account creation) protected from automated abuse
- [ ] **API7 — Server Side Request Forgery (SSRF)**: URLs in server-side fetch calls validated and allowlisted
- [ ] **API8 — Security Misconfiguration**: debug mode off, security headers set, no verbose error messages in production
- [ ] **API9 — Improper Inventory Management**: all API versions documented and secured; unused/shadow endpoints decommissioned
- [ ] **API10 — Unsafe Consumption of APIs**: all data from third-party API responses validated and sanitized before use

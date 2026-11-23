# REST Design Principles

Patterns and conventions for designing REST APIs across Python FastAPI, NestJS 11.x, and Spring Boot WebFlux 3.5.x. Examples are given for all 3 stacks where behavior differs.

---

## URL Structure

### Resource Naming

```
# Correct — plural nouns
GET /api/v1/users
GET /api/v1/orders
GET /api/v1/products

# Incorrect — verbs or mixed conventions
GET /api/getUser
GET /api/user          # inconsistent singular
POST /api/createOrder  # verb in URL
```

### Nested Resources — Shallow Nesting (Max 2 Levels)

```
# Preferred — shallow nesting
GET /api/v1/users/{id}/orders
GET /api/v1/orders/{id}

# Avoid — deep nesting beyond 2 levels
GET /api/v1/users/{id}/orders/{orderId}/items/{itemId}/reviews
# Prefer instead:
GET /api/v1/order-items/{id}/reviews
```

---

## HTTP Methods and Status Codes

| Method | Purpose | Success Code | Error Codes |
|--------|---------|-------------|-------------|
| GET | Retrieve | 200 OK | 404 Not Found |
| POST | Create | 201 Created + Location header | 400, 409 Conflict, 422 |
| PUT | Full replace (idempotent) | 200 OK | 400, 404, 422 |
| PATCH | Partial update | 200 OK | 400, 404, 422 |
| DELETE | Remove (idempotent) | 204 No Content | 404, 409 Conflict |

**POST** must return `Location: /api/v1/users/{newId}` header on 201.

**DELETE** returns 204 (no body). If resource has dependents, return 409 Conflict.

**Full status code reference:**

| Code | Meaning | When to Use |
|------|---------|-------------|
| 200 | OK | Successful GET, PATCH, PUT |
| 201 | Created | Successful POST |
| 204 | No Content | Successful DELETE |
| 304 | Not Modified | Conditional GET — ETag matched |
| 207 | Multi-Status | Batch/bulk with partial failures |
| 400 | Bad Request | Malformed request syntax |
| 401 | Unauthorized | Missing or invalid auth token |
| 403 | Forbidden | Valid token, insufficient permissions |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Duplicate unique field, referential constraint |
| 422 | Unprocessable Entity | Validation errors (well-formed but semantically wrong) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unhandled server error |
| 503 | Service Unavailable | Temporary downtime |

---

## Filtering, Sorting, and Searching

```
# Filtering — query params match field names
GET /api/v1/users?status=active
GET /api/v1/users?role=admin&status=active

# Sorting — prefix - for descending
GET /api/v1/users?sort=created_at
GET /api/v1/users?sort=-created_at
GET /api/v1/users?sort=name,-created_at

# Search — full-text
GET /api/v1/users?search=john
GET /api/v1/users?q=john

# Sparse fieldsets — reduce payload size
GET /api/v1/users?fields=id,name,email
```

### Bracket Filter Operators

```
# Comparison operators (bracket notation)
GET /api/v1/products?price[gte]=10&price[lte]=100
GET /api/v1/orders?created_at[after]=2025-01-01T00:00:00Z

# Multiple values (comma-separated)
GET /api/v1/products?category=electronics,clothing

# Sparse fieldsets (return only needed fields)
GET /api/v1/users?fields=id,name,email
```

Supported bracket operators: `[eq]`, `[neq]`, `[gt]`, `[gte]`, `[lt]`, `[lte]`, `[after]`, `[before]`, `[in]`, `[not_in]`.

---

## Pagination

**Rule:** Every collection endpoint must be paginated. Default page size: 20. Maximum: 100.

### Offset-Based (Use for admin/report endpoints)

```
GET /api/v1/users?page=2&page_size=20

Response:
{
  "items": [...],
  "page": 2,
  "page_size": 20,
  "total": 150,
  "pages": 8
}
```

**Python FastAPI:**
```python
MAX_PAGE_SIZE = 100
class PaginatedResponse[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int

@router.get("/users", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: Annotated[int, Query(ge=1)] = 1,   # bare `page: int = 1` allows 0; PostgreSQL rejects a negative OFFSET
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
):
    offset = (page - 1) * page_size    # needs ORDER BY with a unique tiebreak
    ...
```

**NestJS:**
```typescript
// DTO
export class PaginationQueryDto {
  @IsOptional() @IsInt() @Min(1) @Type(() => Number)
  page: number = 1;

  @IsOptional() @IsInt() @Min(1) @Max(100) @Type(() => Number)
  pageSize: number = 20;
}

// Controller
@Get()
findAll(@Query() query: PaginationQueryDto) {
  const { page, pageSize } = query;
  const skip = (page - 1) * pageSize;
  ...
}
```

**Spring Boot WebFlux:**
```java
@GetMapping
public Mono<PagedResponse<UserResponse>> listUsers(
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") @Max(100) int size) {
  return userService.findAll(PageRequest.of(page, size))
      .map(PagedResponse::fromPage);
}
```

### Cursor-Based (Use for feeds, real-time, large datasets)

```
GET /api/v1/users?limit=20&cursor=eyJpZCI6MTIzfQ

Response:
{
  "items": [...],
  "next_cursor": "eyJpZCI6MTQzfQ",
  "has_more": true
}
```

Cursor encodes the last-seen sort key (e.g., base64-encoded `{"id": 123, "created_at": "..."}`). Never expose raw database offsets in cursors.

---

## API Versioning Strategy

**Recommendation: URL path versioning.**

### URL Path Versioning (Recommended)

```
/api/v1/users   ← production
/api/v2/users   ← new version (breaking changes)
```

Pros: Explicit, cacheable, easy to route
Cons: URL changes between versions

### Header Versioning

```
GET /api/users
Accept: application/vnd.myapp.v2+json
```

Pros: Clean URLs
Cons: Harder to test in browser, easy to forget

| Strategy | Example | When to Use |
|----------|---------|-------------|
| URL path (recommended) | `/api/v1/users` | Default — clear, easy to route, cache-friendly |
| Accept header | `Accept: application/vnd.api+json; version=2` | Clean URLs, but harder to test and cache |
| Query param | `/api/users?version=2` | Easy to test, but forgettable |

### Rules

1. Start with `/api/v1/` — never version prematurely
2. Maintain at most 2 active versions (current + previous)
3. Non-breaking changes (add new optional fields/endpoints) do **NOT** need a new version
4. Breaking changes (remove/rename fields, change types, change URL) **REQUIRE** a new version

**Breaking vs non-breaking changes:**
- Adding optional fields → non-breaking, no version bump required
- Removing fields, renaming fields, changing types → breaking, requires new version

---

## Deprecation Notice Pattern

When deprecating an endpoint, add RFC 8594 response headers to signal the sunset date and migration target.

```
Sunset: Sat, 01 Jan 2026 00:00:00 GMT          # When this endpoint dies
Deprecation: true                                # RFC 8594
Link: </api/v2/users>; rel="successor-version"  # Where to migrate
```

**Python FastAPI:**
```python
@app.get("/api/v1/users")
async def list_users_v1(response: Response):
    response.headers["Sunset"] = "Sat, 01 Jan 2026 00:00:00 GMT"
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/v2/users>; rel="successor-version"'
    return await user_service.list()
```

**NestJS** — custom decorator + interceptor:
```typescript
// decorator
export const Deprecated = (opts: { sunset: string; successor: string }) =>
  SetMetadata('deprecated', opts);

// interceptor
@Injectable()
export class DeprecationInterceptor implements NestInterceptor {
  constructor(private reflector: Reflector) {}
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const opts = this.reflector.get<{ sunset: string; successor: string }>(
      'deprecated', context.getHandler()
    );
    if (opts) {
      const res = context.switchToHttp().getResponse<Response>();
      res.setHeader('Sunset', new Date(opts.sunset).toUTCString());
      res.setHeader('Deprecation', 'true');
      res.setHeader('Link', `<${opts.successor}>; rel="successor-version"`);
    }
    return next.handle();
  }
}

// usage on controller method
@Deprecated({ sunset: '2026-01-01', successor: '/api/v2/users' })
@Get('v1/users')
listUsersV1() { ... }
```

**Spring Boot WebFlux:**
```java
@GetMapping("/v1/users")
public Mono<ResponseEntity<List<UserResponse>>> listUsersV1(ServerHttpResponse serverResponse) {
    serverResponse.getHeaders().add("Sunset", "Sat, 01 Jan 2026 00:00:00 GMT");
    serverResponse.getHeaders().add("Deprecation", "true");
    serverResponse.getHeaders().add("Link", "</api/v2/users>; rel=\"successor-version\"");
    return userService.list().collectList().map(ResponseEntity::ok);
}
```

---

## Rate Limiting

### Response Headers

Always include rate limit headers on every response:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 742
X-RateLimit-Reset: 1640000000    # Unix timestamp when window resets
Retry-After: 3600                # Seconds (on 429 only)
```

**Python FastAPI** — use `slowapi` or `fastapi-limiter` (rules and executed examples: `python-dev/reference/fastapi-rate-limiting.md`):
```python
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.rate_limit_storage_uri)  # shared store

@router.get("/users")
@limiter.limit("100/minute")                      # fine: no path parameter
async def list_users(request: Request): ...

@router.get("/invites/{code}")                    # path parameter: .limit() would bucket per code
@limiter.shared_limit("10/hour", scope="invite-lookup", key_func=user_id_key)  # key on user id, not IP
async def lookup_invite(request: Request, code: str): ...
```

**NestJS** — use `@nestjs/throttler`:
```typescript
@UseGuards(ThrottlerGuard)
@Throttle({ default: { limit: 100, ttl: 60000 } })
@Get()
findAll() { ... }
```

**Spring Boot WebFlux** — use Bucket4j or custom `WebFilter`:
```java
// In WebFilter
return chain.filter(exchange.mutate()
    .response(exchange.getResponse())
    .build())
    .then(Mono.fromRunnable(() ->
        exchange.getResponse().getHeaders()
            .set("X-RateLimit-Remaining", String.valueOf(remaining))));
```

---

## Authentication

**Use Bearer tokens. Never API keys in query params.**

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

| Code | Meaning | When |
|------|---------|------|
| 401 | Unauthorized | Token missing, expired, or invalid signature |
| 403 | Forbidden | Token valid, but role/scope insufficient |

Never return 403 when the token is missing — that is 401.

---

## Error Response Format

Each service declares **one** error body shape in its OpenAPI spec and uses it for every error, including
framework 404/405/422 and the catch-all 500. Two shapes are in use in this toolkit's references, and they are
**not** the same wire format:

| Shape | Where the references use it | Human-readable text | Field errors |
|-------|----------------------------|---------------------|--------------|
| RFC 9457 `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`) | Spring `ProblemDetail` (`java-spring-api`), NestJS `ProblemDetailsFilter` (`nestjs-api`) | `detail` | extension member (e.g. `errors`) |
| The envelope below (`application/json`) | FastAPI (`python-dev/reference/fastapi-error-handling.md`) | `message` | `details` |

Rules for every stack:
- Clients branch on the HTTP status (and a machine `code` when present), never on the text.
- A client that may call services of both shapes reads human text from `detail`, else `message`
  (`angular-ui-patterns/reference/error-handling.md` `toApiError` does this), and shows it only when it is a string.
- 5xx bodies stay opaque (no exception text, stack or SQL) in either shape.
- When you add a machine code or request id to RFC 9457, add them as extension members (`code`, `requestId`).

The envelope:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "details": [
    {
      "field": "email",
      "message": "Must be a valid email address"
    }
  ],
  "timestamp": "2025-10-16T12:00:00Z",
  "path": "/api/v1/users",
  "requestId": "req_1a2b3c4d"
}
```

| Field | Required | Purpose |
|-------|----------|---------|
| `code` | Yes | Machine-readable error code for programmatic handling |
| `message` | Yes | Human-readable description |
| `details` | No | Per-field validation errors (validation errors only). Never echo the submitted `value`: it may be a password or token |
| `timestamp` | Yes | ISO 8601 UTC |
| `path` | Yes | The request path — aids log correlation |
| `requestId` | Yes | Include in support requests for log correlation |

---

## Caching

### Cache-Control Headers

```
# Client-cacheable responses
Cache-Control: public, max-age=3600

# Authenticated responses — user-specific data
Cache-Control: private, max-age=300

# No caching — mutations, sensitive data
Cache-Control: no-cache, no-store, must-revalidate
```

### ETags and Conditional GET (304 Not Modified)

ETags prevent re-downloading unchanged resources. On large list responses, this is significant.

**Python FastAPI:**
```python
import hashlib
from fastapi import Response, Header
from fastapi.responses import Response as FastAPIResponse

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    response: Response,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    user = await user_service.get(user_id)
    etag = f'"{hashlib.md5(user.model_dump_json().encode()).hexdigest()}"'
    if if_none_match == etag:
        return FastAPIResponse(status_code=304)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=300"
    return user
```

**NestJS:**
```typescript
@Get(':id')
async findOne(
  @Param('id') id: string,
  @Headers('if-none-match') ifNoneMatch: string,
  @Res({ passthrough: true }) res: Response,
) {
  const user = await this.usersService.findOne(id);
  const etag = `"${createHash('md5').update(JSON.stringify(user)).digest('hex')}"`;
  if (ifNoneMatch === etag) {
    res.status(304).send();
    return;
  }
  res.setHeader('ETag', etag);
  res.setHeader('Cache-Control', 'private, max-age=300');
  return user;
}
```

**Spring Boot WebFlux:**
```java
@GetMapping("/{id}")
public Mono<ResponseEntity<UserResponse>> getUser(
    @PathVariable String id,
    @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false) String ifNoneMatch) {
  return userService.findById(id)
      .map(user -> {
          String etag = '"' + DigestUtils.md5DigestAsHex(
              user.toString().getBytes()) + '"';
          if (etag.equals(ifNoneMatch)) {
              return ResponseEntity.status(304).<UserResponse>build();
          }
          return ResponseEntity.ok()
              .eTag(etag)
              .cacheControl(CacheControl.maxAge(300, TimeUnit.SECONDS).cachePrivate())
              .body(user);
      });
}
```

---

## Idempotency Keys

Required for any mutation that should not be applied twice — payments, orders, notifications.

**Request:**
```
POST /api/v1/orders
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{ "product_id": "abc", "quantity": 1 }
```

**Behavior:**
- First request: process + cache response with the key (TTL: 24h)
- Duplicate request with same key: return cached response immediately (200 OK, not 201)
- Different key: fresh processing

**Python FastAPI:** the key check and the write must be one atomic step: "read key, then write" lets two
concurrent retries both pass the check.
```python
@router.post("/orders", status_code=201)
async def create_order(
    body: CreateOrderRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", max_length=128)],
    user: CurrentUser, response: Response, service: OrderServiceDep,
) -> OrderResponse:
    # one transaction: INSERT key ON CONFLICT DO NOTHING RETURNING, write, store response, commit
    result, replayed = await service.create_idempotent(user.id, idempotency_key, body)
    if replayed:
        response.status_code = 200            # replay, never re-execute
    return result
```
Scope the key to the caller, store a request fingerprint (same key + different body → 422/409), add a TTL.
Executed on PostgreSQL: 8 concurrent calls produced 1 order. Code and the Redis caveat:
`python-dev/reference/fastapi-architecture-and-config.md` §7.

**NestJS:**
```typescript
@Post()
@HttpCode(201)
async create(
  @Body() dto: CreateOrderDto,
  @Headers('Idempotency-Key') idempotencyKey: string,
  @Res({ passthrough: true }) res: Response,
): Promise<OrderResponse> {
  const cached = await this.idempotencyService.get(idempotencyKey);
  if (cached) {
    res.status(200);
    return cached;
  }
  const order = await this.ordersService.create(dto);
  await this.idempotencyService.set(idempotencyKey, order, 86400);
  res.setHeader('Location', `/api/v1/orders/${order.id}`);
  return order;
}
```

**Spring Boot WebFlux:**
```java
@PostMapping
public Mono<ResponseEntity<OrderResponse>> createOrder(
    @RequestBody @Valid CreateOrderRequest request,
    @RequestHeader("Idempotency-Key") String idempotencyKey) {
  return idempotencyStore.get(idempotencyKey)
      .map(cached -> ResponseEntity.ok(cached))
      .switchIfEmpty(
          orderService.create(request)
              .flatMap(order -> idempotencyStore.set(idempotencyKey, order, Duration.ofDays(1))
                  .thenReturn(ResponseEntity.created(URI.create("/api/v1/orders/" + order.id()))
                      .body(order)))
      );
}
```

---

## Bulk Operations

Use for operations on multiple resources in one request. Always return 207 Multi-Status with per-item results.

**Request:**
```
POST /api/v1/users/batch
Content-Type: application/json

{
  "items": [
    { "name": "Alice", "email": "alice@example.com" },
    { "name": "Bob", "email": "bob@example.com" }
  ]
}
```

**Response (207 Multi-Status):**
```json
{
  "results": [
    { "index": 0, "id": "usr_abc", "status": "created" },
    { "index": 1, "id": null, "status": "failed", "error": "EMAIL_EXISTS" }
  ],
  "succeeded": 1,
  "failed": 1
}
```

**Python FastAPI:**
```python
class BulkCreateResult(BaseModel):
    index: int
    id: str | None
    status: Literal["created", "failed"]
    error: str | None = None

class BulkCreateResponse(BaseModel):
    results: list[BulkCreateResult]
    succeeded: int
    failed: int

@router.post("/users/batch", status_code=207)
async def bulk_create_users(body: BulkCreateRequest) -> BulkCreateResponse:
    results = []
    for i, item in enumerate(body.items):
        try:
            user = await user_service.create(item)
            results.append(BulkCreateResult(index=i, id=user.id, status="created"))
        except DuplicateEmailError as e:
            results.append(BulkCreateResult(index=i, id=None, status="failed", error="EMAIL_EXISTS"))
    return BulkCreateResponse(
        results=results,
        succeeded=sum(1 for r in results if r.status == "created"),
        failed=sum(1 for r in results if r.status == "failed"),
    )
```

**NestJS:**
```typescript
@Post('batch')
@HttpCode(207)
async bulkCreate(@Body() dto: BulkCreateUsersDto): Promise<BulkCreateResponse> {
  const results = await Promise.allSettled(
    dto.items.map((item, index) =>
      this.usersService.create(item).then(user => ({ index, id: user.id, status: 'created' as const }))
    )
  );
  return {
    results: results.map((r, index) =>
      r.status === 'fulfilled'
        ? r.value
        : { index, id: null, status: 'failed' as const, error: (r.reason as Error).message }
    ),
    succeeded: results.filter(r => r.status === 'fulfilled').length,
    failed: results.filter(r => r.status === 'rejected').length,
  };
}
```

**Spring Boot WebFlux:**
```java
@PostMapping("/batch")
@ResponseStatus(HttpStatus.MULTI_STATUS)
public Mono<BulkCreateResponse> bulkCreate(@RequestBody @Valid BulkCreateRequest request) {
  return Flux.fromIterable(request.items())
      .index()
      .flatMap(indexed ->
          userService.create(indexed.getT2())
              .map(user -> BulkResult.success(indexed.getT1().intValue(), user.id()))
              .onErrorResume(e -> Mono.just(BulkResult.failure(indexed.getT1().intValue(), e.getMessage())))
      )
      .collectList()
      .map(BulkCreateResponse::fromResults);
}
```

---

## CORS Configuration

**Python FastAPI:**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # from config, EMPTY default; never ["*"] in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
```

**NestJS (in main.ts):**
```typescript
app.enableCors({
  origin: ['https://app.example.com'],
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
  allowedHeaders: ['Authorization', 'Content-Type', 'Idempotency-Key'],
  credentials: true,
});
```

**Spring Boot WebFlux (WebFluxConfigurer):**
```java
@Configuration
public class CorsConfig implements WebFluxConfigurer {
  @Override
  public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
        .allowedHeaders("Authorization", "Content-Type", "Idempotency-Key")
        .allowCredentials(true);
  }
}
```

---

## Health and Monitoring Endpoints

Every service must expose these two endpoints. Do not require auth on `/health`.

```
GET /health           → 200 OK  { "status": "healthy", "version": "1.2.3" }
GET /health/detailed  → 200 OK  { "status": "healthy", "checks": { "database": "ok", "redis": "ok" } }
                      → 503     { "status": "degraded", "checks": { "database": "error", ... } }
```

**Python FastAPI:**
```python
@app.get("/health")
async def health(): return {"status": "healthy", "version": settings.app_version}

@app.get("/health/detailed")
async def detailed_health():
    db_ok = await check_database()
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={"status": "healthy" if db_ok else "degraded", "checks": {"database": "ok" if db_ok else "error"}}
    )
```

**NestJS** — use `@nestjs/terminus`:
```typescript
@Controller('health')
export class HealthController {
  constructor(private health: HealthCheckService, private db: PrismaHealthIndicator) {}

  @Get() check() {
    return this.health.check([() => this.db.pingCheck('database')]);
  }
}
```

**Spring Boot WebFlux** — use Spring Actuator:
```yaml
# application.yml
management:
  endpoints.web.exposure.include: health,info
  endpoint.health.show-details: when-authorized
```

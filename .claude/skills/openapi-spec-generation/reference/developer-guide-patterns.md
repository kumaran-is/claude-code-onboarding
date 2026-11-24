# Developer Guide Patterns

Narrative documentation patterns to accompany OpenAPI specs. Use alongside `openapi-skeleton-template.md` and `code-first-patterns.md`. Covers: 9-section documentation structure, multi-language code examples (all 3 backend stacks), auth flow documentation, error handling guide, and 4 common pitfalls.

---

## 9-Section Documentation Structure

Every API developer guide should include these sections in order:

| # | Section | What Goes Here |
|---|---------|----------------|
| 1 | **Introduction** | What the API does, base URL, API version, support contact |
| 2 | **Authentication** | How to obtain a token, where to send it, token expiry + refresh |
| 3 | **Quick Start** | One working end-to-end example — copy-paste runnable |
| 4 | **Endpoints** | Full details per endpoint, organized by resource |
| 5 | **Data Models** | Schema definitions, field descriptions, validation rules |
| 6 | **Error Handling** | Error code reference, error response format, troubleshooting |
| 7 | **Rate Limiting** | Limits and quotas, headers to check, handling 429 responses |
| 8 | **Changelog** | API version history, breaking changes, deprecation notices |
| 9 | **SDKs and Tools** | Client libraries, Postman collection, OpenAPI spec download link |

---

## Authentication Flow Documentation

Document the full auth lifecycle — obtain token → use token → refresh token. Include for all three stacks.

### Template

```markdown
## Authentication

All API requests require a Bearer token in the `Authorization` header.

### Step 1 — Obtain a Token

**Endpoint:** `POST /api/v1/auth/login`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "your-password"
}
```

**Response (200 OK):**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4...",
  "expiresIn": 3600
}
```

### Step 2 — Use the Token

Include the access token in every request:

```
Authorization: Bearer <accessToken>
```

### Step 3 — Refresh the Token

Access tokens expire after `expiresIn` seconds. Use the refresh token to get a new pair without re-entering credentials.

**Endpoint:** `POST /api/v1/auth/refresh`

**Request:**
```json
{
  "refreshToken": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4..."
}
```

**Response (200 OK):**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "bmV3UmVmcmVzaFRva2Vu...",
  "expiresIn": 3600
}
```

**Error (401 Unauthorized — refresh token expired):**
```json
{
  "code": "REFRESH_TOKEN_EXPIRED",
  "message": "Refresh token has expired. Please log in again."
}
```
```

---

## Multi-Language Code Examples

For every endpoint in the developer guide, provide cURL + the stack-appropriate client. Use these templates.

### Endpoint: `POST /api/v1/users` — Create User

#### cURL (universal — always include)

```bash
curl -X POST https://api.example.com/api/v1/users \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "name": "John Doe",
    "role": "user"
  }'
```

---

#### Java / Spring Boot WebFlux (WebClient)

Matches `code-first-patterns.md` WebFlux conventions — reactive `Mono<T>`, `WebClient`, records.

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

// DTOs — match CreateUserRequest record from code-first-patterns.md
record CreateUserRequest(String email, String name, String role) {}
record User(String id, String email, String name, String status, String role, String createdAt) {}

// WebClient setup
WebClient client = WebClient.builder()
    .baseUrl("https://api.example.com")
    .defaultHeader("Authorization", "Bearer " + accessToken)
    .build();

// Create user
Mono<User> createUser(CreateUserRequest request) {
    return client.post()
        .uri("/api/v1/users")
        .bodyValue(request)
        .retrieve()
        .onStatus(status -> status.value() == 409,
            response -> response.bodyToMono(ErrorResponse.class)
                .flatMap(err -> Mono.error(new DuplicateEmailException(err.message()))))
        .onStatus(status -> status.is4xxClientError(),
            response -> response.bodyToMono(ErrorResponse.class)
                .flatMap(err -> Mono.error(new ApiException(err.code(), err.message()))))
        .bodyToMono(User.class);
}

// Usage
createUser(new CreateUserRequest("user@example.com", "John Doe", "user"))
    .subscribe(
        user -> log.info("Created user: {}", user.id()),
        error -> log.error("Failed to create user", error)
    );
```

**Error record (matches `ErrorResponse` from `complete-api-example.md`):**
```java
record ErrorResponse(String code, String message, List<FieldError> details, String requestId) {}
record FieldError(String field, String message) {}
```

---

#### Python (httpx async client)

Matches the FastAPI models in `code-first-patterns.md` (camelCase on the wire). Executed 2026-11-23 on
Python 3.14.10, httpx 0.28.1, Pydantic 2.14.4 with `httpx.MockTransport`: 201 parses, a 409 raises
`ApiError` carrying the envelope's `requestId`; `mypy --strict` and ruff (including `T20`, no `print`) exit 0.
Create one `httpx.AsyncClient(base_url=..., timeout=...)` per process (lifespan) and pass it in; a new
client per call discards the connection pool.

```python
# users_client.py — typed async client for the Users API (one shared httpx.AsyncClient per process)
from datetime import datetime
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, serialize_by_alias=True)


class CreateUserRequest(ApiModel):
    email: str
    name: str


class User(ApiModel):
    id: UUID
    email: str
    name: str
    status: str
    created_at: datetime


class ErrorResponse(ApiModel):
    code: str
    message: str
    request_id: str | None = None


class ApiError(Exception):
    """Non-2xx answer from the API, carrying the server's error envelope."""

    def __init__(self, status: int, error: ErrorResponse) -> None:
        super().__init__(f"{status} {error.code}")
        self.status, self.error = status, error


async def create_user(client: httpx.AsyncClient, body: CreateUserRequest, access_token: str) -> User:
    response = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {access_token}"},
        json=body.model_dump(mode="json"),
    )
    if response.is_error:
        raise ApiError(response.status_code, ErrorResponse.model_validate(response.json()))
    return User.model_validate(response.json())
```

For a script, `httpx.Client` offers the same calls synchronously; do not add `requests` as a second
HTTP stack.

---

#### TypeScript / NestJS (HttpService / fetch)

Matches the NestJS conventions of the `nestjs-api` skill.

```typescript
// Types — match interfaces from code-first-patterns.md
interface CreateUserRequest {
  email: string;
  name: string;
  role?: "user" | "moderator" | "admin";
}

interface User {
  id: string;
  email: string;
  name: string;
  status: "active" | "inactive" | "suspended";
  role: "user" | "moderator" | "admin";
  createdAt: Date;
}

interface ErrorResponse {
  code: string;
  message: string;
}

// Using NestJS HttpService (injectable)
import { Injectable } from "@nestjs/common";
import { HttpService } from "@nestjs/axios";
import { firstValueFrom } from "rxjs";

@Injectable()
export class UserApiClient {
  constructor(private readonly httpService: HttpService) {}

  async createUser(request: CreateUserRequest, accessToken: string): Promise<User> {
    const response = await firstValueFrom(
      this.httpService.post<User>(
        "https://api.example.com/api/v1/users",
        request,
        { headers: { Authorization: `Bearer ${accessToken}` } },
      ),
    );
    return response.data;
  }
}

// Using native fetch (Node 18+ / browser)
async function createUser(
  request: CreateUserRequest,
  accessToken: string,
): Promise<User> {
  const response = await fetch("https://api.example.com/api/v1/users", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error: ErrorResponse = await response.json();
    throw new Error(`API error ${response.status}: ${error.message}`);
  }

  return response.json() as Promise<User>;
}
```

---

## Error Handling Reference

Include this section in every developer guide. Matches the `Error` schema from `complete-api-example.md`.

### Error Response Format

All errors return the same structure:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Invalid email format",
  "details": [
    { "field": "email", "message": "Must be a valid email address" }
  ],
  "requestId": "req_1a2b3c4d"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Machine-readable error code — use for programmatic handling |
| `message` | string | Human-readable description |
| `details` | array | Per-field validation errors (validation errors only) |
| `requestId` | string | Include in support requests for log correlation |

### HTTP Status Code Reference

| Status | Code Pattern | When It Occurs |
|--------|-------------|----------------|
| 400 | `VALIDATION_ERROR` | Request body or query param fails validation |
| 401 | `UNAUTHORIZED` | Missing or invalid Bearer token |
| 403 | `FORBIDDEN` | Valid token but insufficient permissions |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` / `EMAIL_EXISTS` | Duplicate unique constraint violated |
| 422 | `UNPROCESSABLE_ENTITY` | Request is syntactically valid but semantically wrong |
| 429 | `RATE_LIMITED` | Too many requests — check `Retry-After` header |
| 500 | `INTERNAL_ERROR` | Server error — include `requestId` in support report |

### Handling Errors by Stack

**Java / Spring Boot WebFlux:**
```java
.onStatus(HttpStatusCode::is4xxClientError,
    response -> response.bodyToMono(ErrorResponse.class)
        .flatMap(err -> switch (err.code()) {
            case "NOT_FOUND" -> Mono.error(new NotFoundException(err.message()));
            case "CONFLICT"  -> Mono.error(new ConflictException(err.message()));
            default          -> Mono.error(new ApiException(err.code(), err.message()));
        }))
```

**Python (httpx client):**
```python
if response.is_error:   # map the envelope to a client exception; HTTPException is server-side only
    raise ApiError(response.status_code, ErrorResponse.model_validate(response.json()))
```

**TypeScript / NestJS:**
```typescript
if (!response.ok) {
  const error: ErrorResponse = await response.json();
  throw new HttpException(error.message, response.status);
}
```

---

## Common Pitfalls

### 1. Documentation Gets Out of Sync with Code

**Symptoms:** Code examples don't compile, parameters are wrong, endpoints return different fields.

**Solution:**
- Generate specs from code annotations (`/v3/api-docs` for Spring, `/openapi.json` for FastAPI, an emit script with `@nestjs/swagger` `SwaggerModule.createDocument` for NestJS: `openapi-spec-generation` SKILL.md)
- Add `npx @redocly/cli lint docs/api/openapi.yaml` to CI — fails build on spec drift
- Every PR that changes a controller must update the spec

### 2. Missing Error Documentation

**Symptoms:** Consumers don't know how to handle errors; support tickets spike.

**Solution:**
- Document every `4xx` response code on every endpoint in the OpenAPI spec
- Provide the `requestId` field in error responses for log correlation
- Include troubleshooting examples for the top 3 most common errors

### 3. Broken Code Examples

**Symptoms:** Users copy-paste examples and get immediate failures; onboarding time increases.

**Solution:**
- Test every cURL example against a running dev/staging environment before publishing
- Include the actual base URL pattern (`https://api.example.com/api/v1/`) not placeholders
- For Java/Python/TypeScript examples, confirm they compile against the current DTO/model definitions

### 4. Unclear Parameter Requirements

**Symptoms:** Consumers send invalid requests; high rate of `400 VALIDATION_ERROR` in logs.

**Solution:**
- Mark required vs optional explicitly in OpenAPI (`required: [email, name]` at schema level)
- Document data types and formats (e.g., `format: uuid`, `format: email`, `minimum: 1`)
- Show validation constraints in examples: `"name": "John Doe  // 1-100 chars, required"`
- In Java DTOs, match `@NotBlank`, `@Size`, `@Min` annotations to OpenAPI schema constraints

---

## When to Use This Reference

| Task | Sections to Load |
|------|-----------------|
| Writing a new developer guide from scratch | All 9 sections structure + auth flow + endpoint examples |
| Adding a new endpoint to existing docs | Multi-language examples for that endpoint |
| Debugging consumer integration issues | Error handling reference + pitfall #3 |
| Onboarding a new team member to the API | Quick Start section + auth flow |
| PR review of API docs changes | Pitfalls checklist — verify all 4 |

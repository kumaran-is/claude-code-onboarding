# Code-First OpenAPI Patterns

Generate OpenAPI specs directly from annotated code. Each stack auto-generates the spec from type hints, decorators, or annotations.

## Quick Reference

| Language | Tool | Annotation Style | Output |
|----------|------|------------------|--------|
| **Python** | FastAPI + Pydantic | Type hints + `Field()` | Auto at `/openapi.json` |
| **Java/Kotlin** | springdoc-openapi | `@Operation`, `@Schema` | Auto at `/v3/api-docs` |
| **TypeScript (Fastify)** | zod 4 + fastify-type-provider-zod + @fastify/swagger | zod schemas on the route | `app.swagger()` after `app.ready()` |
| **TypeScript (NestJS)** | `@nestjs/swagger` | Decorators | See the `nestjs-api` skill |

## Extraction Commands

| Stack | Command |
|-------|---------|
| FastAPI | `python -c "import json; from main import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json` |
| Spring Boot | `curl http://localhost:8080/v3/api-docs > openapi.json` |
| Fastify + zod | `node dist/emit-openapi.js` (script below; no server or port needed) |

---

## Java / Spring Boot (springdoc-openapi)

### Dependency

```java
// build.gradle.kts
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webflux-ui:2.8.0")
}
```

### Configuration

```yaml
# application.yml
springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
    tags-sorter: alpha
    operations-sorter: alpha
```

### OpenAPI Config Bean

```java
// OpenApiConfig.java
@Configuration
public class OpenApiConfig {
    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("User Management API")
                .version("2.0.0")
                .description("API for managing users and profiles")
                .contact(new Contact()
                    .name("API Support")
                    .email("api-support@example.com")))
            .addSecurityItem(new SecurityRequirement().addList("bearerAuth"))
            .components(new Components()
                .addSecuritySchemes("bearerAuth", new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")));
    }
}
```

### Annotated Controller

```java
// UserController.java
@RestController
@RequestMapping("/api/v1/users")
@Tag(name = "Users", description = "User management operations")
@SecurityRequirement(name = "bearerAuth")
public class UserController {

    @Operation(
        summary = "List all users",
        description = "Returns paginated list with optional filtering"
    )
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Success",
            content = @Content(schema = @Schema(implementation = UserListResponse.class))),
        @ApiResponse(responseCode = "400", description = "Invalid request",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
        @ApiResponse(responseCode = "401", description = "Unauthorized")
    })
    @GetMapping
    public Mono<UserListResponse> listUsers(
        @Parameter(description = "Page number (1-based)")
        @RequestParam(defaultValue = "1") @Min(1) int page,

        @Parameter(description = "Items per page")
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,

        @Parameter(description = "Filter by status")
        @RequestParam(required = false) UserStatus status,

        @Parameter(description = "Search by name or email")
        @RequestParam(required = false) @Size(min = 2, max = 100) String search
    ) {
        // Implementation
    }

    @Operation(summary = "Create a new user")
    @ApiResponses({
        @ApiResponse(responseCode = "201", description = "User created",
            content = @Content(schema = @Schema(implementation = User.class))),
        @ApiResponse(responseCode = "400", description = "Invalid request"),
        @ApiResponse(responseCode = "409", description = "Email already exists")
    })
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<User> createUser(
        @Valid @RequestBody CreateUserRequest request
    ) {
        // Implementation
    }

    @Operation(summary = "Get user by ID")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Success"),
        @ApiResponse(responseCode = "404", description = "User not found")
    })
    @GetMapping("/{userId}")
    public Mono<User> getUser(
        @Parameter(description = "User ID", required = true)
        @PathVariable UUID userId
    ) {
        // Implementation
    }

    @Operation(summary = "Update user")
    @PatchMapping("/{userId}")
    public Mono<User> updateUser(
        @PathVariable UUID userId,
        @Valid @RequestBody UpdateUserRequest request
    ) {
        // Implementation
    }

    @Operation(summary = "Delete user")
    @DeleteMapping("/{userId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Tag(name = "Admin")
    public Mono<Void> deleteUser(@PathVariable UUID userId) {
        // Implementation
    }
}
```

### DTOs with Schema Annotations

```java
// DTOs with schema annotations
@Schema(description = "User entity")
public record User(
    @Schema(description = "Unique identifier", format = "uuid")
    UUID id,

    @Schema(description = "Email address", format = "email")
    String email,

    @Schema(description = "Display name", minLength = 1, maxLength = 100)
    String name,

    @Schema(description = "Account status")
    UserStatus status,

    @Schema(description = "User role", defaultValue = "user")
    UserRole role,

    @Schema(description = "Created timestamp")
    Instant createdAt
) {}

@Schema(description = "Create user request")
public record CreateUserRequest(
    @Schema(description = "Email address", format = "email", requiredMode = REQUIRED)
    @NotBlank @Email String email,

    @Schema(description = "Display name", minLength = 1, maxLength = 100, requiredMode = REQUIRED)
    @NotBlank @Size(min = 1, max = 100) String name,

    @Schema(description = "User role", defaultValue = "user")
    UserRole role
) {}
```

---

## Python / FastAPI

```python
from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum

app = FastAPI(
    title="User Management API",
    description="API for managing users and profiles",
    version="2.0.0",
    openapi_tags=[
        {"name": "Users", "description": "User operations"},
        {"name": "Admin", "description": "Admin operations"},
    ],
    servers=[
        {"url": "https://api.example.com/v2", "description": "Production"},
        {"url": "http://localhost:8000", "description": "Development"},
    ],
)

# Enums
class UserStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"

class UserRole(str, Enum):
    user = "user"
    moderator = "moderator"
    admin = "admin"

# Models
class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    name: str = Field(..., min_length=1, max_length=100, description="Display name")
    role: UserRole = Field(default=UserRole.user)

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "user@example.com", "name": "John Doe", "role": "user"}]
        }
    }

class User(BaseModel):
    id: UUID = Field(..., description="Unique identifier")
    email: EmailStr
    name: str
    status: UserStatus
    role: UserRole
    created_at: datetime = Field(..., alias="createdAt")

    model_config = {"populate_by_name": True}

class UserListResponse(BaseModel):
    data: List[User]
    pagination: dict

class ErrorResponse(BaseModel):
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")

# Endpoints
@app.get("/users", response_model=UserListResponse, tags=["Users"])
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[UserStatus] = Query(None, description="Filter by status"),
):
    """List users with pagination and filtering."""
    pass

@app.post("/users", response_model=User, status_code=201, tags=["Users"],
          responses={409: {"model": ErrorResponse, "description": "Email exists"}})
async def create_user(user: UserCreate):
    """Create a new user and send welcome email."""
    pass

@app.get("/users/{user_id}", response_model=User, tags=["Users"],
         responses={404: {"model": ErrorResponse}})
async def get_user(user_id: UUID = Path(..., description="User ID")):
    """Get user by ID."""
    pass

@app.delete("/users/{user_id}", status_code=204, tags=["Users", "Admin"])
async def delete_user(user_id: UUID = Path(..., description="User ID")):
    """Delete user permanently."""
    pass

# Export: python -c "import json; from main import app; print(json.dumps(app.openapi(), indent=2))"
```

---

## TypeScript / Fastify + zod 4

Verified 2026-11-23 against zod 4.6.7, fastify 5.12.8, fastify-type-provider-zod 7.0.0, @fastify/swagger 9.9.5, openapi-types 12.1.3 on Node 26.13.1 + TypeScript 6.0.3 strict: `tsc` exit 0, 8 Vitest tests (invalid body → 400, a handler that breaks its response schema → 500, the document's `$ref`, `operationId` and `required` list).

```bash
npm i -E zod@4.6.7 fastify@5.12.8 fastify-type-provider-zod@7.0.0 @fastify/swagger@9.9.5 openapi-types@12.1.3
```

```typescript
// schemas.ts
import { z } from "zod";

export const CreateOrderInput = z.strictObject({        // additionalProperties: false
  customerId: z.uuid(),
  sku: z.string().min(1).max(64),
  quantity: z.int().min(1).max(100),
  note: z.string().max(500).optional(),                 // may be absent
  couponCode: z.string().nullable(),                    // must be present, may be null
  priority: z.enum(["low", "normal", "high"]).default("normal"), // optional in, always present out
});
export const Order = z.object({ id: z.uuid(), status: z.enum(["pending", "confirmed"]), quantity: z.int(), createdAt: z.iso.datetime() });
z.globalRegistry.add(Order, { id: "Order" });           // becomes components.schemas.Order + $ref
export const ErrorBody = z.object({ code: z.string(), message: z.string() });
```

```typescript
// app.ts
import fastifySwagger from "@fastify/swagger";
import Fastify, { type FastifyInstance } from "fastify";
import {
  type ZodTypeProvider, hasZodFastifySchemaValidationErrors, isResponseSerializationError,
  jsonSchemaTransform, jsonSchemaTransformObject, serializerCompiler, validatorCompiler,
} from "fastify-type-provider-zod";
import { CreateOrderInput, ErrorBody, Order } from "./schemas.js";

export async function buildApp(): Promise<FastifyInstance> {
  const app = Fastify();
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);
  app.setErrorHandler((err, req, reply) => {
    if (hasZodFastifySchemaValidationErrors(err)) return reply.code(400).send({ code: "VALIDATION", message: "Request does not match the schema" });
    if (isResponseSerializationError(err)) {
      req.log.error({ err }, "response failed its schema");
      return reply.code(500).send({ code: "INTERNAL", message: "Internal error" });
    }
    return reply.send(err);
  });
  await app.register(fastifySwagger, {
    openapi: { openapi: "3.1.0", info: { title: "Orders API", version: "1.0.0" } },
    transform: jsonSchemaTransform,
    transformObject: jsonSchemaTransformObject,
  });
  app.withTypeProvider<ZodTypeProvider>().post(
    "/orders",
    { schema: { operationId: "createOrder", body: CreateOrderInput, response: { 201: Order, 400: ErrorBody } } },
    async (req, reply) => {
      const order = await createOrder(req.body); // req.body is z.output: priority is always set
      return reply.code(201).send(order);
    },
  );
  await app.ready();
  return app;
}
```

```typescript
// emit-openapi.ts: build with tsc, then `node dist/emit-openapi.js`
import { writeFileSync } from "node:fs";
import { buildApp } from "./app.js";
const app = await buildApp();
writeFileSync("openapi.json", JSON.stringify(app.swagger(), null, 2));
await app.close();
```

What the generated document contains (executed):

| zod | OpenAPI 3.1 (`draft-2020-12`) | Notes |
|---|---|---|
| `.optional()` | omitted from `required` | |
| `.nullable()` | `type: ["string", "null"]`, listed in `required` | With `openapi: "3.0.x"` the transform switches to the `openapi-3.0` target: `nullable: true` |
| `.default("normal")` | `default`, optional in the request body | The request side uses `io: "input"`. `z.toJSONSchema(schema)` alone defaults to `io: "output"`, where the field becomes required |
| `z.strictObject` | `additionalProperties: false` | `z.object` strips unknown keys silently |
| `z.int()` | `type: integer` | |
| registered schema | `components.schemas.Order` and `OrderInput` | Input and output variants are emitted separately |

- Version floor: zod `< 4.6.6` has GHSA-mrhx-c7xc-m3w5 (memory exhaustion validating oversized constrained collections). fastify-type-provider-zod 7.x needs zod `>= 4.2` (it uses `.encode()`/`.decode()`), so the response serializer checks `z.output`.
- Import from `"zod"` (zod 4 is the package root). `z.uuid()`, `z.iso.datetime()` and `z.int()` are the zod 4 forms; `z.string().uuid()` and `.datetime()` still compile but are marked `@deprecated`.
- tsoa is not covered: its latest npm dist-tag is the prerelease 7.0.0-rc.0, and the last stable (6.6.0, December 2024) bundles a TypeScript 5.7 compiler. Re-check before adopting it on TypeScript 6.

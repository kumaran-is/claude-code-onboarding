---
name: nestjs-coding-standard
description: This skill should be activated when reviewing NestJS/TypeScript code or enforcing coding standards in NestJS 12.x services. It covers naming conventions, TypeScript strictness, Zod request/response schemas (Standard Schema), ESM imports, module organization, and error handling.
allowed-tools: Read
metadata:
  triggers: NestJS coding standard, NestJS code review, NestJS best practices, TypeScript backend standard, NestJS style
  related-skills: nestjs-api, code-reviewer, security-reviewer
  domain: backend
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-11-24"
---

## Iron Law

Always load the nestjs-api skill before writing NestJS code; never generate Prisma or Fastify patterns without consulting current documentation.

# NestJS + TypeScript Coding Standards

Standards for readable, maintainable TypeScript code in NestJS 12.x (verified on 12.6.0) + Fastify services. The runtime-verified reference implementation is `../nestjs-api/reference/nestjs-production-baseline.md`.

## Core Principles

- Prefer clarity over cleverness
- Immutable by default; minimize shared mutable state
- Fail fast with meaningful exceptions
- Consistent naming and module structure

## Key Rules

| Rule | Standard |
|------|----------|
| **Naming** | Classes: `PascalCase`, files: `kebab-case`, constants: `UPPER_SNAKE_CASE` |
| **TypeScript Strictness** | `strict: true` always; no `any`, use `unknown` with type guards |
| **Immutability** | `readonly` on injected dependencies; spread for updates, never mutate |
| **Error Handling** | Custom exceptions extend `BaseException`, or built-in ones with a stable code (`new NotFoundException('…', { errorCode: 'ORDER_NOT_FOUND' })`); log + rethrow, never swallow |
| **Schemas** | Zod 4 schemas in `<entity>.schemas.ts`: request `z.strictObject` bound with `@Body({ schema })` / `@Param(name, { schema })` / `@Query({ schema })`, response `z.object` via `@SerializeOptions({ schema })`; `.meta({ id })` names the OpenAPI component; types via `z.infer`. class-validator DTOs only in a codebase that already uses them, never mixed in one module |
| **ESM** | `"type": "module"`; relative imports end in `.js`; `import.meta.dirname`, never `__dirname` or `require()` |
| **Modules** | Feature-first modules; explicit imports/exports, no implicit dependencies |
| **Logging** | Logger per class with structured key-value pairs; never log PII |
| **Testing** | AAA pattern (Arrange-Act-Assert); one assertion focus per test |
| **Null Handling** | Use `null` over `undefined` for explicit absence; schemas say which fields are `.nullable()` vs `.optional()` |
| **Generics** | Explicit return types on public methods; use type inference for locals |
| **Environment** | All required env vars in `.env` with working defaults; no `??` fallbacks in config code; `.env` written via Bash (hooks block Write/Edit) |
| **Auth & tenancy** | Global auth guard (opt out with `@Public()`, built with `Reflector.createDecorator`); JWT verified with pinned `algorithms`, `issuer`, `audience`; tenant/owner id only from the verified token; cross-tenant read → 404 |
| **Tests** | Vitest (`vi.fn()`), never Jest APIs; e2e through the production `configureApp()`; every guard/validation rule has a negative test |
| **Prisma 7.x** | `provider = "prisma-client"` with `output` path; no `url` in schema; use `prisma.config.ts`; PrismaService via composition (not inheritance) with `@prisma/adapter-pg` |

## Project Structure

```
src/
  main.ts → app.module.ts
  config/ → common/ → core/ → features/
    features/<entity>/
      <entity>.module.ts
      <entity>.controller.ts
      <entity>.service.ts
      <entity>.schemas.ts
      <entity>.repository.ts
```

## Code Examples & Detailed Patterns

For naming examples, TypeScript strictness, immutability patterns, schema validation, module organization, error handling, service patterns, controller patterns, logging, formatting, code smells, and testing expectations, Read `reference/nestjs-standards-examples.md`.

**Remember**: Keep code intentional, typed, and observable. Optimize for maintainability over micro-optimizations unless proven necessary.

## TypeScript Immutability Rules

**CRITICAL** — Never mutate objects or arrays directly in NestJS services/controllers.

```typescript
// ✅ ALWAYS: Spread operator for object updates
const updatedUser = { ...user, name: 'New Name', updatedAt: new Date() }
const updatedItems = [...items, newItem]

// ❌ NEVER: Direct mutation
user.name = 'New Name'    // BAD — breaks immutability, causes subtle bugs
items.push(newItem)       // BAD — mutates in place, unpredictable in reactive chains
```

**Why:** Prisma entities and DTOs passed between layers can be shared references. Mutating them corrupts upstream state silently.

### No Magic Numbers

```typescript
// ✅ GOOD: Named constants
const MAX_RETRY_ATTEMPTS = 3
const DEBOUNCE_DELAY_MS = 500
const DEFAULT_PAGE_SIZE = 20

// ❌ BAD: Magic literals
if (retryCount > 3) { }
setTimeout(fn, 500)
.limit(20)
```

### Early Returns Over Deep Nesting

```typescript
// ✅ GOOD: Guard clauses, max 2 levels nesting
if (!user) throw new NotFoundException('User not found')
if (!user.isActive) throw new ForbiddenException('Account suspended')
return this.userRepo.findOrders(user.id)

// ❌ BAD: 4+ levels of nesting
if (user) {
  if (user.isActive) {
    if (order) {
      if (order.isPaid) { ... }
    }
  }
}
```

### Parallel Async (use Promise.all)

```typescript
// ✅ GOOD: Parallel when operations are independent
const [user, orders, stats] = await Promise.all([
  this.userService.findById(userId),
  this.orderService.findByUser(userId),
  this.statsService.forUser(userId),
])

// ❌ BAD: Sequential when not needed
const user = await this.userService.findById(userId)
const orders = await this.orderService.findByUser(userId)
const stats = await this.statsService.forUser(userId)
```

## Error Handling

**Exception hierarchy**: Use `HttpException` subclasses (`NotFoundException`, `BadRequestException`). Global exception filter returns RFC 9457 ProblemDetail.

**Validation failures**: Declare a Zod schema on every parameter. The global `StandardSchemaValidationPipe` returns **400** with `"path: message"` entries (default `errorHttpStatusCode` 400, not 422) and never echoes the input; unknown request keys are rejected by `z.strictObject`. A parameter without `{ schema }` is not validated at all. In a class-validator codebase the same 400 comes from `ValidationPipe` with `whitelist` + `forbidNonWhitelisted`.

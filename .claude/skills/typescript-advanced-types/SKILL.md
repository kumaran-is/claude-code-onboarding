---
name: typescript-advanced-types
description: "Canonical TypeScript type-design skill (TS 6.0) for Angular 22.x, React, NestJS 12.x and MCP servers: runtime validation at boundaries (Zod) vs compile-time types, DTO-to-domain mapping, discriminated unions with exhaustive never checks, typed errors, branded types, generics, conditional/mapped/template literal types. Use when designing shared types, typing API clients or UI state, hardening type safety, or migrating JS to TS."
allowed-tools: Read
metadata:
  triggers: "Generic types, Conditional types, Mapped types, Utility types, Template literal types, Type-safe API client, Type-safe form, DeepPartial, DeepReadonly, Branded types, type inference, Zod, runtime validation, DTO mapping, discriminated union, exhaustive check, assertNever, TypeScript architecture, type safety hardening, shared types"
  related-skills: nestjs-api, angular-spa, mcp-builder, nestjs-coding-standard, typescript-expert
  domain: frontend, backend
  role: specialist
  scope: implementation
  output-format: code
  risk: safe
  source: "antigravity-awesome-skills (community)"
  date_added: "2026-03-14"
last-reviewed: "2026-11-23"
---

# TypeScript Advanced Types

Canonical home for TypeScript type design in this workspace (absorbs the former `typescript-pro`). Compiler options, `tsconfig` layout, project references and type-check performance live in `typescript-expert`.

## Iron Law

Before applying any type pattern, READ the actual TypeScript file first. Do not suggest type changes from memory — verify the actual code (file:line) before making any claim.

## When to Use

- Building type-safe libraries or frameworks
- Creating reusable generic components
- Implementing complex type inference logic
- Designing type-safe API clients
- Building form validation systems
- Creating strongly-typed configuration objects
- Implementing type-safe state management
- Validating API / SSE / model payloads at runtime and mapping DTOs to domain types
- Designing shared type contracts across Angular, React, NestJS or MCP packages
- Migrating JavaScript codebases to TypeScript

## Do Not Use

- The task is unrelated to TypeScript advanced types
- You need a different domain or tool outside this scope (Flutter/Dart, Java, Python)

## Boundaries: runtime validation, DTO → domain, exhaustive unions

Compile-time types describe what you EXPECT; they check nothing that arrives at runtime. `res.json() as Order` compiles for any payload, and a wrong field becomes `undefined` or an `Invalid Date` three components later. Rules:

1. **Parse every untrusted value at the boundary** (HTTP responses, SSE/WebSocket frames, model output, URL/query params, `localStorage`, `postMessage`) with a schema, then work with the inferred type. Angular: `httpResource(..., { parse: Schema.parse })` (stable since Angular 22) or `.pipe(map(v => Schema.parse(v)))` after `HttpClient`.
2. **DTO ≠ domain model.** The DTO mirrors the wire; the domain type is what the app uses (branded ids, `Date`, camelCase). Map in ONE place (service/repository); templates and components receive domain types only.
3. **Model UI and protocol states as discriminated unions** and end every `switch` with `assertNever`, so a new variant is a compile error, not a blank screen.
4. **No `any`.** `unknown` + narrowing (schema, type guard). Enforce with `@typescript-eslint/no-explicit-any` and the type-aware `no-unsafe-*` rules where ESLint is configured.
5. **Failures are typed:** a `Result` union or a typed error kind, never `catch (e: any)`.
6. **Server side, the environment is a boundary too:** parse `process.env` once with a schema at startup. Zod 4 gotchas: `z.string().url()`/`.email()` are deprecated (use `z.url()`, `z.email()`); `z.httpUrl()` rejects IPs, `localhost` and service names like `http://orders:8080`; `z.coerce.number()` turns `''` into `0`; `z.coerce.boolean()` turns `"false"` into `true` (use `z.stringbool()`). Verified examples: `typescript-expert/references/node-service-engineering.md` §3–§5.

Compiled with TypeScript 6.0.3 + Zod 4.6.7 + @types/node 26.6.7 under `typescript-expert/references/tsconfig-strict.json` (`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noPropertyAccessFromIndexSignature`), together with every block of `resources/implementation-playbook.md`, each as its own module; the two fragments that use the `User` type from an earlier block were compiled with that declaration in scope (2026-11-24). Removing a `case` (or adding a variant without one) fails with TS2345 at `assertNever`.

```typescript
import { z } from 'zod';

// 1. Wire shape (DTO): validated at runtime, because the compiler never sees the network.
const OrderDto = z.object({
  id: z.string().min(1),
  status: z.enum(['pending', 'paid', 'cancelled']),
  total_cents: z.number().int().nonnegative(),
  placed_at: z.iso.datetime(),
  note: z.string().optional(),
});
type OrderDto = z.infer<typeof OrderDto>;

// 2. Domain model: the shape the app uses. Branded id, Date, camelCase, no wire quirks.
type OrderId = string & { readonly __brand: 'OrderId' };
interface Order {
  readonly id: OrderId;
  readonly status: OrderDto['status'];
  readonly totalCents: number;
  readonly placedAt: Date;
  readonly note?: string;
}

// 3. One mapper: DTO -> domain. Templates/components only ever receive Order.
function toOrder(dto: OrderDto): Order {
  return {
    id: dto.id as OrderId,
    status: dto.status,
    totalCents: dto.total_cents,
    placedAt: new Date(dto.placed_at),
    ...(dto.note === undefined ? {} : { note: dto.note }), // exactOptionalPropertyTypes: omit, don't assign undefined
  };
}

// 4. Typed failure instead of a thrown any.
type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };
type LoadError = { kind: 'network'; status: number } | { kind: 'invalid-payload'; issues: string[] };

function parseOrder(json: unknown): Result<Order, LoadError> {
  const parsed = OrderDto.safeParse(json);
  if (!parsed.success) {
    return { ok: false, error: { kind: 'invalid-payload', issues: parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`) } };
  }
  return { ok: true, value: toOrder(parsed.data) };
}

// 5. UI state as a discriminated union + exhaustive check.
type OrderView =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'loaded'; order: Order }
  | { state: 'error'; error: LoadError };

function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}

function label(view: OrderView): string {
  switch (view.state) {
    case 'idle': return '';
    case 'loading': return 'Loading…';
    case 'loaded': return `Order ${view.order.id}`;
    case 'error': return view.error.kind === 'network' ? `Network error ${view.error.status}` : 'Unexpected response';
    default: return assertNever(view); // adding a variant without a case is a compile error here
  }
}

export { parseOrder, label, type Order, type OrderView, type LoadError };
```

## Core Type Patterns

### 1. Generics
Create reusable, type-flexible components while maintaining type safety. Use generic constraints (`T extends HasLength`) to narrow what types are accepted. Supports multiple type parameters, default types, and conditional constraints. See playbook §1 for examples.

### 2. Conditional Types
Create types that depend on conditions: `T extends string ? true : false`. Supports `infer` for extracting type components (e.g., return type, promise type, array element type). Distributive conditional types apply over union members automatically. See playbook §2 for examples.

### 3. Mapped Types
Transform existing types by iterating over their properties with `[P in keyof T]`. Supports modifiers (`readonly`, `?`), key remapping via `as`, and filtering properties by type. Enables patterns like `Partial<T>`, `Readonly<T>`, and `Getters<T>`. See playbook §3 for examples.

### 4. Template Literal Types
Create string-based types with pattern matching: `` `on${Capitalize<EventName>}` ``. Enables type-safe event names, path builders, getter/setter name generation. Built-in helpers: `Uppercase`, `Lowercase`, `Capitalize`, `Uncapitalize`. See playbook §4 for examples.

### 5. Utility Types
TypeScript's built-in transformation utilities: `Partial<T>`, `Required<T>`, `Readonly<T>`, `Pick<T,K>`, `Omit<T,K>`, `Exclude<T,U>`, `Extract<T,U>`, `NonNullable<T>`, `Record<K,T>`. Combine with custom mapped types for `DeepPartial<T>` and `DeepReadonly<T>`. See playbook §5 and Pattern 4 for examples.

## Tech Stack Applicability

| Stack | Applicable | Notes |
|-------|-----------|-------|
| Angular 22.x | Yes | Type-safe forms, component inputs, RxJS operator types, signal types, `httpResource` `parse` |
| React 19 | Yes | Props and state unions, typed hooks, schema-parsed fetch results |
| NestJS 12.x | Yes | Type-safe DTOs, guards, interceptors, Prisma query result types |
| MCP Builder (TypeScript) | Yes | Type-safe tool definitions, request/response contracts |
| Flutter / Dart | No | Dart has its own type system — use the flutter-mobile skill |
| Java / Spring Boot | No | Java generics differ significantly — use the java-spring-api skill |
| Python / FastAPI | No | Use Pydantic models via the python-dev skill |

## Resources

`resources/implementation-playbook.md` contains full patterns, checklists, and code samples covering:

- **Core Concepts:** Generics, Conditional Types, Mapped Types, Template Literal Types, Utility Types
- **Advanced Patterns:**
  - Pattern 1: Type-Safe Event Emitter
  - Pattern 2: Type-Safe API Client
  - Pattern 3: Builder Pattern with Type Safety
  - Pattern 4: Deep Readonly / Deep Partial
  - Pattern 5: Type-Safe Form Validation
  - Pattern 6: Discriminated Unions
- **Type Inference Techniques:** `infer` keyword, Type Guards, Assertion Functions
- **Best Practices:** 10 rules including `unknown` over `any`, strict mode, type testing
- **Common Pitfalls and Performance Considerations**

## Related Skills

| Combine With | When |
|-------------|------|
| `nestjs-api` | Typing NestJS DTOs, guards, interceptors, Prisma result shapes with advanced utility types |
| `angular-spa` | Typing Angular reactive forms, component inputs/outputs, RxJS pipe operators |
| `mcp-builder` | Defining type-safe tool schemas, strongly-typed request/response contracts for MCP tools |

---
name: openapi-spec-generation
description: This skill should be used when creating API documentation, generating SDKs, or ensuring API contract compliance. It generates and maintains OpenAPI 3.1 specifications.
allowed-tools: Read
metadata:
  triggers: OpenAPI, Swagger, API specification, OpenAPI 3.1, API documentation, SDK generation, API contract
  related-skills: documentation-generation, java-spring-api, nestjs-api, python-dev
  domain: api-architecture
  role: specialist
  scope: design
  output-format: specification
last-reviewed: "2026-03-15"
---

## Iron Law

Never generate an OpenAPI spec without running it through a validator; always produce machine-parseable YAML/JSON, not prose descriptions.

# OpenAPI Spec Generation

Generate, validate, and maintain OpenAPI 3.1 specifications for RESTful APIs. Supports design-first, code-first, and hybrid approaches across Java/Spring, Python/FastAPI, and TypeScript stacks.

## When to Use

- Creating API documentation from scratch
- Generating OpenAPI specs from existing code
- Designing API contracts (design-first approach)
- Validating API implementations against specs
- Generating client SDKs from specs
- Setting up API documentation portals

## Quick Start

**Design-First:**
1. Copy the minimal skeleton from `reference/openapi-skeleton-template.md` into `openapi.yaml`
2. Add paths and schemas for the domain
3. Validate: `spectral lint openapi.yaml`
4. Preview: `redocly preview-docs openapi.yaml`

**Code-First:**

| Stack | Command |
|-------|---------|
| FastAPI | `uv run python scripts/dump_openapi.py openapi.json` (builds the app from `create_app()`; `reference/code-first-patterns.md`) |
| Spring Boot | `curl http://localhost:8080/v3/api-docs > openapi.json` |
| NestJS (`@nestjs/swagger`) | `nest build && node dist/emit-openapi.js` (script below) |
| Fastify + zod | `node dist/emit-openapi.js` (`reference/code-first-patterns.md`) |

NestJS: build the document with `DocumentBuilder` + `SwaggerModule.createDocument` and write it at build time, without `listen()`. Apply the same global prefix and versioning as `main.ts`, or the paths differ. Decorator patterns: `nestjs-api` skill.

```typescript
// src/emit-openapi.ts
import { writeFileSync } from 'node:fs';
import { Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { AppModule } from './app.module.js';

async function emit(): Promise<void> {
  const app = await NestFactory.create<NestFastifyApplication>(AppModule, new FastifyAdapter(), { logger: false });
  const config = new DocumentBuilder().setTitle('Orders API').setVersion('1').addBearerAuth().build();
  writeFileSync('openapi.json', JSON.stringify(SwaggerModule.createDocument(app, config), null, 2));
  await app.close();
}

emit().catch((error: unknown) => {
  new Logger('EmitOpenApi').error('openapi emit failed', error instanceof Error ? error.stack : String(error));
  process.exit(1);
});
```

## Process Steps

### Step 1: Choose Approach

| Approach | When to Use | Reference |
|----------|-------------|-----------|
| **Design-First** | New APIs, contracts, external consumers | `reference/openapi-skeleton-template.md` |
| **Code-First** | Existing APIs, rapid iteration | `reference/code-first-patterns.md` |
| **Hybrid** | Evolving APIs, keep spec in sync | Both references above |

### Step 2: Generate the Spec

**Design-first** -- Read `reference/openapi-skeleton-template.md` for the starter template. Copy the minimal skeleton, then customize paths, schemas, and security for the domain.

**Code-first** -- Read `reference/code-first-patterns.md` for annotated examples in:
- Java/Spring Boot (springdoc-openapi) -- annotations, config bean, DTOs
- Python/FastAPI -- Pydantic models, type hints, endpoint decorators
- TypeScript/Fastify + zod -- zod route schemas, `@fastify/swagger` (NestJS: `@nestjs/swagger`, script above)

### Step 3: Add a Complete Example (if needed)

Read `reference/complete-api-example.md` for a full User Management API spec demonstrating all features: CRUD paths, pagination, filtering, error responses, rate limiting headers, security schemes, and reusable components.

### Step 4: Validate and Lint

Read `reference/validation-and-linting.md` for:
- Spectral configuration (`.spectral.yaml`)
- Redocly configuration
- Validation commands
- Custom linting rules (naming conventions, required fields)

### Step 5a: Write the Developer Guide (if needed)

Read `reference/developer-guide-patterns.md` for:
- 9-section documentation structure (Introduction → Authentication → Quick Start → Endpoints → Data Models → Errors → Rate Limiting → Changelog → SDKs)
- Auth flow documentation template (obtain → use → refresh token)
- Multi-language code examples for all 3 backend stacks: Java/Spring Boot WebFlux (WebClient), Python/FastAPI (httpx async), TypeScript/NestJS (fetch with `AbortSignal.timeout`)
- Error handling reference (status codes, error response format, per-stack handling patterns)
- 4 common pitfalls with solutions (sync drift, missing errors, broken examples, unclear parameters)

### Step 5b: Generate SDKs and Set Up CI/CD

Read `reference/sdk-and-cicd.md` for:
- SDK generation commands (TypeScript, Python, Java, Dart)
- GitHub Actions workflow for validation
- Full CI/CD pipeline (validate, generate, publish)

## Reference Files

| File | Content | Size |
|------|---------|------|
| `reference/openapi-skeleton-template.md` | Minimal starter skeleton, structure overview, customization checklist | ~5KB |
| `reference/code-first-patterns.md` | Java/Spring, Python/FastAPI, TypeScript/Fastify + zod annotated examples | ~10KB |
| `reference/validation-and-linting.md` | Spectral rules, Redocly config, validation commands, common mistakes and best practices | ~5KB |
| `reference/sdk-and-cicd.md` | SDK generation commands, GitHub Actions workflows | ~5KB |
| `reference/complete-api-example.md` | Full User Management API with all OpenAPI features | ~10KB |
| `reference/developer-guide-patterns.md` | 9-section doc structure, auth flow template, multi-language code examples (Java WebFlux / Python FastAPI / TypeScript NestJS), error handling reference, 4 common pitfalls | ~8KB |

## Resources

- [OpenAPI 3.1 Specification](https://spec.openapis.org/oas/v3.1.0)
- [Swagger Editor](https://editor.swagger.io/)
- [Redocly](https://redocly.com/)
- [Spectral](https://stoplight.io/open-source/spectral)
- [OpenAPI Generator](https://openapi-generator.tech/)
- [springdoc-openapi](https://springdoc.org/)

## Error Handling

**Schema validation failures**: Run the spec through an OpenAPI validator before committing. Fix all `$ref` resolution errors first.

**Breaking changes detected**: When modifying existing endpoints, check for removed fields, changed types, or new required parameters. Document breaking changes in the spec description.

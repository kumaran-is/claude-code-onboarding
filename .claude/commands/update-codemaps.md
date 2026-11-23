---
description: "Generate or refresh token-lean architecture snapshots in docs/CODEMAPS/ via the doc-updater agent."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
---

# /update-codemaps — Generate Token-Lean Architecture Snapshots

Generates and updates `docs/CODEMAPS/` — compact, <1000-token snapshots of each service layer. Used to orient sub-agents and new sessions without loading entire codebases.

## What It Generates

| File | Covers |
|------|--------|
| `docs/CODEMAPS/spring-api.md` | Java 21 / Spring Boot 3.5.x WebFlux service |
| `docs/CODEMAPS/nestjs-api.md` | NestJS 11.x / Fastify / Prisma service |
| `docs/CODEMAPS/angular-spa.md` | Angular 21.x SPA |
| `docs/CODEMAPS/flutter-mobile.md` | Flutter 3.41.x mobile app |
| `docs/CODEMAPS/python-api.md` | Python 3.14 / FastAPI service |
| `docs/CODEMAPS/architecture.md` | Cross-service integration map |

## Process

1. **Detect which services exist** — check for `pom.xml`, `package.json` with NestJS deps, `angular.json`, `pubspec.yaml`, `pyproject.toml` in the project tree
2. **For each detected service**, generate the codemap (see format below)
3. **30% diff gate** — if an existing codemap exists, run `git diff --stat` against the files it covers. If < 30% of covered files changed since last update → skip with note "No significant changes (< 30% diff)"
4. **Write files** to `docs/CODEMAPS/` (create dir if missing)
5. **Write diff summary** to `.reports/codemap-diff.txt`

## Codemap Format

Each codemap file must follow this structure and stay under 1000 tokens:

```markdown
# {Service} Codemap
**Updated:** {ISO-8601 date}  **Stack:** {tech + version}

## Entry Points
- `{file}:{line}` — {one-line description}

## Key Modules / Features
- `{path}/` — {one-line description}

## Shared Utilities
- `{file}` — {one-line description}

## External Dependencies
- {dependency}: {how it's used}

## Data Flow
{1-3 line prose: request → service → DB pattern}

## Known Constraints
- {any non-obvious architectural decisions}
```

## Example: Spring Boot Codemap

```markdown
# Spring Boot API Codemap
**Updated:** 2026-03-29  **Stack:** Java 21 / Spring Boot 3.5.x / WebFlux / R2DBC

## Entry Points
- `src/main/java/.../Application.java:1` — SpringApplication entry
- `src/main/java/.../router/ApiRouter.java:20` — WebFlux functional route definitions

## Key Modules / Features
- `src/main/java/.../features/auth/` — JWT authentication, token validation
- `src/main/java/.../features/users/` — User CRUD, role management

## Shared Utilities
- `src/main/java/.../common/error/GlobalErrorHandler.java` — WebExceptionHandler
- `src/main/java/.../common/security/CorrelationIdFilter.java` — MDC tracing

## External Dependencies
- PostgreSQL (R2DBC): async reactive queries via R2dbcRepository
- Firebase Auth: token verification in JwtAuthFilter

## Data Flow
HTTP request → RouterFunction → Handler → Service → R2dbcRepository → PostgreSQL
All reactive — Mono/Flux all the way down, no blocking calls.

## Known Constraints
- No JPA — R2DBC only (reactive stack)
- WebFlux functional endpoints (not @Controller annotations)
```

## Diff Summary Format

`.reports/codemap-diff.txt`:
```
Codemap Update — {date}
=======================
spring-api.md    UPDATED  (45% files changed since last update)
nestjs-api.md    SKIPPED  (12% files changed — below 30% threshold)
angular-spa.md   CREATED  (new service detected)
flutter-mobile.md UPDATED (67% files changed since last update)
python-api.md    NOT FOUND (no pyproject.toml detected)
architecture.md  UPDATED
```

## Rules

- Keep each codemap under 1000 tokens (roughly 700 words)
- Freshness date is mandatory — stale codemaps are worse than no codemaps
- Do NOT include implementation details — paths and descriptions only
- Do NOT auto-load codemaps into context — they are reference files for agents
- If `docs/CODEMAPS/` does not exist, create it
- If `.reports/` does not exist, create it
- Dispatches: `.claude/agents/doc-updater.md`

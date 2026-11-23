---
description: Scaffold a new NestJS 11.x REST API on Fastify with Prisma 7, global JWT auth, validation, rate limiting and Vitest — from the skill's verified templates
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold NestJS API

**Project name:** $ARGUMENTS (default to "my-nestjs-api" if not provided)

All file contents come from the `nestjs-api` skill. The project is written from those templates rather than generated
by the Nest CLI: the CLI template is Express + Jest, which this stack replaces, so generating and then rewriting it adds
steps and drift. Do not run a project creator (`nest new`) — the scaffold hook blocks it and it is not needed.

## Steps

1. **Create `.gitignore` first** — before any other file: `node_modules/`, `dist/`, `coverage/`, `src/generated/`, `.env`, `*.pem`, `*.key`, `.DS_Store`.
2. **Read the skill** — `nestjs-api/SKILL.md`, then `reference/nestjs-config-npm-ts.md` (versions, `package.json`, tsconfig, Vitest, ESLint) and `reference/nestjs-production-baseline.md` (source files).
3. **Check versions** — for each pinned package, `npm view <pkg>@<major> version`. If a newer patch exists on the same major, use it; if a package is not found, stop and report it (never guess a package name).
4. **Write `package.json`** from `nestjs-config-npm-ts.md`, then install with exact pins: `npm install` (lockfile committed). Keep NestJS packages on one major.
5. **Write config files** — `tsconfig.json`, `tsconfig.build.json`, `vitest.config.mts`, `vitest.e2e.config.mts`, `eslint.config.mjs`, `prisma.config.ts`, `prisma/schema.prisma`.
6. **Write source** from the baseline — `src/main.ts`, `src/configure-app.ts`, `src/app.module.ts`, `src/config/env.ts`, `src/auth/*` (token verifier, global guard, decorators), `src/common/*` (problem+json filter, throttle tracker), `src/health.controller.ts`, and one example feature module under `src/features/<entity>/` (the baseline's `src/orders/` files) with a tenant-scoped repository. Required directories after this step: `src/config/`, `src/common/`, `src/auth/`, `src/features/`.
7. **Write tests** — `test/jwt-fixture.ts`, the unit specs and `test/app.e2e-spec.ts` from the baseline (they include the negative cases).
8. **Infrastructure** — `Dockerfile` and `docker-compose.dev.yml` from `reference/nestjs-templates-infrastructure.md`; `.env` written via **Bash** with local defaults matching docker-compose (no real secrets).
9. **Generate and verify** — run each and quote its exit code; any non-zero exit stops the scaffold:
   - `npx prisma generate`
   - `npm run typecheck`
   - `npm run lint`
   - `npx vitest run`
   - `npm run test:e2e`
   - `npm audit --audit-level=high` (fix, or document an `overrides` entry with the advisory id)
10. **Report** — files created, each command with its exit code, and anything NOT RUN (for example Docker build without a running daemon).

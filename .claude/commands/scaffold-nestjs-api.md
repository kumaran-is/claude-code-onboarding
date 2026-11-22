---
description: Scaffold a new NestJS 11.x REST API project with Fastify, Prisma, structured logging, and proper module structure
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold NestJS API

**Project name:** $ARGUMENTS (default to "my-nestjs-api" if not provided)

Delegate to the `nestjs-api` skill for all patterns, templates, and reference files.

## Steps

1. **Create `.gitignore` first** — before any other file. Include: `node_modules/`, `.env`, `*.pem`, `*.key`, `dist/`, `coverage/`, `.turbo/`, `.DS_Store`
2. Read the `nestjs-api` skill and its reference files for exact code templates
3. Create NestJS project — `CC_SCAFFOLD=scaffold-nestjs-api npx @nestjs/cli new <name> --package-manager npm --strict --skip-git` (the `CC_SCAFFOLD=` prefix is the per-command authorization `block-raw-scaffold.sh` requires)
3. Install dependencies (Fastify adapter, Prisma, config, swagger, terminus, throttler, validators, helmet) per skill conventions
4. Replace Jest with Vitest (remove jest packages, add vitest + @swc/core + unplugin-swc)
5. Replace Express with Fastify adapter in `src/main.ts`
6. Set up directory structure, config, Prisma 7.x (driver adapter pattern), and modules using skill reference templates
7. Add global exception filter (RFC 9457), validation pipe, logging interceptor, health module, and security middleware
8. Add infrastructure (Dockerfile, docker-compose.dev.yml, .env via Bash)
9. Run `npm audit --audit-level=high` — fix or document any critical/high CVEs before proceeding
10. Verify — `npx tsc --noEmit`

---
name: codebase-onboarding
description: "Analyse an unfamiliar repository and produce an architecture map, entry points, conventions and a tailored CLAUDE.md. Use when joining a repo or generating/refreshing CLAUDE.md. Not for explaining one file (code-explainer)."
allowed-tools: Glob, Grep, Read, Bash, Write
metadata:
  triggers: analyze codebase, onboard to project, generate CLAUDE.md, understand project structure, map architecture, new repository, joining new team
  related-skills: architecture-design, java-spring-api, nestjs-api, python-dev, angular-spa, flutter-mobile
  domain: architecture
  role: specialist
  scope: analysis
  output-format: report
last-reviewed: "2026-03-29"
---

## Iron Law

Read actual files before making any claims about the codebase. Never infer stack from directory names alone — read the config files. A wrong CLAUDE.md is worse than no CLAUDE.md.

# Codebase Onboarding Skill

Systematically maps an unfamiliar codebase in 4 phases, then generates two artifacts: a structured Onboarding Guide and a tailored CLAUDE.md.

## When to Use

- Opening a new client project with Claude Code for the first time
- Joining a new team repository
- User asks "onboard me", "analyze this codebase", "generate a CLAUDE.md"
- Updating an existing CLAUDE.md to reflect current project state

## Four-Phase Analysis Workflow

### Phase 1: Reconnaissance (read config files, not source)

Gather signals without reading all source files. Run these in sequence:

```bash
# 1. Package manifest detection
ls pom.xml package.json pyproject.toml pubspec.yaml angular.json go.mod Cargo.toml Gemfile 2>/dev/null

# 2. Framework fingerprinting — read the detected manifests
cat pom.xml 2>/dev/null | grep -E "<artifactId>spring-boot|webflux|r2dbc" | head -5
cat package.json 2>/dev/null | grep -E "@nestjs/core|@angular/core|fastify|prisma" | head -5
cat pyproject.toml 2>/dev/null | grep -E "fastapi|langchain|langgraph" | head -5
cat pubspec.yaml 2>/dev/null | grep -E "^name:|flutter:|riverpod|go_router" | head -5

# 3. Entry point identification
ls src/main/java 2>/dev/null || ls src/app 2>/dev/null || ls lib/main.dart 2>/dev/null || ls main.py 2>/dev/null

# 4. Directory snapshot (top 2 levels, ignore noise)
find . -maxdepth 2 -type d \
  ! -path "*/node_modules/*" ! -path "*/.git/*" ! -path "*/build/*" \
  ! -path "*/dist/*" ! -path "*/.dart_tool/*" ! -path "*/target/*" \
  ! -path "*/__pycache__/*" ! -path "*/.gradle/*" 2>/dev/null | sort

# 5. CI/CD and tooling detection
ls .github/workflows/ Dockerfile docker-compose*.yml .env.example 2>/dev/null
```

**Stack fingerprint → skill mapping:**
| Detected | Stack | Load Skill |
|----------|-------|-----------|
| `pom.xml` + `spring-boot` | Java 21 / Spring Boot 3.5.x WebFlux | `java-spring-api` |
| `package.json` + `@nestjs/core` | NestJS 11.x / Fastify / Prisma | `nestjs-api` |
| `pyproject.toml` + `fastapi` | Python 3.14 / FastAPI 0.165.0 | `python-dev` |
| `pyproject.toml` + `langchain`/`langgraph` | Agentic AI / LangGraph | `agentic-ai-dev` |
| `angular.json` | Angular 22.3.x / daisyUI 5.8.2 | `angular-spa` |
| `pubspec.yaml` + `flutter:` | Flutter 3.50.x / Dart 3.14.0 | `flutter-mobile` |

### Phase 2: Architecture Mapping

After fingerprinting, read selectively:

```bash
# For each detected stack, read key config files
# Spring Boot
cat src/main/resources/application.yml 2>/dev/null | head -40
find src/main/java -name "*Application.java" -o -name "*Router*.java" 2>/dev/null | head -5

# NestJS
cat src/app.module.ts 2>/dev/null | head -40
find src -name "*.module.ts" 2>/dev/null | head -10

# Python/FastAPI
cat main.py 2>/dev/null | head -40
find src -name "router*.py" -o -name "routes*.py" 2>/dev/null | head -5

# Flutter
cat lib/main.dart 2>/dev/null | head -40
find lib -name "*.dart" -path "*/di/*" -o -path "*/config/*" 2>/dev/null | head -10
```

Map these dimensions:
- **Tech Stack** — Languages, frameworks, databases, build tools
- **Architecture Pattern** — Monolith / microservices / monorepo; reactive vs imperative; API style
- **Key Directories** — top-level folder to purpose mapping
- **Data Flow** — trace a request: entry → validation → service → repository → database

### Phase 3: Convention Detection

```bash
# Naming conventions — sample 5 files from each layer
find src -name "*.java" | head -5 | xargs ls -1 2>/dev/null
find src -name "*.ts" | head -10 | xargs ls -1 2>/dev/null
find lib -name "*.dart" | head -10 | xargs ls -1 2>/dev/null

# Error handling pattern — grep for try/catch patterns
grep -r "catch\|@ExceptionHandler\|@ControllerAdvice\|GlobalExceptionHandler" src/ --include="*.java" -l 2>/dev/null | head -3
grep -r "catch\|ExceptionFilter\|@Catch" src/ --include="*.ts" -l 2>/dev/null | head -3

# Git conventions
git log --oneline -10 2>/dev/null
git branch -a 2>/dev/null | head -5
```

### Phase 4: Generate Artifacts

Produce **both** outputs. Do not skip either.

#### Artifact 1: Onboarding Guide

Save to `docs/ONBOARDING.md` (create if missing, enhance if exists):

```markdown
# {Project Name} — Onboarding Guide
**Generated:** {ISO-8601 date}  **Stack:** {detected stacks}

## Overview
{1-2 sentences: what the project does and who uses it}

## Tech Stack
| Layer | Technology | Version |
|-------|-----------|---------|
| {layer} | {tech} | {version} |

## Architecture
{Architecture pattern: reactive/imperative, monolith/microservices}
{Key architectural decisions detected from code}

## Directory Map
| Path | Purpose |
|------|---------|
| `{path}` | {one-line purpose} |

## Request Lifecycle
{Request flow: entry → validation → business logic → data access — traced from actual code}

## Conventions Detected
- **Naming:** {file naming pattern observed}
- **Error handling:** {pattern observed — @ControllerAdvice / ExceptionFilter / etc.}
- **Testing:** {test framework and patterns found}
- **Git:** {branch naming, commit style observed}

## Common Tasks
```bash
# Build
{actual build command}

# Test
{actual test command}

# Run locally
{actual run command}
```

## Skills to Load
{list skills from fingerprint table above}
```

#### Artifact 2: CLAUDE.md (create or enhance)

If `CLAUDE.md` exists: **enhance, do not replace**. Add detected sections while preserving existing content.

If missing: create at project root. Target: under 100 lines.

```markdown
# {Project Name}

## Tech Stack
{detected stack versions}

## Build & Run
```bash
{commands from package manager}
```

## Code Conventions
- {naming pattern detected}
- {error handling pattern}
- {test framework}

## Key Entry Points
- `{file}:{line}` — {description}

## Skills
{stack-appropriate skills from this workspace}
```

## Anti-Patterns

- **Don't read every source file** — use Glob/Grep for reconnaissance; read selectively only when signals are ambiguous
- **Don't infer from directory names** — a folder called `auth/` might contain Firebase logic, not custom auth. Read the files.
- **Don't replace existing CLAUDE.md** — enhance and preserve existing guidance
- **Don't guess version numbers** — read `pom.xml`, `package.json`, `pubspec.yaml` for exact versions
- **Don't generate CLAUDE.md over 100 lines** — scannable in 2 minutes is the goal

## Error Handling

If a manifest file is detected but unreadable:
```
BLOCKED: Cannot read {file} — permission denied or binary format.
Proceeding without {stack} stack analysis.
```

If no manifest files found at project root:
```
No standard manifest detected at project root.
Searching subdirectories...
[run find . -name "pom.xml" -o -name "package.json" -maxdepth 3]
If still none found: "This may not be a standard project root. Please cd to the correct directory."
```

## Verify Step

After generating both artifacts:
```bash
# Confirm files exist and are non-empty
wc -l docs/ONBOARDING.md CLAUDE.md 2>/dev/null
```

Report: "Generated: docs/ONBOARDING.md ({N} lines), CLAUDE.md ({N} lines)"

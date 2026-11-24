# Skills Integration Guide

## Purpose

Documents skill dependencies, workflow sequences, and auto-loading heuristics.
Use this when deciding which skills to load alongside the primary skill for a task.

---

## Skill Dependency Matrix

When loading the primary skill (left column), also consider loading the companion skills (right column).

| Primary Skill | Also Consider Loading | Why |
|---------------|----------------------|-----|
| `flutter-mobile` | `ui-standards-tokens`, `mobile-design`, `riverpod-patterns` | UI tokens required; Riverpod patterns extend state management; mobile-design covers platform UX |
| `java-spring-api` | `java-coding-standard`, `postgres-best-practices` | Coding standards enforce package layout; postgres-best-practices covers R2DBC query patterns |
| `nestjs-api` | `nestjs-coding-standard`, `postgres-best-practices` | Coding standards enforce module layout; postgres-best-practices covers Prisma query patterns |
| `agentic-ai-dev` | `python-dev`, `prompt-engineering-patterns` | Agent code is Python; prompt patterns govern LLM call design |
| `angular-spa` | `angular`, `angular-best-practices`, `ui-standards-tokens` | Angular covers core APIs; best-practices covers signals/standalone; tokens enforce design system |
| `python-dev` | `uv-package-manager`, `python-patterns` | uv is the required package manager; python-patterns covers async, typing, pydantic |
| `database-schema-designer` | `postgres-best-practices`, `sql-optimization-patterns` | postgres-best-practices covers index strategy; sql-optimization covers EXPLAIN ANALYZE usage |
| `vector-database` | `database-schema-designer`, `postgres-best-practices` | pgvector lives inside PostgreSQL; schema and index rules apply |
| `architecture-design` | `architecture-decision-records`, `plan-mode-review` | ADRs capture decisions; plan-mode-review validates the plan before implementation |
| `mobile-developer` | `mobile-design`, `flutter-mobile` | Mobile developer covers RN/native modules; mobile-design covers cross-platform UX |
| `security-reviewer` | — | Standalone auditor — no companions needed |
| `plan-mode-review` | `architecture-decision-records` | Plans that result in structural decisions need an ADR |

---

## Standard Workflow Sequences

### New Feature (any stack)

```
1. plan-mode-review          — validate approach before writing code
2. {stack skill}             — load the relevant implementation skill
3. code-reviewer             — general quality review
4. security-reviewer         — auth, input validation, secrets
```

### Schema Change

```
1. database-schema-designer  — design schema, migrations
2. postgresql-database-reviewer — verify migration safety, index coverage
```

### New Agentic AI Feature

```
1. agentic-ai-dev            — load skill (includes LangChain/LangGraph patterns)
2. python-dev                — companion for Python conventions
3. prompt-engineering-patterns — prompt design
4. agentic-ai-reviewer       — post-implementation review
```

### Architecture Decision

```
1. architecture-design        — load skill, run /design-architecture
2. plan-mode-review           — validate plan, get approval
3. architecture-decision-records — write ADR before implementation starts
```

### Security Audit (standalone)

```
1. security-reviewer          — dispatch after implementation
2. threat-modeling            — for new services or data flows
```

### New Skill or Agent Creation

```
1. writing-skills             — governs skill authoring conventions
2. (implement the skill)
3. Add a row to the Routing table in `.claude/SKILLS_GUIDE.md` (technology → skill / agent / command / reviewer)
```

### UI / Design System Work

```
1. {stack skill}              — angular-spa or flutter-mobile
2. ui-standards-tokens        — tokens, spacing, color, typography
3. ui-standards-expert        — post-implementation UI review
4. accessibility-auditor      — WCAG 2.2 AA check (web + Flutter)
```

---

## Auto-Loading Heuristics

Map file patterns to the skill that should be loaded automatically.

| File Pattern | Load Skill |
|-------------|------------|
| `*.java`, `pom.xml`, `@RestController`, `@Service` annotations in Java | `java-spring-api` |
| `*.ts` + `@Module()`, `@Controller()`, `@Injectable()` | `nestjs-api` |
| `*.dart`, `pubspec.yaml`, `@riverpod`, `ConsumerWidget` | `flutter-mobile` |
| `angular.json`, `*.ts` with `@Component()` (v22 file names drop the `.component` suffix), `*.routes.ts`, Angular `@Service()` | `angular-spa` |
| `*.py` + `FastAPI`, `@app.get`, `APIRouter` | `python-dev` |
| `*.py` + `LangChain`, `LangGraph`, `StateGraph`, `AgentExecutor` | `agentic-ai-dev` |
| `*.sql`, `db/migration/V*.sql`, `prisma/migrations/` | `database-schema-designer` |
| `pgvector`, `CREATE EXTENSION vector`, `weaviate` | `vector-database` |
| `*.tf`, `*.tfvars`, `terraform {}` blocks | `terraform-skill` |
| `Dockerfile`, `docker-compose.yml` | `docker` |
| `*.spec.ts`, `*.test.ts`, Vitest imports | `nestjs-api` (if NestJS), `angular-spa` (if Angular) or `react-spa` (if React) |
| `test/widget_test.dart`, `flutter_test` imports | `flutter-mobile` |
| `conftest.py`, `pytest`, `*.test.py` | `python-dev` |

---

## Cross-Cutting Skills (always available, no trigger required)

These skills apply across stacks and should be loaded on demand regardless of technology:

| Skill | When to Load |
|-------|-------------|
| `systematic-debugging` | Any bug, crash, or "not working" report |
| `plan-mode-review` | Any non-trivial feature before coding starts |
| `verification-before-completion` | Before declaring any task done |
| `clean-code` | Refactoring sessions |
| `code-reviewer` | After any implementation |
| `security-reviewer` | After any auth, input handling, or data flow change |
| `feature-forge` | Turning a vague request into a concrete spec |
| `the-fool` | Challenging assumptions in a completed plan |
| `subagent-driven-development` | Multi-agent orchestration for large tasks |

---

## Reviewer Agent Selection

After implementation, dispatch the matching reviewer:

| Changed Files | Reviewer Agent |
|--------------|----------------|
| `*.java`, Spring annotations | `spring-boot-reviewer` |
| `*.ts` with NestJS decorators | `nestjs-reviewer` |
| `*.dart`, Riverpod providers | `riverpod-reviewer` |
| `*.dart`, auth / secure storage | `flutter-security-expert` |
| LangChain/LangGraph imports | `agentic-ai-reviewer` |
| SQL migrations, schema files | `postgresql-database-reviewer` |
| pgvector schema | `pgvector-schema-reviewer` |
| Weaviate collections | `weaviate-schema-reviewer` |
| RAG pipeline code | `rag-implementation-reviewer` |
| Auth, crypto, input handling | `security-reviewer` |
| UI components | `ui-standards-expert` |
| Accessibility-sensitive UI | `accessibility-auditor` |
| Any / mixed stack | `code-reviewer` |

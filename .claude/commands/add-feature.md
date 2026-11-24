---
description: Add a new feature end-to-end to an existing project across backend API (Spring, NestJS, FastAPI), web UI (Angular, React) and/or Flutter mobile, with tests routed per target and a /verify gate
argument-hint: "[feature description]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Add Feature End-to-End

Add a complete feature across the stack:

**Feature description:** $ARGUMENTS

## Steps
0. **Already done?** When the feature comes from an issue, run `/status-check <issue>` first: it audits the acceptance criteria against the source. If every criterion is WORKS with executed evidence, report that and propose closing the issue with the evidence instead of implementing it again; implement only the criteria that are BROKEN or NOT IMPLEMENTED.
1. **Analyze** which layers the feature needs (database? backend API? web UI? mobile screen?) and which stacks the repo actually contains. Create only the relevant layers. Load each layer's skill before writing code (`.claude/SKILLS_GUIDE.md` → Routing).
2. **Database** — migration in the stack's tool (Alembic, Flyway, Prisma) with up and down; `postgresql-database-reviewer` before applying.
3. **Backend API** — DTO/schema, repository, service, controller/router, authz check and validation, plus unit and integration tests (JUnit / pytest / Vitest), including one error-path test.
4. **Web UI** — Angular (`angular-spa`) or React (`react-spa`): component, data access, route, loading/empty/error states; unit tests with `ng test` (Vitest) or Vitest + Testing Library; Playwright for the E2E flow.
5. **Flutter mobile** — model, Riverpod provider, screen, widget tests with `flutter test`; device UI/E2E with Maestro only (missing device → BLOCKED).
6. **Verify** — `/verify full` for every touched stack; report PASS / FAIL / BLOCKED / NOT RUN per check with its own exit code, then `/review-code`. Do not report the feature done on a FAIL or BLOCKED.

Tool routing: `.claude/rules/testing-tool-selection.md`. Use instead when: `/new-project` — no project exists yet; `/scaffold-genui-feature` — the feature is an agent-rendered (A2UI) surface.

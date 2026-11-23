# Agent Activation Prompts

> Ready-to-use invocation templates for every agent in the kit. Copy-paste these into Claude Code to activate the right agent with the right context. Each template encodes the institutional knowledge a new developer would otherwise need to learn by reading the agent spec.

---

## How to Use This Guide

1. Find the workflow stage or task below
2. Copy the activation prompt
3. Paste it into Claude Code (or use in a `Task` tool `prompt` parameter)
4. Replace `[bracketed placeholders]` with your actual values

**Tip for sub-agent dispatch:** When using the `Agent` tool, paste the relevant template into the `prompt` parameter. Agents do NOT inherit conversation context — the template provides the required context automatically.

---

## Stage 1 — Planning & Architecture

### Design System Architecture
```
Load the architecture-design skill. I need to design [brief description of system/feature].

Context:
- Tech stack: [list relevant stack components]
- Scale: [expected users/requests/data volume]
- Constraints: [time, budget, team size, existing systems]

Deliverables needed:
- C4 context + container diagrams (Mermaid)
- API contracts for all service boundaries
- ADR for the key technology choice
- Sequence diagram for the primary happy path
```

### Document an Architectural Decision
```
Load the architecture-decision-records skill. I need to write an ADR for [decision topic].

Context:
- We are deciding between: [option A] vs [option B] (vs [option C])
- Driver: [why this decision matters now]
- Constraints: [non-negotiables]

Use the Standard MADR template and score each option using the dual-lens rubric
in reference/adr-scoring.md (Systems /50 + Developer /50).
```

### Write a Feature Spec
```
Load the feature-forge skill. I need a specification for [feature name].

User story: As a [role], I want to [action] so that [outcome].

Known constraints:
- [constraint 1]
- [constraint 2]

Produce: EARS-format acceptance criteria, edge cases, and out-of-scope items.
```

### Domain-Driven Design Analysis
```
Load the ddd-architect skill. Perform DDD analysis for [domain name].

Domain description: [2-3 sentences on what the domain does]
Key entities I'm aware of: [list]
Existing system context: [how it fits the current architecture]

Produce: bounded context map, aggregate roots, domain events, and
anti-corruption layer recommendations where needed.
```

---

## Stage 2 — Implementation

### Scaffold Java Spring Boot API
```
Load the java-spring-api skill. Scaffold a new [resource name] module for
a Spring Boot 3.5.x WebFlux service.

Requirements:
- Endpoints: [list CRUD or specific operations]
- Domain model: [fields and types]
- Persistence: PostgreSQL via R2DBC
- Constraints: [auth, rate limiting, validation rules]

Follow the reactive WebFlux patterns from the skill's reference files.
Consult the Spring WebFlux MCP for current API signatures before writing code.
```

### Scaffold NestJS Module
```
Load the nestjs-api skill. Scaffold a new [module name] module for
a NestJS 11.x Fastify service.

Requirements:
- Endpoints: [list]
- DTO fields: [list with validation rules]
- Prisma model: [schema definition]
- Guards needed: [JWT, roles, etc.]

Follow patterns from the skill's reference files.
Check NestJS docs via Context7 MCP before using any decorator.
```

### Scaffold Python FastAPI Endpoint
```
Load the python-dev skill. Add a [endpoint description] endpoint to
the FastAPI service.

Requirements:
- Route: [METHOD /path]
- Request body: [Pydantic model fields]
- Response: [model or description]
- Auth: [none / JWT / API key]
- Side effects: [DB writes, external calls]

Use uv for dependency management. Follow async patterns from the skill.
```

### Build Angular Feature
```
Load the angular-spa skill. Build a [feature name] feature for the Angular 22.3.x SPA.

Requirements:
- Route: [path]
- Component behaviour: [describe what it shows/does]
- Data source: [API endpoint or service]
- State management: Signals
- Styling: TailwindCSS + daisyUI semantic tokens only — no hardcoded colors

Check Angular CLI MCP for current component/service generation commands.
```

### Build Flutter Screen
```
Load the flutter-mobile skill. Build a [screen name] screen for the Flutter app.

Requirements:
- Screen purpose: [what user accomplishes here]
- Data: [provider or repository]
- State: Riverpod AsyncNotifier or Notifier
- Navigation: [from / to]
- Accessibility: WCAG 2.2 AA — target size >= 24×24 (AA minimum); Flutter house standard 48dp

Run MFRI risk scoring (reference/mfri-scoring.md) before implementing UI.
Check Dart MCP for current Flutter API before writing widget code.
```

### Build LangGraph AI Agent
```
Load the agentic-ai-dev skill. Build a [agent name] agent.

Requirements:
- Goal: [what the agent accomplishes]
- Tools available: [list tools the agent can call]
- State schema: [fields needed in state]
- Entry/exit conditions: [how it starts and ends]
- Error handling: retry on [conditions], escalate on [conditions]

Use LangGraph StateGraph. Check LangChain docs via Context7 MCP
for current graph/node API before writing code.
```

### Build Google ADK Agent
```
Load the google-adk skill. Build a [agent name] agent using Google ADK.

Requirements:
- Agent type: [SequentialAgent / ParallelAgent / LoopAgent / custom]
- Gemini model: [gemini-3.1-flash or specify]
- Tools: [FunctionTool definitions needed]
- Session/memory needs: [stateless / in-memory / persistent]
- FastAPI integration: [yes/no]

Consult ADK MCP for current API signatures before coding.
```

---

## Stage 3 — Code Review

### General Code Review
```
You are the code-reviewer agent. Review the following changed files:
[list file paths]

Scope: [describe what was changed and why]
Tech stack: [languages and frameworks involved]

Check for:
1. Security vulnerabilities (OWASP Top 10)
2. Error handling — no silent failures, every catch must log + rethrow or return error state
3. No deprecated APIs
4. No unused imports or dead code introduced
5. Logic correctness — trace a concrete example through the code

Return verdict: APPROVE / NEEDS_REVIEW / REJECT with file:line evidence for each issue.
```

### NestJS-Specific Review
```
You are the nestjs-reviewer agent. Review the NestJS module changes in:
[list file paths]

Changes summary: [describe what was implemented]

Check for:
- Module registration correctness (providers, imports, exports)
- DTO validation with class-validator
- Prisma transaction patterns
- JWT guard placement
- No console.log (use NestJS Logger)
- Vitest test coverage for happy path + error path

Return verdict: APPROVE / NEEDS_REVIEW / REJECT with file:line evidence.
```

### Spring WebFlux Review
```
You are the spring-reactive-reviewer agent. Review the Spring Boot WebFlux changes in:
[list file paths]

Changes summary: [describe what was implemented]

Check for:
- No blocking calls inside reactive chains (no .block(), no Thread.sleep())
- Resilience4j circuit breaker on external calls
- R2DBC transaction patterns
- Error handling via onErrorResume / doOnError
- WebTestClient tests for all endpoints

Return verdict: APPROVE / NEEDS_REVIEW / REJECT with file:line evidence.
```

### Security Review
```
You are the security-reviewer agent. Perform a security review of:
[list file paths]

Context: [describe what the code does — auth, payment, file upload, etc.]

Check for:
- Hardcoded secrets or credentials
- SQL injection / query string concatenation
- SSRF vulnerabilities
- Unsafe deserialization
- Missing auth/authz checks
- XSS vectors
- File upload without validation

Return verdict: APPROVED (no CRITICAL/HIGH) or NEEDS WORK with
severity, CWE reference, and remediation for each finding.
```

### Database Migration Review
```
You are the postgresql-database-reviewer agent. Review this migration:
[paste migration SQL or file path]

Check for:
- Migration reversibility (up + down)
- Index coverage for expected query patterns
- Constraint correctness (FK, unique, not null)
- No direct table drops without explicit justification
- Lock impact on production traffic (long-running ALTER TABLE)
- EXPLAIN ANALYZE implications

Return verdict: SAFE TO APPLY or NEEDS CHANGES with file:line evidence.
```

### Flutter/Riverpod Review
```
You are the riverpod-reviewer agent. Review the Flutter/Riverpod changes in:
[list file paths]

Changes summary: [describe what was implemented]

Check for:
- Correct provider type (Provider, Notifier, AsyncNotifier, StreamNotifier; no legacy StateNotifier/StateProvider in new code)
- ref.watch only in build methods, ref.read in callbacks
- AsyncValue handling — all 3 states covered (data/loading/error)
- No provider leaks or circular dependencies
- Widget test coverage for loading and error states

Return verdict: APPROVE / NEEDS_REVIEW / REJECT with file:line evidence.
```

---

## Stage 4 — Testing

### Write Tests First (TDD)
```
Load the test-driven-development skill. I need tests for [feature/function name].

Acceptance criteria:
- [criterion 1]
- [criterion 2]
- [criterion 3]

Tech stack: [Jest/Vitest/JUnit/pytest/flutter_test]

Start with Red phase: write failing tests that define success.
Then implement until Green. Then Refactor.
Show test output at each phase.
```

### Debug Failing Test / Unexpected Behavior
```
Load the systematic-debugging skill. I have an unexpected failure.

Symptom: [describe exactly what happens vs what should happen]
Trigger: [what action causes it]
Environment: [local dev / CI / production]
Error output: [paste stack trace or error message]
Files involved: [list]

Do NOT guess the fix. Trace the root cause first using the debugging methodology.
Propose fix only after root cause is confirmed.
```

### Browser / E2E Testing
```
Load the browser-testing skill. Run an E2E test for [user flow description].

URL: [starting URL]
Flow steps:
1. [step 1]
2. [step 2]
3. [expected end state]

Use Chrome DevTools MCP for network + console monitoring.
Use Browser-Use MCP for UI interactions.
Report: console errors, network failures, screenshots at key steps.
```

---

## Stage 5 — Final Validation

### Reality Check (Pre-Merge)
```
You are the reality-checker agent. Validate that [feature name] actually works.

Acceptance criteria:
1. [criterion 1]
2. [criterion 2]
3. [criterion 3]

URL: [feature URL in dev/staging]

Iron Law: Do NOT issue APPROVED without:
- At least one screenshot taken via mcp__chrome-devtools__take_screenshot in this session
- Actual passing test output (not described — pasted)

Default to NEEDS WORK. Re-examine if you find zero issues on first pass.
Check unhappy paths: empty input, API error, mobile viewport (375px).
```

### Output Evaluator (Pre-Commit)
```
You are the output-evaluator agent. Evaluate staged changes before commit.

Changed files: [list]
Purpose: [describe what was implemented]

Score on:
- Correctness: does it do what was asked?
- Completeness: are all acceptance criteria met?
- Safety: no secrets, no dangerous patterns?

Return JSON: { "verdict": "APPROVE|NEEDS_REVIEW|REJECT", "score": N, "issues": [...] }
```

### Security Audit (Pre-Deploy)
```
Load the security-reviewer skill. Run a full security audit before deploying [service/feature].

Changed files since last audit:
[list file paths]

Scope:
- Auth changes: [yes/no — describe]
- Data inputs from users: [yes/no — describe]
- External API calls: [yes/no — describe]
- File handling: [yes/no — describe]

After audit:
- If 0 CRITICAL + 0 HIGH → write Lock Document to docs/approvals/security-YYYY-MM-DD-<commit>.md
- If any CRITICAL/HIGH → list all findings with CWE reference and fix instructions before proceeding
```

---

## Stage 6 — Specialized Workflows

### Multi-Agent Implementation (SDD Pipeline)
```
Load the subagent-driven-development skill. Run a 3-role pipeline for this plan.

Plan file: [path to approved plan in docs/plans/]

Tasks to implement (in order):
1. [task 1 — file:action]
2. [task 2 — file:action]
3. [task 3 — file:action]

Pipeline:
- Implementer: writes code per plan
- Spec Reviewer: checks implementation matches spec (file:line evidence required)
- Quality Reviewer: APPROVE or BLOCK with evidence

Use handoff templates from reference/handoff-templates.md between stages.
```

### Iterate PR Until Green
```
Load the iterate-pr skill. Autonomously fix CI failures and address review feedback
on the current PR until all checks pass.

PR: [number or "current branch"]

Rules:
- Auto-fix high/medium feedback without asking
- Ask user before addressing low/nit feedback
- Reply to review threads after processing each item
- Circuit breaker: stop after 6 full cycles and escalate
- Do NOT push broken code

Start with Step 1: gh pr view to confirm PR exists.
```

### Threat Modeling
```
Load the threat-modeling skill. Perform STRIDE threat model for [system/feature].

System description: [what it does]
Trust boundaries: [list external entities, data flows across boundaries]
Assets to protect: [list sensitive data or operations]
Existing controls: [auth, encryption, network policies]

Produce:
- STRIDE threat table with severity ratings
- Top 3 attack trees
- Security requirements derived from threats
- Mitigations mapped to each threat
```

### Onboard a New Developer
```
A new developer is joining the team. Walk them through our Claude Code setup.

Kit location: [path]
Their background: [languages/frameworks they know]
First task they'll work on: [describe]

Show them:
1. Key agents for their stack (from CLAUDE.md tech stack table)
2. The skill to load before their first task
3. The quality gates they must pass before declaring work done
4. How to use iterate-pr when CI fails

Reference: .claude/SKILLS_GUIDE.md for the full catalog.
```

---

## Quick Reference — Agent by Task

| I need to... | Activation Template |
|---|---|
| Design system architecture | Stage 1 → Design System Architecture |
| Document a tech decision | Stage 1 → Document an Architectural Decision |
| Write feature spec | Stage 1 → Write a Feature Spec |
| Build a Java/Spring API | Stage 2 → Scaffold Java Spring Boot API |
| Build a NestJS module | Stage 2 → Scaffold NestJS Module |
| Build a Python endpoint | Stage 2 → Scaffold Python FastAPI Endpoint |
| Build an Angular feature | Stage 2 → Build Angular Feature |
| Build a Flutter screen | Stage 2 → Build Flutter Screen |
| Build an AI agent | Stage 2 → Build LangGraph AI Agent |
| Review code (general) | Stage 3 → General Code Review |
| Review NestJS code | Stage 3 → NestJS-Specific Review |
| Review Spring code | Stage 3 → Spring WebFlux Review |
| Review for security | Stage 3 → Security Review |
| Review database migration | Stage 3 → Database Migration Review |
| Review Flutter/Riverpod | Stage 3 → Flutter/Riverpod Review |
| Write tests (TDD) | Stage 4 → Write Tests First |
| Debug a failure | Stage 4 → Debug Failing Test |
| Run E2E tests | Stage 4 → Browser / E2E Testing |
| Validate a feature pre-merge | Stage 5 → Reality Check |
| Check staged changes pre-commit | Stage 5 → Output Evaluator |
| Audit security pre-deploy | Stage 5 → Security Audit |
| Run multi-agent implementation | Stage 6 → Multi-Agent Implementation |
| Fix CI + PR feedback | Stage 6 → Iterate PR Until Green |
| Model threats for new feature | Stage 6 → Threat Modeling |

---

## Notes for Sub-Agent Dispatch

When using the `Agent` tool to dispatch a sub-agent, agents **do not inherit** conversation context, `CLAUDE.md`, or rules files. Always include in the prompt:

1. The skill to load (if applicable)
2. The files to read (file paths, not descriptions)
3. The acceptance criteria or checklist to verify against
4. The output format expected (verdict, report, code, etc.)

Without these, sub-agents make assumptions that the context already answered.

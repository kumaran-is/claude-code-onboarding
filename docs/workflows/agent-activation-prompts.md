# Agent Activation Prompts

> Ready-to-use invocation templates for every agent in the kit. Copy-paste these into Claude Code to activate the right agent with the right context. Each template encodes the institutional knowledge a new developer would otherwise need to learn by reading the agent spec.

---

## How to Use This Guide

1. Find the workflow stage or task below and copy the activation prompt.
2. Paste it into Claude Code, or into the `prompt` parameter of the `Agent` tool.
3. Replace `[bracketed placeholders]` with your actual values.

Each reviewer template names the checks that matter most for that task; the agent definition in `.claude/agents/<agent>.md` holds the full checklist, so the template does not repeat it. Sub-agent dispatch rules: [Notes for Sub-Agent Dispatch](#notes-for-sub-agent-dispatch).

---

## Stage 1 — Planning & Architecture

### Design System Architecture
```
Load the architecture-design skill. I need to design [brief description of system/feature].

Context: tech stack [list relevant stack components]; scale [expected users/requests/data
volume]; constraints [time, budget, team size, existing systems]

Deliverables needed: C4 context + container diagrams (Mermaid); API contracts for all service boundaries;
ADR for the key technology choice; Sequence diagram for the primary happy path.
```

### Document an Architectural Decision
```
Load the architecture-decision-records skill. I need to write an ADR for [decision topic].

We are deciding between: [option A] vs [option B] (vs [option C]).
Driver: [why this decision matters now]. Constraints: [non-negotiables].

Use the Standard MADR template and score each option using the dual-lens rubric
in reference/adr-scoring.md (Systems /50 + Developer /50).
```

### Write a Feature Spec
```
Load the feature-forge skill. I need a specification for [feature name].

User story: As a [role], I want to [action] so that [outcome].
Known constraints: [constraint 1]; [constraint 2]

Produce: EARS-format acceptance criteria, edge cases, and out-of-scope items.
```

### Domain-Driven Design Analysis
```
Load the ddd-architect skill. Perform DDD analysis for [domain name].

Domain description: [2-3 sentences on what the domain does]
Key entities I'm aware of: [list]; existing system context: [how it fits the current architecture]

Produce: bounded context map, aggregate roots, domain events, and
anti-corruption layer recommendations where needed.
```

---

## Stage 2 — Implementation

### Scaffold Java Spring Boot API
```
Load the java-spring-api skill. Scaffold a new [resource name] module for
a Spring Boot 3.5.x WebFlux service.

Requirements: endpoints [list CRUD or specific operations]; domain model [fields and types];
Persistence: PostgreSQL via R2DBC; constraints [auth, rate limiting, validation rules]

Follow the reactive WebFlux patterns from the skill's reference files.
Consult the Spring WebFlux MCP for current API signatures before writing code.
```

### Scaffold NestJS Module
```
Load the nestjs-api skill. Scaffold a new [module name] module for
a NestJS 11.x Fastify service.

Requirements: endpoints [list]; DTO fields [list with validation rules];
Prisma model [schema definition]; guards needed [JWT, roles, etc.]

Follow patterns from the skill's reference files.
Check NestJS docs via Context7 MCP before using any decorator.
```

### Scaffold MCP Server (TypeScript)
```
Run /scaffold-mcp-server [name] [stdio|http|both] in the main session, then
load the mcp-builder skill and add [tool names] to src/tools.ts.

Requirements:
- Each tool: zod inputSchema + outputSchema, annotations, a scope in TOOL_SCOPES
- Read-only unless a side effect is approved
- Tests drive the built server with a real MCP Client (stdio and HTTP)
```

### Scaffold Python FastAPI Endpoint
```
Load the python-dev skill. Add a [endpoint description] endpoint to
the FastAPI service.

Requirements: route [METHOD /path]; request body [Pydantic model fields]; response [model or
description]; auth [none / JWT / API key]; side effects [DB writes, external calls]

Use uv for dependency management. Follow async patterns from the skill.
```

### Build Angular Feature
```
Load the angular-spa skill. Build a [feature name] feature for the Angular 22.3.x SPA.

Requirements:
- Route: [path]; component behaviour: [describe what it shows/does]; data source: [API endpoint or service]
- State management: Signals
- Styling: TailwindCSS + daisyUI semantic tokens only — no hardcoded colors

Check Angular CLI MCP for current component/service generation commands.
```

### Build Flutter Screen
```
Load the flutter-mobile skill. Build a [screen name] screen for the Flutter app.

Requirements:
- Screen purpose: [what user accomplishes here]
- Data: [provider or repository]; Navigation: [from / to]
- State: Riverpod AsyncNotifier or Notifier
- Accessibility: WCAG 2.2 AA — target size >= 24×24 (AA minimum); Flutter house standard 48dp

Run MFRI risk scoring (reference/mfri-scoring.md) before implementing UI.
Check Dart MCP for current Flutter API before writing widget code.
```

### Build LangGraph AI Agent
```
Load the agentic-ai-dev skill. Build a [agent name] agent.

Requirements:
- Goal: [what the agent accomplishes]; tools available: [list tools the agent can call]
- State schema: [fields needed in state]; entry/exit conditions: [how it starts and ends]
- Error handling: retry on [conditions], escalate on [conditions]

Use LangGraph StateGraph. Check LangChain docs via Context7 MCP
for current graph/node API before writing code.
```

### Build Google ADK Agent
```
Load the google-adk skill. Build a [agent name] agent using Google ADK.

Requirements:
- Agent type: [LlmAgent / Workflow graph] (SequentialAgent, ParallelAgent, LoopAgent are deprecated in ADK 2.x)
- Gemini model: [gemini-3.1-flash or specify]; tools: [FunctionTool definitions needed]
- Session/memory needs: [stateless / in-memory / persistent]; FastAPI integration: [yes/no]
- Risk tier: [T0–T3] from the ADR (`/ai-decision-record`); evals: golden cases + R1 tests on a fake model

Consult ADK MCP for current API signatures before coding.
```

---

## Stage 3 — Code Review

### General Code Review
```
You are the code-reviewer agent. Review the following changed files:
[list file paths]

Scope: [describe what was changed and why]. Tech stack: [languages and frameworks involved]

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
You are the nestjs-reviewer agent. Review the NestJS module changes in: [list file paths]
Changes summary: [describe what was implemented]

Check for (full list in your agent checklist):
- Module registration correctness (providers, imports, exports); JWT guard placement
- DTO validation with class-validator; Prisma transaction patterns
- No console.log (use NestJS Logger)
- Vitest test coverage for happy path + error path

Return verdict: APPROVE / NEEDS_REVIEW / REJECT with file:line evidence.
```

### Spring WebFlux Review
```
You are the spring-reactive-reviewer agent. Review the Spring Boot WebFlux changes in: [list file paths]
Changes summary: [describe what was implemented]

Check for (full list in your agent checklist):
- No blocking calls inside reactive chains (no .block(), no Thread.sleep())
- Resilience4j circuit breaker on external calls; R2DBC transaction patterns
- Error handling via onErrorResume / doOnError; WebTestClient tests for all endpoints

Return verdict: APPROVE / NEEDS_REVIEW / REJECT with file:line evidence.
```

### Security Review
```
You are the security-reviewer agent. Perform a security review of: [list file paths]
Context: [describe what the code does — auth, payment, file upload, etc.]

Check for (full list in your agent checklist):
- Hardcoded secrets or credentials; SQL injection / query string concatenation
- SSRF vulnerabilities; Unsafe deserialization; Missing auth/authz checks
- XSS vectors; File upload without validation

Return verdict: APPROVED (no CRITICAL/HIGH) or NEEDS WORK with
severity, CWE reference, and remediation for each finding.
```

### Database Migration Review
```
You are the postgresql-database-reviewer agent. Review this migration:
[paste migration SQL or file path]

Check for (full list in your agent checklist):
- Migration reversibility (up + down); Index coverage for expected query patterns
- Constraint correctness (FK, unique, not null); No direct table drops without explicit justification
- Lock impact on production traffic (long-running ALTER TABLE); EXPLAIN ANALYZE implications

Return verdict: SAFE TO APPLY or NEEDS CHANGES with file:line evidence.
```

### AI Feature Review (guardrails, evals, governance records)
```
Review the AI changes in: [list file paths]. Risk tier: [T0–T3]. Autonomy level, if recorded: [A0–A4].

1. Run `python3 .claude/scripts/check-ai-assets.py --root .`; report its exit code and each
   BLOCK / REVIEW / ADVISORY line (ADVISORY is pattern-only, never proof).
2. Dispatch read-only reviewers by what changed: ai-security-reviewer (model calls, tools,
   retrieval, memory), agentic-ai-reviewer or adk-reviewer (framework), rag-implementation-reviewer
   (retrieval), eval-reviewer (evals, golden data, prompt files).
3. Map findings to guardrails G1–G24 and the merge requirements in
   .claude/skills/ai-playbook/reference/engineering-guardrails.md (GR §6); a check nobody ran is NOT RUN.

Verdict: APPROVE / NEEDS_REVIEW / BLOCK per the Review Severity Policy.
```

### Flutter/Riverpod Review
```
You are the riverpod-reviewer agent. Review the Flutter/Riverpod changes in: [list file paths]
Changes summary: [describe what was implemented]

Check for (full list in your agent checklist):
- Correct provider type (Provider, Notifier, AsyncNotifier, StreamNotifier; no legacy StateNotifier/StateProvider in new code)
- ref.watch only in build methods, ref.read in callbacks
- AsyncValue handling — all 3 states covered (data/loading/error)
- No provider leaks or circular dependencies; Widget test coverage for loading and error states

Return verdict: APPROVE / NEEDS_REVIEW / REJECT with file:line evidence.
```

---

## Stage 4 — Testing

### Write Tests First (TDD)
```
Load the test-driven-development skill. I need tests for [feature/function name].

Acceptance criteria: [criterion 1]; [criterion 2]; [criterion 3]
Tech stack: [Jest/Vitest/JUnit/pytest/flutter_test]

Start with Red phase: write failing tests that define success.
Then implement until Green. Then Refactor.
Show test output at each phase.
```

### Debug Failing Test / Unexpected Behavior
```
Load the systematic-debugging skill. I have an unexpected failure.

Symptom: [describe exactly what happens vs what should happen]
Trigger: [what action causes it]; environment: [local dev / CI / production]; files involved: [list]
Error output: [paste stack trace or error message]

Do NOT guess the fix. Trace the root cause first using the debugging methodology.
Propose fix only after root cause is confirmed.
```

### Browser / E2E Testing
Web targets only. A Flutter Android/iOS app is tested with Maestro instead (`.claude/rules/testing-tool-selection.md`).
```
Load the browser-testing skill. Run an E2E test for [user flow description].

URL: [starting URL]
Flow steps: 1. [step 1] 2. [step 2] 3. [expected end state]

Use Chrome DevTools MCP for interactive debugging (network + console monitoring).
Use playwright-cli for scripted interactive steps and @playwright/test for committed E2E specs.
Report: console errors, network failures, screenshots at key steps.
```

---

## Stage 5 — Final Validation

### Reality Check (Pre-Merge)
```
You are the reality-checker agent. Validate that [feature name] actually works.

Acceptance criteria: 1. [criterion 1] 2. [criterion 2] 3. [criterion 3]
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

Changed files: [list]. Purpose: [describe what was implemented]
Score on: Correctness: does it do what was asked? / Completeness: are all acceptance criteria met? /
Safety: no secrets, no dangerous patterns?

Return JSON: { "verdict": "APPROVE|NEEDS_REVIEW|REJECT", "score": N, "issues": [...] }
```

### AI Release Gate (Pre-Deploy)
```
Run /ship. For the AI release gate rows, show: check-ai-assets.py exit code, the R1 eval run
(executed count), the release-candidate eval report for this commit (dataset_version,
prompt_version, model_name, tool_surface_hash, thresholds), the /ai-launch-check verdict for
the risk tier, and for T2/T3 the link to the recorded independent sign-off.
Any missing item is NOT READY or BLOCKED; never infer an approval that has no record.
```

### Security Audit (Pre-Deploy)
```
Load the security-reviewer skill. Run a full security audit before deploying [service/feature].

Changed files since last audit: [list file paths]
Scope (yes/no — describe each): auth changes; data inputs from users; external API calls; file handling

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
Tasks to implement (in order): 1. [task 1 — file:action] 2. [task 2 — file:action] 3. [task 3 — file:action]

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

Rules: Auto-fix high/medium feedback without asking. Ask user before addressing low/nit feedback.
Reply to review threads after processing each item. Circuit breaker: stop after 6 full cycles and escalate.
Do NOT push broken code.

Start with Step 1: gh pr view to confirm PR exists.
```

### Threat Modeling
```
Load the threat-modeling skill. Perform STRIDE threat model for [system/feature].

System description: [what it does]
Trust boundaries: [list external entities, data flows across boundaries]
Assets to protect: [list sensitive data or operations]; existing controls: [auth, encryption, network policies]

Produce: STRIDE threat table with severity ratings; Top 3 attack trees;
Security requirements derived from threats; Mitigations mapped to each threat.
```

### Onboard a New Developer
```
A new developer is joining the team. Walk them through our Claude Code setup.

Kit location: [path]; their background: [languages/frameworks they know]
First task they'll work on: [describe]

Show them: 1. Key agents for their stack (from CLAUDE.md tech stack table) 2. The skill to load before their first task
3. The quality gates they must pass before declaring work done 4. How to use iterate-pr when CI fails

Reference: .claude/SKILLS_GUIDE.md for the full catalog.
```

---

## Quick Reference — Agent by Task

| I need to... | Activation Template |
|---|---|
| Design architecture / document a decision / write a spec | Stage 1 → Design System Architecture / Document an Architectural Decision / Write a Feature Spec |
| Build a Java/Spring API, NestJS module or Python endpoint | Stage 2 → Scaffold Java Spring Boot API / Scaffold NestJS Module / Scaffold Python FastAPI Endpoint |
| Build an Angular feature or Flutter screen | Stage 2 → Build Angular Feature / Build Flutter Screen |
| Build an AI agent | Stage 2 → Build LangGraph AI Agent / Build Google ADK Agent |
| Review code (general, NestJS, Spring, Flutter/Riverpod) | Stage 3 → General Code Review / NestJS-Specific Review / Spring WebFlux Review / Flutter/Riverpod Review |
| Review for security or a database migration | Stage 3 → Security Review / Database Migration Review |
| Review AI code, evals or prompts | Stage 3 → AI Feature Review |
| Write tests (TDD), debug a failure, run web E2E tests | Stage 4 → Write Tests First / Debug Failing Test / Browser / E2E Testing |
| Validate pre-merge, check staged changes pre-commit | Stage 5 → Reality Check / Output Evaluator |
| Gate an AI release or audit security pre-deploy | Stage 5 → AI Release Gate / Security Audit |
| Run multi-agent implementation, fix CI + PR feedback | Stage 6 → Multi-Agent Implementation / Iterate PR Until Green |
| Model threats for new feature | Stage 6 → Threat Modeling |

---

## Notes for Sub-Agent Dispatch

When using the `Agent` tool to dispatch a sub-agent, agents **do not inherit** the conversation context. Custom and general-purpose agents load `CLAUDE.md` and `.claude/rules/`; the built-in Explore and Plan agents do not (see `.claude/rules/leverage-patterns.md`). Always include in the prompt:

1. The skill to load (if applicable)
2. The files to read (file paths, not descriptions)
3. The acceptance criteria or checklist to verify against
4. The output format expected (verdict, report, code, etc.)

Without these, sub-agents make assumptions that the context already answered.

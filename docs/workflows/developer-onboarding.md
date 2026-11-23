# Developer Onboarding

> **When to use**: A new developer joins the team and needs to get productive with the Claude Code workspace, tech stack, and development workflows
> **Time estimate**: 2–4 hours for initial setup; 1–2 days to be fully productive
> **Prerequisites**: Access to the repository, GCP project credentials, required accounts

## Overview

Step-by-step onboarding for a new developer joining a project that uses Claude Code. Covers workspace setup, understanding the skill/agent/hook system, stack-specific environment setup, and first-contribution workflow. Uses `/weaviate:quickstart` as the model for guided onboarding.

---

## Phases

### Phase 1 — Repository and Claude Code Setup

**1. Clone the repository**:
```bash
git clone <repo-url>
cd <project>
```

**2. Install Claude Code**:
```bash
npm install -g @anthropic-ai/claude-code
```

**3. Configure Claude Code with MCP servers**:
```bash
# Check MCP servers configured in the project
cat .claude/settings.json | jq '.mcpServers'

# Required MCPs for this project:
# - context7 (library documentation)
# - angular-cli (Angular tooling)
# - dart-mcp-server (Flutter/Dart tooling)
# - firebase (Firebase integration)
# - chrome-devtools (browser testing)
```

**4. Review the workspace structure**:
```bash
ls .claude/
# agents/     — 41 specialized agents
# skills/     — 60+ skills for each technology domain
# commands/   — 45 slash commands
# hooks/      — 17 bash hooks for quality enforcement
# rules/      — always-loaded rules (core-behaviors, code-standards, etc.)
```

**5. Read CLAUDE.md** — this is the most important file:
```bash
cat CLAUDE.md
```

Key sections to understand:
- Tech Stack (what you're building with)
- Code Conventions table (skill → agent → command mapping)
- Git Workflow (branch naming, commit conventions)
- Important Rules

---

### Phase 2 — Understand the Skill / Agent / Hook System

**Skills** (lazy-loaded instruction sets):
- Located in `.claude/skills/<name>/SKILL.md`
- Load when working in a domain: `"Load the flutter-mobile skill"`
- Contain Iron Laws, patterns, templates, MCP server references

**Agents** (specialized sub-Claude instances):
- Located in `.claude/agents/<name>.md`
- Dispatched for review after implementation
- Examples: `code-reviewer`, `spring-reactive-reviewer`, `security-reviewer`

**Hooks** (automatic enforcement):
- Located in `.claude/hooks/`
- Run automatically on session start, before/after tool use, on stop
- Include: secret scanning, format checking, design system enforcement, session resume

**Hookify rules** (pattern-based guardrails):
- Located in `.claude/hookify.*.local.md`
- Pattern-match code before it's written
- View with `/hookify-list`

**How they work together**:
```
Developer asks Claude to build a feature
    → Hooks run on session start (resume check, lessons inject)
    → Claude loads the appropriate skill (lazy-loaded)
    → Claude implements the feature
    → Hookify rules check each file write (pattern match)
    → Claude dispatches reviewer agent after implementation
    → Hook runs on stop (lessons reminder)
```

---

### Phase 3 — Stack-Specific Environment Setup

**Java / Spring Boot**:
```bash
# Verify Java 21
java --version  # Should be 21.x

# Build and test
./mvnw test
```

**NestJS / Node.js**:
```bash
# Verify Node.js 24.x (NestJS stack; Angular 22 and React use Node 26 LTS)
node --version  # Should be 24.x

# Install dependencies and test
npm ci
npx vitest run
```

**Python / FastAPI**:
```bash
# Verify Python 3.14 with uv
python --version  # Should be 3.14.x
uv --version

# Install and test
uv sync
uv run pytest
```

**Flutter / Dart**:
```bash
# Verify Flutter 3.50
flutter --version

# Get dependencies and test
flutter pub get
flutter test
```

**Angular** (Node 26 LTS; Angular 22 engines `^22.22.3 || ^24.15.0 || ^26.0.0`):
```bash
# Install and serve with the workspace's local CLI
npm ci
npm exec --no -- ng serve
```

**Database**:
```bash
# Start PostgreSQL and services
docker-compose up -d

# Run migrations (Java/Flyway)
./mvnw flyway:migrate

# Verify connection
psql $DATABASE_URL -c "SELECT version();"
```

---

### Phase 4 — Weaviate Quickstart (if using Weaviate)

**Command**: `/weaviate:quickstart`

**6-step onboarding**:
1. Understand available Weaviate commands
2. Sign up for Weaviate Cloud (if needed): [console.weaviate.cloud](https://console.weaviate.cloud)
3. Verify prerequisites: Python, `uv` installed
4. Configure credentials:
   ```bash
   export WEAVIATE_URL="https://<cluster>.weaviate.network"
   export WEAVIATE_API_KEY="..."
   export OPENAI_API_KEY="..."
   ```
5. Test drive: `/weaviate:collections` should return list without error
6. Plan next steps with the team

---

### Phase 5 — First Contribution Workflow

**Your first feature should follow this path**:

1. Check for existing tasks:
   ```
   TaskList  (Claude Code will check automatically on session start)
   ```

2. Pick up a small, well-defined task
3. Create a feature branch:
   ```bash
   git checkout -b feature/TICKET-123-add-order-status
   ```

4. Load the relevant skill for your tech domain:
   ```
   "Load the nestjs-api skill"  (or java-spring-api, flutter-mobile, etc.)
   ```

5. Use TDD workflow:
   - Write a failing test first
   - Implement until it passes
   - See: [`test-driven-development.md`](test-driven-development.md)

6. Use code review before pushing:
   - `/review-code` — runs the relevant reviewer agent
   - Address any CRITICAL or HIGH findings

7. Push and create PR:
   - `/ship` — comprehensive pre-deployment check
   - Create PR: `gh pr create --base develop`

8. Respond to review feedback:
   - See: [`receiving-code-review.md`](receiving-code-review.md)

---

### Phase 6 — Key Commands to Know

```bash
# Check status of current feature
/status-check

# Review your code before committing
/review-code

# Comprehensive pre-deploy check
/ship

# Create PR
gh pr create --base develop

# Security audit
/audit-security

# List active Hookify rules
/hookify-list

# Get help with any workflow
# Just describe what you want to do in plain English
```

---

## Team Setup Checklist

```
Accounts and Access:
[ ] GitHub repository access
[ ] GCP project access (for Cloud Run, Cloud SQL)
[ ] Firebase project access
[ ] Weaviate Cloud account (if applicable)
[ ] App Store Connect / Google Play Console (for mobile)

Local Setup:
[ ] Claude Code installed (claude --version)
[ ] MCP servers configured (context7, angular-cli, etc.)
[ ] All stack runtimes installed (Java 21, Node 24 for NestJS / Node 26 for Angular and React, Python 3.14, Flutter 3.50)
[ ] Docker running (docker-compose up -d succeeds)
[ ] All tests passing (run test suite for your stack)

Understanding:
[ ] Read CLAUDE.md completely
[ ] Understand skill loading pattern
[ ] Know which agent reviews your stack
[ ] Know the branch naming convention
[ ] Know the commit message convention (conventional commits)
[ ] Review active Hookify rules (/hookify-list)
```

---

## Where to Find Help

| Question | Where to Look |
|---------|--------------|
| "What does this code do?" | Read the code, then ask Claude Code |
| "How do I implement X in [stack]?" | Load the skill: "Load the [stack] skill" |
| "What's the right pattern for Y?" | Run `/design-architecture` or check `docs/workflows/` |
| "How do I deploy?" | See `docs/workflows/deployment-ci-cd.md` |
| "There's a bug in production" | See `docs/workflows/production-incident.md` |
| "I need to review my code" | Run `/review-code` |

---

## Related Workflows

- [`ideation-to-spec.md`](ideation-to-spec.md) — how features start
- [`test-driven-development.md`](test-driven-development.md) — how to write code
- [`code-review.md`](code-review.md) — how code is reviewed
- [`pr-shipping.md`](pr-shipping.md) — how code gets merged
- [`new-skill-creation.md`](new-skill-creation.md) — when you want to add your own patterns

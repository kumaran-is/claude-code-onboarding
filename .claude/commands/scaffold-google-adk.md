---
description: Scaffold a new Google ADK service with Gemini, FastAPI, sessions, memory, and production infrastructure
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold Google ADK Service

**Project name:** $ARGUMENTS (default to "my-adk-service" if not provided)

Delegate to the `google-adk` skill for all patterns, templates, and reference files.

## Pre-Scaffold Questions

Before writing any code or running any command, ask ALL of the following. Present DESIGN_SPEC.md for approval before running any scaffold command.

**Always ask:**

1. **What problem will the agent solve?** — Core purpose and capabilities
2. **External APIs or data sources needed?** — Tools, integrations, auth requirements
3. **Safety constraints?** — What the agent must NOT do, guardrails
4. **Deployment preference?** — Prototype first (recommended) or full deployment? If deploying: Agent Engine or Cloud Run?

**Ask based on context:**

- If **retrieval or search over data** mentioned (RAG, semantic search, vector search, embeddings, similarity search, data ingestion) → **Datastore?** Use `--agent agentic_rag --datastore <choice>`:
  - `vertex_ai_vector_search` — for embeddings, similarity search, vector search
  - `vertex_ai_search` — for document search, search engine
- If agent should be **available to other agents** → **A2A protocol?** Use `--agent adk_a2a` (see Option C below)
- If **full deployment** chosen → **CI/CD runner?** Choose `github_actions` (WIF-based, no PAT) or `google_cloud_build` (native GCP)
- If **Cloud Run** chosen → **Session storage?** `cloud_sql` for production → `DatabaseSessionService(db_url="postgresql+asyncpg://...")` (needs `sqlalchemy[asyncio]` + `asyncpg`); `in_memory` for dev/prototype only. `VertexAiSessionService(project=, location=, agent_engine_id=)` is for Agent Engine deployments
- If **background job** chosen (schedule/event trigger, no HTTP) → Use Option D (BackgroundJob pattern) — no FastAPI, no streaming

---

## Steps

1. Read the `google-adk` skill (`SKILL.md` and reference files) before generating any code
2. **Ask the user which setup approach they want:**

   > "Do you want:
   > **A) agent-starter-pack** (production-grade — includes Terraform, Dockerfile, CI/CD, eval harness; recommended for real projects)
   > **B) Manual setup** (simpler, no deployment scaffold — use for learning or quick prototypes)"

3. Proceed based on their answer:

   ### Option A: agent-starter-pack

   ```bash
   uvx agent-starter-pack create $ARGUMENTS --agent adk --prototype --agent-guidance-filename CLAUDE.md -y
   ```

   - Templates: `adk` (default), `adk_a2a` (A2A protocol), `agentic_rag` (RAG with data ingestion)
   - Project name must be ≤26 characters, lowercase, letters/numbers/hyphens only
   - Do NOT `mkdir` the project directory first — the CLI creates it
   - After scaffolding, write `DESIGN_SPEC.md` in the project root
   - Run `make playground` (or `adk web .`) for interactive testing
   - To add deployment later: `uvx agent-starter-pack enhance . --deployment-target agent_engine -y`

   ### Option B: Manual setup

   Initialize project — `uv init $ARGUMENTS --python <the interpreter you deploy>` (verify `google-adk` installs on it; the skill references were executed on 3.14.10)

   Add dependencies:
   ```bash
   uv add "google-adk[db,mcp,otel]==2.15.0" "google-genai==2.34.0" "fastapi[standard-no-fastapi-cloud-cli]==0.165.0" "uvicorn[standard]==0.54.0" "pydantic-settings==2.16.3" "structlog==26.1.0" "sqlalchemy[asyncio]==2.1.9" "asyncpg==0.32.0"
   # google-adk 2.15 requires google-genai>=2.34,<3; McpToolset needs the mcp extra
   uv add --dev "pytest==9.2.0" "pytest-asyncio==1.5.0" "httpx2==2.16.2" "aiosqlite==0.22.1" "ruff==0.17.6" "mypy==2.4.1"
   # pin every dependency exactly (==) to what uv lock resolved; commit uv.lock
   ```

   Create directory structure per `adk-project-config.md`:
   - `src/config.py` — Settings with required `agent_model` and the per-environment auth matrix (`adk-project-config.md` §3)
   - `src/agents/` — Agent definitions with `model=settings.agent_model` (no literal id)
   - `src/tools/` — Tool functions with full docstrings
   - `src/api/routes.py` — POST /chat and POST /stream (`adk-fastapi-integration.md`: principal-owned sessions, timeout, `max_llm_calls`, typed statuses)
   - `src/main.py` — FastAPI app with lifespan: session service + Runner once, `await runner.close()` on shutdown

   Create a sample agent demonstrating: Agent with 1 tool (typed result), POST /chat, POST /stream SSE

   Create `tests/fakellm.py` (scripted model, `adk-testing.md` §2) and `tests/test_agent.py` + `tests/test_api.py` using it — `InMemoryRunner` alone still calls the real model

   Create `.env.example` from the template in `adk-project-config.md` §2 (placeholders only; `.env` is git-ignored)

   Create `Dockerfile` per `adk-project-config.md` §5 (`uv sync --locked`, pinned uv image, non-root, no key in the image)

   ### Option C: A2A Project Template (`adk_a2a`)

   Use when the agent must be callable by other ADK agents via the A2A protocol. **NEVER write A2A code from scratch** — the import paths, `AgentCard` schema, and `to_a2a()` signature change across versions.

   ```bash
   uvx agent-starter-pack create $ARGUMENTS \
     --agent adk_a2a \
     --deployment-target cloud_run \
     --prototype \
     --agent-guidance-filename CLAUDE.md \
     -y
   ```

   - Generates valid A2A imports and Dockerfile — no manual A2A code needed
   - Enables inter-agent calling via A2A protocol between independently deployed agents

   ### Option D: BackgroundJob Pattern

   Use when the agent runs on a schedule or event trigger — not on user request. No HTTP server.

   **Entry point:** `src/job.py`
   ```python
   async def run_job(payload: dict) -> JobResult:
       ...
   ```

   **Trigger:** Cloud Scheduler cron OR Pub/Sub message. No FastAPI server or HTTP layer.

   **ADK usage:** Construct the Agent directly and call `await runner.run_async(...)` — no streaming, no HTTP.

   **Session:** `InMemorySessionService` — jobs are stateless; no `VertexAiSessionService` needed.

   **Directory structure:**
   ```
   src/
     agent.py       # Agent definition
     tools/         # Tool functions
     job.py         # Entry point — run_job()
   tests/
     test_job.py    # Use InMemoryRunner directly
   ```

   **Tests:** `InMemoryRunner` with the scripted fake model. Fake any external status writes — do not call real external services in unit tests.

   **Delivery:** jobs and messages repeat — key side effects on the job/message id, bound each run (timeout + `max_llm_calls`), and report failure (failed job / non-ack), never swallow.

4. Verify (show each command's exit code):
   - `uv sync --locked` (Option B) — lock matches `pyproject.toml`
   - `uv run ruff check src/ tests/` (Option B) or `make lint` (Option A)
   - `uv run mypy src/` (Option B only)
   - `env -u GOOGLE_API_KEY uv run pytest -q` — must pass with no credentials (proves the fake model is used)
5. Report scaffolded files with paths as evidence

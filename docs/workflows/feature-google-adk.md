# Feature Development — Google ADK

> **When to use**: Building an AI agent with Google ADK, Gemini models, Workflow graphs (google-adk 2.x), FastAPI integration
> **Time estimate**: 2–5 hours for initial agent; 1–2 hours per additional tool or subagent
> **Prerequisites**: GCP project configured, ADK credentials set up

## Overview

Full Google ADK agent development lifecycle from scaffold to deployed. Covers the decision between agent-starter-pack (production-grade with Terraform + CI/CD) vs manual setup, observability configuration, evaluation harness, and deployment to Cloud Run or Agent Engine.

---

## Phases

### Phase 1 — Load Skills

**Before anything**: Load `google-adk` skill (`skills/google-adk/SKILL.md`)
**MCP**: Context7 for current ADK API — ADK changes frequently

**Agent types available** (from `agents/google-adk.md`):
- `Workflow` (ADK 2.x) — graph of agents and function nodes: sequence, routing, capped loops, fan-out (`google-adk/reference/adk-agent-types.md` §0)
- `SequentialAgent` / `ParallelAgent` / `LoopAgent` — deprecated in 2.x (`DeprecationWarning`); keep only where the flow must sit under an `LlmAgent`
- `FunctionTool` — wrap Python functions as tools
- `McpToolset` — expose MCP servers as ADK tools

---

### Phase 2 — Scaffold Decision

**Command**: `/scaffold-google-adk [project-name]`
**Source**: `commands/scaffold-google-adk.md`

**Two paths** (from `commands/scaffold-google-adk.md`):

**Option A — agent-starter-pack** (recommended for production):
- Production-grade scaffold with Terraform, Docker, CI/CD pipeline
- Includes evaluation harness out of the box
- Connects to Cloud Run or Agent Engine automatically
- Best for: projects going to production

**Option B — Manual setup** (recommended for prototyping):
- Simpler directory structure
- No deployment scaffold
- Best for: local development, testing ADK capabilities

**Ask user**: `Which setup? (A) agent-starter-pack or (B) manual?`

**Produces**: Project scaffold with selected structure
**Gate**: `adk run` or equivalent launches without error

---

### Phase 3 — Build Agent

**Core structure** (from `skills/google-adk/SKILL.md`):

```
src/<project>/
├── agent.py          # Root agent definition
├── tools/            # FunctionTool definitions
├── subagents/        # Sub-agent definitions
├── prompts/          # System prompts
└── tests/
```

**Agent composition patterns**:

```python
# ADK 2.x: one Workflow graph; run it with Runner(node=root_workflow, ...)
from google.adk import Workflow

# Sequential — agents and plain functions in order
root_workflow = Workflow(name="pipeline", edges=[("START", step1_agent, normalize, step2_agent)])

# Routing — a node returns Event(route=["BUG"]); the dict edge picks the branch
root_workflow = Workflow(name="triage", edges=[
    ("START", classifier_agent, router),
    (router, {"BUG": bug_node, "LOGISTICS": logistics_node}),
])

# Capped loop and fan-out: a @node function with ctx.run_node(...) and a fixed range / asyncio.gather
# (google-adk/reference/adk-agent-types.md §0). SequentialAgent/ParallelAgent/LoopAgent are deprecated.
```

**Tool wrapping**:
```python
@tool
def search_database(query: str) -> dict:
    """Search the internal database. Returns matching records."""
    ...
```

**MCP tools**:
```python
toolset = McpToolset(connection_params=SseServerParams(url="..."))
agent = LlmAgent(tools=[toolset])
```

**Gate**: Agent runs end-to-end on test input

---

### Phase 4 — Observability Setup

**Skill**: `adk-observability-guide` (`skills/adk-observability-guide/SKILL.md`)

**Configure**:
- Cloud Trace for distributed tracing
- Prompt logging for debugging
- BigQuery agent logs for analytics
- ADK monitoring dashboards

**Environment variables** (from skill):
```
GOOGLE_GENAI_USE_ENTERPRISE=true   # GOOGLE_GENAI_USE_VERTEXAI is the deprecated name
GOOGLE_CLOUD_PROJECT=<project>
GOOGLE_CLOUD_LOCATION=<region>
```

**Gate**: Traces visible in Cloud Console on test run

---

### Phase 5 — Evaluation

**Skill**: `adk-eval-guide` (`skills/adk-eval-guide/SKILL.md`)
**Command**: `adk eval`

**8 evaluation criteria** (from `skills/adk-eval-guide/SKILL.md`):
1. `tool_trajectory_avg_score` — correct tools called in right order
2. `response_quality` — response meets user intent
3. `safety_score` — no harmful outputs
4. `latency_p50` / `latency_p95` — meets latency targets
5. `token_efficiency` — cost per task
6. `tool_call_success_rate` — tools execute without error
7. `context_retention` — multi-turn correctness
8. `groundedness` — claims backed by retrieved context (if RAG)

**Write evalset** (from skill): JSON file with input/expected_output/expected_tool_calls
**Run**: `adk eval --evalset_path evals/my_evalset.json`

**Produces**: Evaluation report with scores per criterion
**Gate**: All 8 criteria at target thresholds before deploy

---

### Phase 6 — Deploy

**Skill**: `adk-deploy-guide` (`skills/adk-deploy-guide/SKILL.md`)
**Iron Law** (from skill): `MUST READ adk-deploy-guide BEFORE DEPLOYING ANY ADK AGENT`

**Deployment targets**:

| Target | When to use | Command |
|--------|-------------|---------|
| Cloud Run | Custom container, full control | `gcloud run deploy` |
| Agent Engine (Vertex AI) | Managed ADK runtime | `adk deploy agent_engine` |
| Firebase | Mobile/web apps | Firebase ADK integration |

**Pre-deploy checklist** (from `adk-deploy-guide` skill):
- Evaluation scores meet targets
- Observability configured
- Secrets in Secret Manager (not `.env`)
- Docker image built and tested locally
- Terraform plan reviewed (if agent-starter-pack)

**Gate**: Deploy succeeds, agent responds to test request in production

---

## Quick Reference

| Phase | What to Run | Produces | Gate |
|-------|-------------|----------|------|
| 1 — Load skill | `google-adk` + Context7 MCP | Pattern reference | MCP queried |
| 2 — Scaffold | `/scaffold-google-adk` | Project scaffold (A or B) | `adk run` succeeds |
| 3 — Build | Define tools → subagents → root agent | Working agent | E2E test passes |
| 4 — Observability | `adk-observability-guide` skill | Traces in Cloud Console | Traces visible |
| 5 — Evaluation | `adk eval` | Score report (8 criteria) | All criteria at target |
| 6 — Deploy | `adk-deploy-guide` skill + deploy command | Live agent endpoint | Test request succeeds |

---

## Common Pitfalls

- **ADK API from memory** — ADK evolves rapidly; always query Context7 MCP for current syntax
- **Unbounded loops** — a `LoopAgent` without `max_iterations` or a `@node` loop without a fixed range can run indefinitely and exhaust quota; also cap every run with `RunConfig(max_llm_calls=N)`
- **Tools without docstrings** — Gemini uses the docstring to decide when to call the tool; missing docs = wrong tool selection
- **Skipping evaluation** — eval score below target in prod means users see wrong/unsafe outputs
- **Secrets in `.env` file in Docker** — use Secret Manager; never bake secrets into container images
- **Skipping `adk-deploy-guide`** — deploy configuration details are version-specific and easy to get wrong from memory

## Related Workflows

- [`ideation-to-spec.md`](ideation-to-spec.md) — spec first
- [`deployment-ci-cd.md`](deployment-ci-cd.md) — CI/CD pipeline for the service
- [`cloud-run-terraform.md`](cloud-run-terraform.md) — Terraform for Cloud Run deployment

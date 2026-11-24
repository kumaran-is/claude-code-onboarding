---
name: adk-dev-guide
description: "ADK development lifecycle guardrails — 4-phase workflow (Understand → Build → Evaluate → Deploy), import precision rules, GOOGLE_CLOUD_LOCATION debugging, code preservation, and infinite loop breaking. Load BEFORE google-adk when starting a new ADK agent feature."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: adk dev, adk lifecycle, adk workflow, new adk agent, adk debugging, adk import, GOOGLE_CLOUD_LOCATION
  related-skills: google-adk, adk-eval-guide, adk-deploy-guide
  domain: agentic-ai
  role: specialist
  scope: workflow
  output-format: guide
last-reviewed: "2026-11-23"
---

# ADK Development Guide

Development lifecycle guardrails for AI agents using Google ADK and Gemini models.

## Iron Law

**No phase is done without executed evidence.** Phase 2 ends with tests that pass using a scripted fake model and no credentials; Phase 3 ends with an eval run whose failures fail the command; Phase 4 starts only from a locked, exactly pinned ADK version. Report anything you did not execute as NOT RUN.

## 4-Phase Development Lifecycle

Every ADK agent feature follows this workflow. Skipping phases increases risk of eval failures, infinite loops, and deployment issues.

### Phase 1: Understand Spec
**Before writing any code:**
- Read `DESIGN_SPEC.md` completely — this is the source of truth
- Identify: agent purpose, required tools, safety constraints, success criteria, edge cases
- Flag ambiguities, contradictions, or missing information before proceeding
- Check if similar agent patterns exist in your project already (avoid duplication)
- Clarify: is this a new agent or an enhancement to an existing one?

**Stop if:**
- The spec is vague or self-contradictory
- Required dependencies are unavailable
- The scope exceeds what a single agent should handle

### Phase 2: Build
**Follow these patterns:**
- Use `ToolContext` for session state — never global variables
- Import tools with precision (see ADK Import Precision Rules section below)
- Add `# Fallback:` comment to every tool function
- Tests use `InMemoryRunner` **plus a scripted fake model** — `InMemoryRunner` only swaps services and still calls the real model (`google-adk/reference/adk-testing.md` §2)
- Bound every run: `RunConfig(max_llm_calls=N)`, `asyncio.timeout`, `LoopAgent(max_iterations=N)` (its default is unbounded)
- Development commands:
  - `adk web` — launch ADK playground for interactive testing
  - `uv run pytest tests/ -v` — run unit tests
  - `uv run ruff check src/ && uv run ruff format src/` — lint and format
  - `uv run mypy src/` — type check

**Stop if:**
- Type errors appear when running `mypy`
- Linting fails (`ruff check` returns non-zero)
- Unit tests fail

### Phase 3: Evaluate
**Iterate 5–10 rounds per feature:**
- Create `evalset.json` with: 1 happy path, 1 error path, 1+ edge cases
- Create `eval_config.json` with appropriate eval criteria
- Run: `adk eval ./app evalset.json --config_file_path=eval_config.json --print_detailed_results`
- Review detailed results — identify failure patterns
- Refine agent instructions, tool signatures, or tool implementations
- Re-run until success rate stabilizes
- Common pitfalls: app name must match directory name, state type mismatches, tool return types
- Since 2.13 `adk eval` exits 1 when any case fails or no results were produced (1.29 exited 0); CI can gate on its exit code directly or through pytest + `AgentEvaluator.evaluate` (`adk-deploy-guide` skill, "Eval gate before traffic")

**Stop if:**
- Success rate plateaus below target threshold (defined in eval_config.json)
- Same test case fails repeatedly for unrelated reasons

### Phase 4: Deploy
**Use adk-deploy-guide skill:**
- Choose between Cloud Run (event-driven, full control) or Agent Engine (managed)
- Verify health endpoint responds after deployment
- Run `uv run pytest tests/evals/` locally before opening PR
- Eval gates block merge if accuracy thresholds are not met

---

## DESIGN_SPEC.md as Primary Source of Truth

Every ADK agent project MUST have a `DESIGN_SPEC.md` in the agent service root before any implementation code is written.

### Spec Contents (Required Sections)

```
# Agent Name — Design Spec

## Purpose
One-sentence mission statement.

## Example Use Cases
- User does X, agent responds with Y
- User does A, agent handles error B gracefully

## Required Tools
- tool_name: description and responsibility
- tool_name: description and responsibility

## Safety Constraints
- No [X] without [Y]
- Always [Z] before [A]
- Blocked: [B] under any condition

## Success Criteria
- Agent achieves 90% accuracy on test set
- Tool calls execute in <500ms
- Error recovery succeeds in <1 min

## Edge Cases & Fallbacks
- When tool A fails: [fallback behavior]
- When state is invalid: [reset or error response]
```

### Implementation ↔ Spec Alignment
- Implementation must align with spec — drift = stop and reconcile
- If implementation requires spec change: update spec first, then code
- If spec is impossible to implement: surface this during Phase 1 (Understand), not Phase 2 (Build)

---

## ADK Import Precision Rules

Use the import paths the **installed** package exports; never guess and never copy paths from older docs. Executed against `google-adk==2.15.0`:

```python
# ✅ Works in 2.15
from google.adk.tools import google_search, load_web_page, exit_loop, AgentTool, FunctionTool, ToolContext
from google.adk.code_executors import BuiltInCodeExecutor      # Agent(code_executor=BuiltInCodeExecutor())
from google.adk.runners import InMemoryRunner, Runner
from google.adk.agents import Agent, LlmAgent, SequentialAgent, ParallelAgent, LoopAgent, RunConfig  # the three orchestrators warn: deprecated in favor of Workflow
from google.adk import Agent, Context, Event, Runner, Workflow  # google.adk.__all__ in 2.15
from google.adk.workflow import FunctionNode, RetryConfig, node
from google.adk.tools import McpToolset                        # needs the google-adk[mcp] extra

# ❌ Fails in 2.15 (ModuleNotFoundError / ImportError)
from google.adk.tools.google_search import google_search        # module is google_search_tool
from google.adk.tools.built_in_code_execution import built_in_code_execution
from google.adk import InMemoryRunner                            # google.adk exports Agent, Context, Event, Runner, Workflow
from google.adk import App                                       # App lives in google.adk.apps
```

**Rule:** before adding an import, run `uv run python -c "from <module> import <name>"` against the locked version. Pin ADK exactly so the check stays true.

---

## GOOGLE_CLOUD_LOCATION Debugging

On Vertex, a model 404 is usually a location or project issue — check those first, then whether that model id is offered on Vertex in that region (an id that works on the developer API may not).

### Debug Sequence

1. **Check GOOGLE_CLOUD_LOCATION env var** — must be set to a region that supports the model
   - Verify region supports the model in Google's documentation before assuming

2. **Check GOOGLE_CLOUD_PROJECT env var** — must be set to a valid GCP project ID

3. **Only then check model name** — but rarely the issue if steps 1–2 are correct

### Example Error & Recovery

```
Error: 404 Model 'projects/my-project/locations/<region>/models/<model-id>' not found

↓ Fix: set GOOGLE_CLOUD_LOCATION (deploy config, not code) to a region the models page lists for
<model-id>, or a global endpoint if your model supports it; re-run the one-call probe
```

**Remember:** check location and project first, then model availability on that endpoint.

---

## Code Preservation Principle

Once an agent is working, protect it from accidental breakage.

### Never Do This Without Explicit Approval

- Change the model in existing agent code
- Rewrite working agent code (refactor incrementally instead)
- Remove tools from an agent
- Rename `output_key` values (downstream agents reference them by name)
- Modify tool signatures without updating all callers

### Safe Refactoring
- Extract duplicated logic into helper functions
- Rename variables for clarity
- Update comments and docstrings
- Add new tools without removing old ones
- Adjust agent instructions (careful — may change behavior)

---

## Breaking Infinite Loops

If the same error occurs 3+ times in a row: **STOP immediately**. Do not retry the same approach.

### Common ADK Infinite Loops

- Tool returns error → model retries same tool → same error (repeat forever)
- State validation fails → agent resets state → validation fails again
- Rate limit hit → agent retries immediately → rate limit hit again
- `LoopAgent` without `max_iterations` (default `None`) or a run without `max_llm_calls` (default 500)

### How to Break the Loop

1. **Cap the run** — `RunConfig(max_llm_calls=N)` raises `LlmCallsLimitExceededError` instead of looping
2. **Return typed tool errors** (`{"ok": False, "error_code": ...}`); convert exceptions with `on_tool_error_callback`; say in the instruction which codes are final (do not retry)
3. **Add state guards** to detect invalid state before calling tools
4. **Configure model retries once** in the client (`HttpRetryOptions`, `gemini-api-dev` skill) — not in the agent loop

### Escalation Protocol

After 3 identical failures:
```
STOPPED after 3 identical failures:
- Attempt 1: [what you tried, what failed]
- Attempt 2: [what you tried, what failed]
- Attempt 3: [what you tried, what failed]

Options:
A) Different approach: [describe]
B) Escalate to human — need more context
```

---

## Project-Specific Constraints

> Replace this section with your project's ADK constraints.
> Document: ADK version pin, model name(s), tool placement rules (R1/R2), eval thresholds,
> session backend choices, and any compliance requirements.

Example table:

| Constraint | Value | Notes |
|-----------|-------|-------|
| ADK version | `google-adk==X.Y.Z` exactly | Pin to specific version |
| Model | `settings.agent_model` (env `AGENT_MODEL`) | No literal id in code; bump = probe + evals + gradual rollout |
| Runner (dev) | `InMemoryRunner` + scripted fake model in tests | Never use real API in unit tests |
| Runner (prod) | `Runner`, built once per process | `DatabaseSessionService` (Postgres/Cloud SQL) or `VertexAiSessionService(project=, location=, agent_engine_id=)` (Agent Engine) |
| Every tool must have | `# Fallback:` comment | Defines degradation mode |
| Eval gates | Accuracy thresholds block merge | Define per-agent thresholds |

---

## Stale Skills Detection

Run periodically to detect outdated skill files:

```bash
# Check if skills are outdated (>90 days)
npx skills check -g

# Update all skills to latest version
npx skills update -g

# Update specific skill
npx skills update adk-dev-guide -g
```

If a skill's `last-reviewed` date is >90 days old, flag it for review before using.

---

## Testing Without Burning API Credits

When you need to validate system behavior, measure performance, or run CI without real LLM calls:

### Deterministic Shadow Agent

Create a variant of your ADK agent whose `before_model_callback` returns a deterministic `LlmResponse`, so the model is never called. Same tools, output schema and session state. Do **not** subclass `BaseAgent` and override `_run_async_impl`: in ADK 2.x `BaseAgent` is a workflow node and that override is bypassed.

```python
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types


def autopilot_decision(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    energy = float(callback_context.state.get("energy", 1.0))
    decision = "slow" if energy < 0.3 else "steady"
    return LlmResponse(content=types.ModelContent(parts=[types.Part(text=decision)]))  # skips the model


def build_runner_agent(settings: Settings) -> Agent:
    return Agent(
        name="runner",
        model=settings.agent_model,
        instruction="Decide the pace from the energy level.",
        output_key="decision",
        before_model_callback=autopilot_decision if settings.runner_mode == "autopilot" else None,
    )
```

Executed on `google-adk==2.15.0` with no credentials: `state={"energy": 0.1}` produced `decision == "slow"` and no model call. `runner_mode` comes from settings, not an ad-hoc `os.getenv` at the call site.

Use the autopilot variant when you need whole-system runs without a model (load tests, demos). For unit tests of a real `LlmAgent`, prefer the scripted fake model (`google-adk/reference/adk-testing.md` §2): it exercises your actual instructions and the model-facing path, which the callback skips.

### NDJSON Replay for Integration Tests and Demos

Record every event your ADK agent emits to a `.ndjson` file during a real run. Replay against the frontend or test harness without running agents:

```python
# Record in agent's broadcast/after_agent layer
with open("recordings/sim-run.ndjson", "a") as f:
    f.write(json.dumps({"ts": elapsed, "event": event.model_dump()}) + "\n")
```

Commit the recording — it becomes a regression baseline. CI replays it; no agents need to be running. Raw events contain user text, tool arguments and model output: record only from synthetic or consented sessions, redact before committing, and never record production traffic into the repo.

**When to use either pattern:** CI integration tests, load testing (run 1000s of autopilot agents cheaply), keynote demos, UI development iterations.

> Full implementation detail for both patterns: `agentic-agent-variant-ladder.md` in `agentic-ai-dev/reference/`

## Reference Files

- **`adk-dev-lifecycle.md`** — Full detail on each phase, commands, common pitfalls
- **`google-adk/SKILL.md`** — Agent patterns, tool API reference, ToolContext usage
- **`adk-eval-guide` skill** — Evaluation strategy and eval dataset structure
- **`adk-deploy-guide` skill** — Deployment to Cloud Run / Agent Engine, health checks, rollback
- **`agentic-ai-dev/reference/agentic-agent-variant-ladder.md`** — Agent variant ladder, deterministic shadow agents, NDJSON replay

---

## Quick Reference: When to Load This Skill

Load **adk-dev-guide BEFORE google-adk** when:
- Starting a new ADK agent feature
- Debugging an infinite loop or eval failure
- Onboarding a new developer to ADK patterns
- Reviewing an ADK agent's lifecycle

Load **google-adk only** when:
- Writing agent code (patterns, APIs, ToolContext)
- Implementing a specific tool
- Tweaking agent instructions

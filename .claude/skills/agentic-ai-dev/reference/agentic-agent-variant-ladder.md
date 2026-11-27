# Agent Variant Ladder, Deterministic Shadow Agents, and NDJSON Replay

Patterns sourced from the `race-condition` reference architecture (Google Cloud Next '26 keynote).
Use when designing multi-agent systems that need testability, cost control, or staged capability rollout.

---

## Pattern 1 — Agent Variant Ladder (Separate Agents per Capability Tier)

### Rule

**NEVER use feature flags inside a single agent to toggle capabilities — create separate agent files per capability tier.**

### What This Means

Instead of one agent with `if use_memory:` / `if enable_eval:` / `if use_llm:` branches:

```
agents/
  planner/          ← base agent (route planning, no frills)
  planner_with_eval/    ← adds LLM-as-Judge eval gating
  planner_with_memory/  ← adds AlloyDB persistent memory
```

Each variant:
- Has its own entry point (`agent.py`) and A2A card (`agent.json`)
- Can be deployed, scaled, and removed independently
- Shows what the added capability costs by **diffing two `agent.py` files**
- The higher-tier variant calls `get_base_agent()` from the tier below and adds one override

### Implementation Pattern

```python
from google.adk import Workflow
from google.adk.agents import LlmAgent

# planner/agent.py — base tier
def get_agent():
    return LlmAgent(
        name="planner",
        model=MODEL,
        instruction=PLANNER_INSTRUCTIONS,
        tools=[get_route_candidates, score_route, estimate_cost],
    )

# planner_with_eval/agent.py — adds eval gating
from agents.planner.agent import get_agent as get_base_agent

def get_agent():
    base = get_base_agent()
    return Workflow(
        name="planner_with_eval",
        edges=[("START", base, LlmAgent(name="eval_judge", instruction=EVAL_JUDGE_INSTRUCTIONS, ...))],
    )  # SequentialAgent is deprecated in google-adk 2.x (adk-agent-types.md)

# planner_with_memory/agent.py — adds AlloyDB persistence
from agents.planner_with_eval.agent import get_agent as get_base_agent

def get_agent() -> Agent:
    base = get_base_agent()
    base.before_agent_callback = load_route_memory
    base.after_agent_callback = persist_route_memory
    return base
```

### When to Use This Pattern

- You want to evaluate cost/complexity of each capability in isolation
- Different deployment environments need different capability tiers (dev = base, staging = +eval, prod = +memory)
- You need to A/B test capability tiers independently
- You want independent scaling per tier (memory agent needs AlloyDB; base agent doesn't)

### Anti-Pattern to Avoid

```python
# ❌ Feature flags inside one agent — diff is impossible, tiers cannot be deployed independently
def get_agent(use_memory=False, use_eval=False) -> Agent:
    tools = [get_route_candidates, score_route]
    if use_eval:
        tools.append(eval_judge_tool)
    if use_memory:
        tools.append(memory_tool)
    return LlmAgent(...)
```

---

## Pattern 2 — Deterministic Shadow Agent

### Rule

**Every LLM-powered agent that is loop-critical (called per tick, per event, or per user turn) MUST have a deterministic shadow variant that makes zero API calls.**

### What This Is

A shadow agent that:
- Makes the **same shape of decisions** as the LLM-powered variant
- Uses deterministic logic (rules, heuristics, fixed thresholds) instead of LLM calls
- Produces outputs in **exactly the same format** as the LLM variant
- Can substitute for the LLM variant with a single config switch

### Why This Matters

| Use Case | Benefit |
|---|---|
| **Load testing** | Run 1000 concurrent simulated users without burning LLM budget |
| **CI/CD testing** | Integration tests that run in <1s instead of 10s with no API cost |
| **Demo mode** | Reliable behavior for keynotes, demos, and stakeholder reviews |
| **Baseline measurement** | Measure system performance (latency, throughput) without LLM variance |
| **Cost estimation** | Validate system architecture before committing to LLM spend |

### Implementation Pattern

```python
# runner/agent.py — LLM-powered variant
class RunnerAgent:
    def decide_pace(self, state: RunnerState) -> Decision:
        response = self.llm.generate(
            prompt=build_decision_prompt(state),
            response_schema=Decision,
        )
        return response

# runner_autopilot/agent.py — deterministic shadow
# Key: imports from LLM variant but overrides ONLY the decision callback
from agents.runner.agent import RunnerAgent, RunnerState, Decision

class AutopilotRunnerAgent(RunnerAgent):
    def decide_pace(self, state: RunnerState) -> Decision:
        # Zero LLM calls — deterministic heuristic
        if state.energy < 0.3:
            return Decision(pace="slow", hydrate=True)
        if state.position_rank <= 3 and state.lap > 20:
            return Decision(pace="fast", hydrate=False)
        return Decision(pace="steady", hydrate=state.distance_since_hydration > 5)
```

### Structural Requirements

1. Shadow agent **inherits from** or **wraps** the LLM variant — shares all non-decision code
2. Only the LLM call is replaced — I/O format, state schema, tool contracts are identical
3. Output schema is validated against the same Pydantic model as the LLM variant
4. Switched via env var or config — not a separate code path at the call site:

```python
# ❌ Wrong — caller decides which variant to use
if settings.use_autopilot:
    agent = AutopilotRunnerAgent()
else:
    agent = RunnerAgent()

# ✅ Right — factory function encapsulates the choice
def get_runner_agent() -> RunnerAgent:
    if settings.runner_mode == "autopilot":
        return AutopilotRunnerAgent()
    return RunnerAgent()
```

---

## Pattern 3 — NDJSON Replay for Demo Reliability and UI Testing

### Rule

**Record real agent run outputs as NDJSON streams. Replay them for demos, UI testing, and CI — indistinguishable from a live run.**

### What This Is

A recording of every event emitted by a live agent run, stored as newline-delimited JSON. The replay system reads the file and re-emits events at timing-faithful intervals, feeding them to the frontend exactly as a live run would.

### File Format

One JSON object per line. Each line is a complete event:

```jsonl
{"ts": 1716000000.001, "type": "runner_update", "runner_id": "r1", "position": [36.17, -115.13], "pace": "steady"}
{"ts": 1716000000.120, "type": "weather_update", "condition": "sunny", "temp_c": 28}
{"ts": 1716000000.340, "type": "runner_update", "runner_id": "r2", "position": [36.16, -115.14], "pace": "fast"}
```

### Why NDJSON Over Other Formats

- **Streamable** — can start replaying before the file is fully loaded
- **Appendable** — recording just appends lines, no JSON structure to maintain
- **Parseable line by line** — no need to hold the full run in memory
- **Human-readable** — diff, grep, or truncate any recording for test subsets

### Recorder Implementation

```python
class NdjsonRecorder:
    def __init__(self, path: Path):
        self._file = path.open("a")
        self._t0 = time.monotonic()

    def record(self, event: dict) -> None:
        event["ts"] = time.monotonic() - self._t0
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()
```

### Replay Service (Frontend / Test)

```typescript
// TypeScript — replay with timing fidelity
async function beginNdjsonReplay(
  path: string,
  onEvent: (event: SimEvent) => void,
  timeScale = 1.0
): Promise<void> {
  const lines = (await fetch(path).then(r => r.text())).split('\n').filter(Boolean);
  const events = lines.map(l => JSON.parse(l) as NdjsonEvent);
  let lastTs = 0;
  for (const event of events) {
    const delay = ((event.ts - lastTs) / timeScale) * 1000;
    if (delay > 0) await sleep(delay);
    onEvent(event);
    lastTs = event.ts;
  }
}
```

### Use Cases

| Scenario | How to Use |
|---|---|
| **Demo / keynote** | Point frontend at `.ndjson` file; no agents running, no API cost, no network blip risk |
| **UI development** | Run frontend against recording — iterate on rendering without spinning up agents |
| **Integration test** | Replay a known-good recording and assert UI state at key timestamps |
| **Regression test** | Re-record after agent changes; diff `.ndjson` files to detect behavior changes |
| **Load test baseline** | Replay at `timeScale: 100` to stress-test the frontend event loop |

### Project Integration

1. Add recorder to the simulator's broadcast path (writes alongside live emit)
2. Store recordings in `assets/sim-<scenario>-log.ndjson` (committed to repo for CI)
3. Frontend boots with `REPLAY_MODE=true` env var pointing at a recording path
4. `timeScale` in demo config controls playback speed (1.0 = real time, 0.5 = half speed)
5. CI integration test: replay the committed recording, assert no errors, assert final state

### What to Record

Record at the **gateway/broadcast layer**, not at the agent layer:
- All messages the frontend would receive in a live run
- Include timestamps relative to run start (not wall clock)
- Do NOT record internal agent state — only the published events

This ensures the recording is an exact replay of what the frontend would see.

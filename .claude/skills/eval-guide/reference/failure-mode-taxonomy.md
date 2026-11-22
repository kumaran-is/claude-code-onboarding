# Agent Failure Mode Taxonomy

> Use this when an agent is underperforming. Classify the failure type first,
> then route to the right eval tool. Skipping classification wastes eval cycles.

## The 6 Failure Modes

| Mode | Description | Signal |
|------|-------------|--------|
| **Instruction misunderstanding** | Agent misreads its own role or task scope | Consistently wrong tool selected; response addresses different task than asked |
| **Output format error** | Response structure doesn't match `output_schema` | JSON parse failures; missing required fields; wrong enum values |
| **Context loss** | Multi-turn conversation degrades mid-session | Correct early turns, wrong late turns; agent forgets constraints stated 3+ turns back |
| **Tool misuse** | Wrong tool called, wrong order, or unnecessary calls | High tool call count with low `ToolCallAccuracy`; calling MCP tools when FunctionTools suffice |
| **Constraint violation** | Business rule or tenant isolation breach | Any CI BLOCKER firing; required review flag not set on restricted input |
| **Edge case collapse** | Unusual input causes silent wrong output or exception | Low confidence scores on outlier inputs; a critical-path case misclassified |

---

## Failure → Eval Tool Routing

### Instruction Misunderstanding

**Root cause:** System prompt is ambiguous, underspecified, or conflicting with few-shot examples.

**How to diagnose:**
Replay the failing cases with tracing on and inspect which instruction branch fired; run the flow's golden set (`adk eval` or your runner) on diverse cases.

**Eval tools:**
- **Arize Phoenix** → inspect `llm.instruction` span attribute to see which prompt branch the model took
- **ADK eval** (`adk eval`) → `FinalResponseMatchV2` on the flow's held-out golden set
- **Giskard** → `Scenario` with adversarial instruction variants; catches systematic misreading

**Fix pattern:** Rewrite the instruction's ambiguous clause in your PromptRegistry → re-seed prompts locally → re-run the held-out set (not only the failing case).

---

### Output Format Error

**Root cause:** `output_schema` Pydantic model doesn't match what the prompt instructs the model to produce, OR the model ignores the schema under certain inputs.

**How to diagnose:**
Run the R1 schema cases (`uv run pytest -m r1 -k format`).

**Eval tools:**
- **pytest (deterministic, preferred)** → schema validity is a parse, not a judgment: validate with the Pydantic model; an LLM `GEval` for JSON validity is weaker and costs a judge call
- **ADK eval** → output schema validation is built-in; any `output_schema` mismatch surfaces as a failed case
- **pytest** → add a `@pytest.mark.r1` test that asserts `OutputModel.model_validate_json(response.content)` for every agent with a Pydantic `output_schema`

**Fix pattern:** Add 2-3 few-shot examples in the system prompt showing the exact JSON structure → re-eval.

---

### Context Loss

**Root cause:** Long conversation history pushes early constraints out of the model's effective attention window.

**How to diagnose:**
Run the multi-turn set (ADK user simulation or your simulator; see `../SKILL.md` Multi-turn).

**Eval tools:**
- **ADK User Simulation** (`InMemoryRunner` + `run_async` with multi-turn `Content` list) → tests specifically whether the agent degrades across turns
- **Arize Phoenix** → inspect token count per turn; spikes near the end of a long session signal attention pressure
- **DeepEval** `ConversationalGEval` → scores contextual consistency across turn N vs turn N-5

**Fix pattern:** Add a `# Context anchor:` block at the start of the agent's instruction that restates the 2-3 invariants that must survive the full session. ADK `DatabaseSessionService` keeps state server-side — verify it's in use (never `InMemorySessionService` in production).

---

### Tool Misuse

**Root cause:** System prompt doesn't specify when to use each tool, or tool descriptions overlap and confuse the model.

**How to diagnose:**
Run the tool-call metrics (deterministic `ToolCallAccuracy` / `ToolCorrectnessMetric`) and the MCP contract suite (`mcp-eval-patterns.md`).

**Eval tools:**
- **DeepEval** `MCPUseMetric` → checks tool name, input correctness, and call ordering
- **Ragas** `ToolCallAccuracy(strict_order=True)` → strict ordering required for agents with sequential tool dependencies (per `per-agent-thresholds.md`)
- **Promptfoo** → log actual tool call sequences in `vars:` and assert with `toolCalls` assertion

**Fix pattern:** Add a `## When to use each tool` section to the agent's PromptRegistry instruction. Each tool gets one sentence describing preconditions. Re-eval `MCPUseMetric` immediately after prompt change.

---

### Constraint Violation

**Root cause:** Business rules (regulated-policy constraints, tenant isolation, audit-record requirement) not enforced in tool pre-conditions.

**How to diagnose:**
```bash
uv run pytest tests/golden/security/ -m r1        # hard CI blockers (ci-tiers.md)
npx promptfoo redteam run -c <redteam-config>     # verify command and plugins via Context7 (promptfoo)
```

**Eval tools:**
- **Promptfoo** red-team → policy plugin with your regulated-policy ruleset; PII and harmful-content plugins (verify plugin ids via Context7)
- **Giskard** → `Scenario` with policy-bypass and injection prompts
- **pytest golden/security/** → mandatory for every hard CI blocker; must pass before any agent PR merges
- **MCP eval** → cross-tenant input ID test catches tenant isolation violations at the MCP layer

**Fix pattern:** Enforce the constraint in deterministic code at the tool pre-condition (not the prompt). Prompt-level rules are a probabilistic signal, never authorization. If the required safety class has no category in your deterministic taxonomy, that is a PRODUCT gap: leave the case red and report the missing type; never add a pattern that matches only the one failing utterance.

---

### Edge Case Collapse

**Root cause:** Training distribution doesn't include the unusual input; the model falls back to a plausible-but-wrong answer with high confidence.

**How to diagnose:**
Run the critical-case file for the flow on its own (100% gate).

**Eval tools:**
- **ADK eval** → separate critical-case evalset gated at 1.0 (see `per-agent-thresholds.md` critical-path sub-threshold)
- **DeepEval** `ArenaGEval` → A/B compare old vs new prompt on the failing edge cases; isolates whether prompt or model is at fault
- **Ragas** `AgentGoalAccuracyWithReference` → catches cases where tool calls look right but the final answer is wrong for an unusual input

**Fix pattern:** Add the failing case to the held-out set (or `regression/`) immediately — this is the golden dataset growth mechanism. Then fix the input class with a general change; any few-shot example you add must be a different, general example, never the golden case or its phrasing (`golden-dataset.md` leakage rules).

---

## Quick Routing Table

| Symptom observed | Failure mode | First tool to run |
|---|---|---|
| Wrong tool called | Tool misuse | deterministic tool-call assertions, then `MCPUseMetric` |
| JSON parse error in response | Output format | Pydantic schema validation in R1 |
| Works in turn 1, wrong in turn 5+ | Context loss | multi-turn set |
| Restricted request not flagged | Constraint violation | security golden set + red-team run |
| Correct tool, wrong final answer | Instruction misunderstanding | trace replay of the failing cases |
| Confident wrong answer on unusual input | Edge case collapse | critical-case file |
| Critical case misclassified | Edge case collapse (CRITICAL) | CI BLOCKER — fix before any merge |

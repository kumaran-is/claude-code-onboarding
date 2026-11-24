# Agentic AI Code Review Checklist

Used by the `agentic-ai-reviewer` agent. Framework-neutral items first; LangChain/LangGraph specifics marked **[LG]**. Google ADK services use the same core items with `adk-reviewer` for ADK specifics.

## Severity

| Level | Criteria | Verdict effect |
|-------|----------|----------------|
| CRITICAL | Cross-tenant/user data exposure, model-controlled scope or authorization, unbounded loop/spend, side effect without approval or idempotency, secrets/PII leak | BLOCK |
| HIGH | Missing deadline/step cap mapping, exception text to clients/streams/model, broken HITL resume, non-transient failover, missing tests for a new graph/tool | BLOCK |
| MEDIUM | Suboptimal pattern, missing metric/trace attribute, weak but present validation | NEEDS_REVIEW |
| LOW | Style, naming, docs | Comment only |

## Review Areas

### 1. Authority and scope (CRITICAL)
- Routing targets, scope ids, approvals and state transitions are computed by code; a model-proposed route is validated against a closed enum before `Command(goto=...)`
- Tenant/org/user scope is injected into tools from verified context (**[LG]** `ToolRuntime[Ctx]` / `InjectedToolArg`); scope params are absent from the model-visible schema; missing scope = deny
- `user_id`/`org_id`/`thread_id`/`session_id` are never trusted from body or query; thread keys are principal-scoped or ownership-checked
- Tool allowlist is non-empty and every name resolves (test present); server-side authorization still runs on every backend call
- Memory recall/write is principal-namespaced and fails closed (`agentic-memory-systems.md`)
- Answer caches keyed by org + ACL scope + model + prompt version; no cross-user sharing of generated answers

### 2. Execution control (CRITICAL/HIGH)
- **[LG]** Explicit `recursion_limit` from settings (default is 10007 in langgraph 1.2.x, 10000 in 1.0.x); `GraphRecursionError` caught and mapped to a typed status
- **[LG]** `ModelCallLimitMiddleware`/`ToolCallLimitMiddleware` use `exit_behavior="error"` (the default `"end"` returns a library string as the answer)
- Every run is inside `asyncio.timeout(settings.…)`; `TimeoutError` mapped to a typed status
- Budgets are cumulative across router, sub-agents, retries and fallback models
- A cap never returns the last message (possibly an unanswered tool call) as success

### 3. Tools and side effects (CRITICAL/HIGH)
- Tools return a typed JSON-serializable result with an explicit error field (`ok`/`error_code`/`data`), not exception strings; read results are projected through an allowlist of fields
- Deterministic evidence gate after the run: all grounding tools failed/empty → `INSUFFICIENT_EVIDENCE` regardless of model text
- Side-effecting tools take an idempotency key bound to a payload hash; high-consequence writes go through a propose → approve → execute flow
- HITL uses `interrupt()`/`HumanInTheLoopMiddleware` + `Command(resume=<typed decision>)` with a durable checkpointer and an approval record; no substring matching, no in-process events, no new-message "resume"
- Code before `interrupt()` has no side effects (the node re-runs on resume)
- No stub tools returning synthetic data; each tool documents its degradation mode

### 4. Errors, retries, failover (HIGH)
- No `str(e)`/`exc_info=True`/user text in logs; Phase 2 `log_exception` used
- No exception text in HTTP `detail`, SSE `data:` or `AIMessage` content
- One retry layer, transient error classes only; **[LG]** `ModelRetryMiddleware(on_failure="error", retry_on=<transient>)`
- Failover only on availability errors to an approved same-tier model; never on refusal/400/schema; `with_fallbacks(exceptions_to_handle=…)` set
- Agent-run retries only when all tools are read-only/idempotent, on a fresh thread, never after the first streamed byte

### 5. Streaming (HIGH)
- Every SSE `data:` is JSON; typed events; exactly one terminal event
- Only user-facing node text is streamed; no tool args/outputs, router or grader tokens
- Scoping/safety decisions made before returning `StreamingResponse`; `CancelledError` not swallowed

### 6. Input/output safety (HIGH)
- Untrusted text (user, retrieved, tool output, memory, OCR) goes in user/tool content, never interpolated into system instructions
- Injection classifiers/regex are signals (log, raise risk), not the security boundary
- Output validated against a schema before use; validation failure has a defined path (bounded retry → typed fallback)

### 7. Inference configuration (MEDIUM/HIGH)
- Model ids from settings only; no literal in code or test assertions
- Sampling/reasoning params follow provider guidance for that model; output-token limit covers reasoning tokens; empty answer on a length finish is treated as a defect
- Pins: `langgraph` and `langgraph-prebuilt` (and checkpoint packages) pinned together with `==`; lockfile committed

### 8. Testing (HIGH for new graphs/tools)
- Scripted fake model tests for routing, tool sequence/args, caps, error mapping, idempotency, HITL approve/reject
- Cross-principal isolation test (threads, memory, caches)
- Live golden + failure-matrix replay before release (`agentic-testing.md`)

### 9. Observability and cost (MEDIUM)
- Traces carry agent, model, tool and prompt version; no PII in trace metadata
- Token/cost metrics with bounded labels (provider, model, feature) — never user/org ids as metric labels
- Retry, failover, cap-hit and fallback counters

## Output Format

For each finding:

```
### [SEVERITY] {area}: {short description}
**Evidence:** `{file_path}:{line}` — `{quoted code}`
**Impact:** {what breaks, for whom}
**Fix:** {specific change}
```

Do not claim a test, eval or runtime check passed unless you executed it in this session and show the command and its output; otherwise mark it NOT RUN.

## Summary Template

```
## Review Summary
Files reviewed: {count}
Checks executed: {commands + exit codes, or NOT RUN}
VERDICT: {APPROVE|NEEDS_REVIEW|BLOCK} — CRITICAL: N | HIGH: N | MEDIUM: N | LOW: N
```

## Reference

Expected patterns: `agentic-templates-core.md`, `agentic-streaming-hitl.md`, `agentic-templates-resilience.md`, `agentic-error-handling.md`, `tool-execution-safety.md`, `llm-inference-and-model-routing.md`, `agentic-memory-systems.md`, `agentic-caching-patterns.md`, `agentic-guardrails-security.md`, `agentic-testing.md`, `agentic-ai-coding-standard/reference/agentic-standards-examples.md`.

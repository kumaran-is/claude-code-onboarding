# Tool Execution Safety

Canonical home for how agents call tools safely: contracts, server-injected scope, allowlists, result verification, side-effect idempotency, budgets, approval gates, compensation and durable resume. Framework-neutral core first; LangChain v1 / LangGraph specifics marked **[LG]**; Google ADK equivalents live in `google-adk/reference/adk-tools-callbacks.md` and link here. Principles (autonomy ladder, least privilege) are in `ai-playbook/playbook.md` §2.5–2.6. MCP server implementation is out of scope.

Validation: every Python block below was executed on Python 3.14 with langchain 1.2.8 / langgraph 1.0.7 and PostgreSQL 16 (`ToolRuntime` scope injection and schema hiding re-run on langchain 1.5.2) (`ruff` + `mypy --strict` clean; tests listed in §11), using scripted fake models. No live model was called.

**Model proposes, code authorizes.** Tool *visibility* (what the model sees), *caller permission* (what this agent may call) and *resource authorization* (which record the backend lets this principal touch) are three independent layers; none substitutes for another. LLM-based checks are probabilistic signals, never authorization.

## 1. Tool contract

| Element | Rule |
|---|---|
| Name + docstring | Verb-noun name; the docstring says when to use it and what it returns (the model reads it) |
| Arguments | Typed, minimal, validated; **no scope parameters** in the model-visible schema |
| Result | `ToolResult` = `{ok, error_code, data}`; JSON-serializable; read results projected through a field allowlist |
| Authority tier | One of the tiers in §2, recorded next to the tool |
| Degradation mode | One line: what the agent does when this tool is unavailable (`# Fallback: answer INSUFFICIENT_EVIDENCE`) |
| Timeout | Per-call timeout inside the run deadline |
| Schema version | Explicit `major.minor` on the tool contract (guardrails G3). Boundary order: tool exists → version supported (same major, minor ≤ pinned) → payload valid → authorized; failures return `SCHEMA_VERSION_MISMATCH` / `SCHEMA_VALIDATION_FAILED` and nothing executes. Minor = additive only; enum changes and new required fields need compatibility review |
| Real backend | No stub tools returning synthetic, hash-derived or random data in shipped code: remove the tool instead |

```python
ErrorCode = Literal["NOT_FOUND", "UNAUTHORIZED", "TOOL_UNAVAILABLE", "INPUT_REJECTED",
                    "IDEMPOTENCY_PAYLOAD_MISMATCH"]


class ToolResult(TypedDict):
    ok: bool
    error_code: ErrorCode | None
    data: dict[str, Any] | None


def ok(data: dict[str, Any]) -> ToolResult:
    return {"ok": True, "error_code": None, "data": data}


def fail(code: ErrorCode) -> ToolResult:
    return {"ok": False, "error_code": code, "data": None}


def project(raw: Mapping[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    """Return only allow-listed fields of a backend record to the model."""
    return {k: raw[k] for k in allowed if k in raw}
```

Replaces the older rules "tools return `str`" and "return error strings": an error string is free text the model may ignore, paraphrase as fact, or echo with internal details.

## 2. Authority tiers

| Tier | Examples | Gate |
|---|---|---|
| Read | search, get record | Scope injected; result projected |
| Advisory compute | estimate, classify, draft score | Output is a proposal, never a state change |
| Draft | create a draft reply/document | Visible as draft; a human or workflow publishes |
| Controlled write | update a preference, add a note | Idempotency key; authorization check in the service |
| High-consequence write | refund, delete, send external message, change permissions | **Propose tool** + approval (§7) + idempotency; executed by the authorized workflow |
| Prohibited autonomous | anything legally or contractually requiring a human | Not exposed as a tool |

Adding a write tool re-classifies the agent (and triggers security review); a low-authority agent never gains authority silently.

Propose-tool shape for high-consequence actions: return `{candidate_action, args, missing_evidence, required_authority, side_effects}`; it changes nothing. The approved workflow (or the HITL resume) executes.

## 3. Scope injection (never model-supplied)

Tenant/org/user scope comes from the verified request principal. Remove it from the model-visible schema and inject it at call time; if it is missing, deny. Without this the model invents placeholder ids or picks another tenant's id from context.

**[LG]** `ToolRuntime[Ctx]` — the model sees only `order_id`; the route passes `context=RequestCtx(...)` (see `agentic-templates-core.md`):

```python
@dataclass(frozen=True)
class RequestCtx:
    org_id: str
    user_id: str


@tool
def lookup_order(order_id: str, runtime: ToolRuntime[RequestCtx]) -> ToolResult:
    """Look up one order visible to the caller."""
    record = orders.get(org_id=runtime.context.org_id, order_id=order_id)   # service re-authorizes
    return ok(project(record, ORDER_FIELDS)) if record else fail("NOT_FOUND")


agent = create_agent(model, tools=[lookup_order], context_schema=RequestCtx, checkpointer=saver)
await agent.ainvoke(inputs, config, context=RequestCtx(org_id=p.org_id, user_id=p.user_id))
```

Executed: `convert_to_openai_tool(lookup_order)` exposes only `order_id`; through the FastAPI route the tool received the principal's `org_id`. `Annotated[str, InjectedToolArg]` also hides a parameter, but then *your* code must supply it on every call path; prefer `ToolRuntime`.

Framework-neutral dispatcher (custom loops, MCP gateways, other SDKs): overwrite, never trust.

```python
SCOPE_KEYS = frozenset({"org_id", "tenant_id", "account_id", "user_id"})


def bind_scope(model_args: Mapping[str, Any], *, org_id: str, user_id: str) -> dict[str, Any]:
    """Drop any scope value the model sent and inject the verified one; fail closed."""
    if not (org_id and user_id):
        raise PermissionError("tool call without verified scope")
    clean = {k: v for k, v in model_args.items() if k not in SCOPE_KEYS}
    return {**clean, "org_id": org_id, "user_id": user_id}
```

Executed: a model-sent `org_id="account-1"` was replaced by the session value; an empty scope raised. Test this per tool: a forged scope argument must be ignored.

## 4. Allowlists

```python
def resolve_allowlist(registry: Mapping[str, Any], allowed_names: Iterable[str]) -> list[Any]:
    """Unknown names must fail loudly: silent filtering can leave an agent with zero tools."""
    names = list(allowed_names)
    if not names:
        raise ValueError("tool allowlist is empty")
    unknown = sorted(set(names) - set(registry))
    if unknown:
        raise ValueError(f"unknown tools in allowlist: {unknown}")
    return [registry[n] for n in names]
```

- Each agent gets an explicit, non-empty allowlist; construction fails on an unknown name (executed: `[]` and a misspelled name both raise).
- The tool server/gateway enforces the same allowlist per caller principal (defense in depth).
- A CI check that validates allowlists must resolve names through the code (import the registry or walk the AST for constants), not regex over string literals: a regex check can report "0 unknown names" while seeing only some agents.
- Deterministic code calls services directly, not through the model's tool gateway.

## 5. Tool results are untrusted data

- Tool output (and retrieved text, fetched pages, OCR) can carry instructions. It goes back as a tool message, never into system instructions; unknown fields are dropped by projection.
- Never stream raw tool arguments or outputs to end users (`agentic-streaming-hitl.md`).
- **Deterministic evidence gate** after the run, in the route:

```python
def evidence_status(grounding_results: list[ToolResult]) -> Literal["OK", "INSUFFICIENT_EVIDENCE"]:
    """Run after the agent, in code: model text cannot override it."""
    if not any(r["ok"] and r["data"] for r in grounding_results):
        return "INSUFFICIENT_EVIDENCE"
    return "OK"
```

If every grounding tool errored or returned nothing, the response is `INSUFFICIENT_EVIDENCE` regardless of how confident the model's text is. Collect `grounding_results` from the `ToolMessage`s of the run (parse their JSON content) or from a state field the tools append to.

- Do not report a business outcome from a tool's HTTP 200 alone: verify the resulting state (read it back) before telling the user "done".

## 6. Side-effecting tools: idempotency bound to a payload hash

The model, the retry layer and a resumed checkpoint can all call a write tool twice. Bind each logical action to a key, and the key to the exact payload.

```python
DDL = """
CREATE TABLE IF NOT EXISTS tool_idempotency (
    org_id        text        NOT NULL,
    idem_key      text        NOT NULL,
    payload_hash  text        NOT NULL,
    result        jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, idem_key)
)"""


def payload_hash(action: str, args: Mapping[str, Any]) -> str:
    canonical = json.dumps({"action": action, "args": args}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def run_once(conn: psycopg.AsyncConnection[Any], *, org_id: str, idem_key: str, action: str,
                   args: Mapping[str, Any], effect: Callable[[], Awaitable[dict[str, Any]]]) -> ToolResult:
    h = payload_hash(action, args)
    async with conn.transaction():
        claimed = await conn.execute(
            "INSERT INTO tool_idempotency (org_id, idem_key, payload_hash) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING RETURNING 1", (org_id, idem_key, h))
        if await claimed.fetchone() is None:
            row = await (await conn.execute(
                "SELECT payload_hash, result FROM tool_idempotency WHERE org_id = %s AND idem_key = %s",
                (org_id, idem_key))).fetchone()
            if row is None:              # key released between the conflict and this read: transient
                return fail("TOOL_UNAVAILABLE")
            if row[0] != h:
                return fail("IDEMPOTENCY_PAYLOAD_MISMATCH")
            return ok(row[1])
        result = await effect()
        await conn.execute("UPDATE tool_idempotency SET result = %s WHERE org_id = %s AND idem_key = %s",
                           (Jsonb(result), org_id, idem_key))
    return ok(result)
```

Executed against PostgreSQL 16: same key + same payload returned the stored result without re-running the effect; same key + different amount returned `IDEMPOTENCY_PAYLOAD_MISMATCH`; the same key in another org ran independently; five concurrent callers with one key ran the effect exactly once.

- Key source: `sha256(org_id + action + client_request_id)` or a server-minted id stored in the run state before the call — never generated fresh inside the retried code.
- `effect()` above runs inside the DB transaction: fine for a local write. For an external call (payments, email), do not hold the transaction open across the network: pass the key to the provider's own idempotency mechanism and use the outbox pattern (`python-dev/reference/reliability-idempotency-retries-outbox.md` §1, §4, §6).
- Keep keys for the replay window (retries + resume + approval delay), then expire. An expired key never re-executes blindly: re-check canonical state (record version) first, and reject with a typed status if it changed.
- Guardrails G4 writes the key as `SHA256(org_id + entity_id + action_name + payload_hash)`. Persist that value for audit, but look duplicates up by the payload-independent scope (`org_id`, entity or channel, action, client request id) as in `run_once` above: a key that already contains the payload hash cannot detect "same request, changed payload", because the changed payload produces a new key. Executed in the guardrail contract suite (`ai-launch-check/assets/guardrail_contract_tests.py`).
- A human change to the same record invalidates pending AI intents (version/etag check before the write).

## 7. Approval gates

High-consequence tools run only after a typed approval resumed from a durable checkpoint: `HumanInTheLoopMiddleware` or `interrupt()` + `Command(resume=...)`, a persisted approval record with owner, required authority, due time and args hash, and an authenticated approver endpoint. Full pattern and executed tests: `agentic-streaming-hitl.md` §Human-in-the-Loop.

## 8. Budgets and recursion

Budgets are **cumulative per user request** across router, sub-agents, retries and fallback models: max model calls, max tool calls, tokens/cost, wall-clock. Exhaustion stops retries, keeps canonical state unchanged, and returns a typed status or routes to a human.

**[LG]**

```python
middleware = [
    ModelCallLimitMiddleware(run_limit=settings.max_model_calls, exit_behavior="error"),
    ToolCallLimitMiddleware(run_limit=settings.max_tool_calls, exit_behavior="error"),
    ToolCallLimitMiddleware(tool_name="send_message", run_limit=1, exit_behavior="error"),
]
config = {"configurable": {"thread_id": key}, "recursion_limit": settings.max_graph_steps}
```

Executed: with `exit_behavior="error"` a looping fake model raised `ModelCallLimitExceededError` after 3 calls; with the default `"end"` the run ended on an `AIMessage` reading "Model call limits exceeded: run limit (3/3)", which a naive route would show as the answer. LangGraph 1.2.x default `recursion_limit` is 10007 (1.0.x: 10000); set it and map `GraphRecursionError` (`agentic-templates-core.md`). Sub-agents receive the *remaining* budget, not a fresh one. Calibrate limits from measured p95/p99 of real runs; add per-org rate and concurrency caps at the gateway.

## 9. Compensation: agents do not own transactions

An agent loop must not be the only thing holding a multi-step business change together. The agent *requests*; a domain service or durable workflow *commits*, with compensations for each completed step (saga) — see `workflow-orchestration-patterns`. Budget exhaustion or a crash mid-run must never leave state half-mutated.

## 10. Durable resume

With a checkpointer, a crashed or interrupted run resumes from the last completed super-step, and the interrupted node **re-runs from its first line** (executed: a counter placed before `interrupt()` reached 2 after one resume). Therefore:
- Side effects live in their own node or tool, after the decision point, and are idempotency-keyed (§6).
- Never put a write before `interrupt()` in the same node.
- Do not retry a whole run that already executed a non-idempotent tool; resume it instead.

## 11. Tests (scripted fake model)

| Test | Asserts |
|---|---|
| Schema has no scope params | `convert_to_openai_tool(t)` parameter fields exclude `org_id`/`user_id` |
| Forged scope ignored | Model-sent `org_id` replaced by the context value; missing scope denies |
| Allowlist resolves | Empty or unknown names raise at construction |
| Evidence gate | All grounding failures → `INSUFFICIENT_EVIDENCE` even when the model's text is confident |
| Idempotency | Same key/same payload → one effect; same key/different payload → mismatch; concurrent callers → one effect |
| Caps | Looping model → `ModelCallLimitExceededError`/`GraphRecursionError` → typed status |
| HITL | Approve runs once; reject and stale args hash run nothing; resume works on a new process |
| Tool surface lock | Hash of model-visible schemas matches the committed lock file |

Tool surface lock (contract test; intentional changes update the lock in the same PR with owner review):

```python
def tool_surface(tools: Sequence[BaseTool]) -> dict[str, str]:
    """name -> sha256 of the provider-facing schema (injected params excluded)."""
    out: dict[str, str] = {}
    for t in sorted(tools, key=lambda t: t.name):
        schema = convert_to_openai_tool(t)
        out[t.name] = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()
    return out
```

Scripted-model setup for these tests: `agentic-testing.md` §Scripted model.

# Error Handling Patterns (agents)

Canonical error **policy** for agent services. Code templates: `agentic-templates-core.md` (route mapping), `agentic-templates-resilience.md` (retry/failover middleware), `tool-execution-safety.md` (tool results), `llm-inference-and-model-routing.md` (model-call errors, 429, deadlines). Logging uses the Phase 2 `log_exception(logger, event, exc, **non_pii_ids)` helper (`deployment-ci-cd/reference/python-observability.md` §2): never `str(e)`, `exc_info=True` or the user's text in logs.

## Rules

| # | Rule |
|---|---|
| 1 | Exception text never reaches the client, the stream, or the model's context. Clients get a typed `status` / opaque `error_code`; logs get the exception type + non-PII ids. |
| 2 | Graph nodes do not catch provider errors to append chat messages. Errors propagate to one retry/failover layer, then to the route boundary. |
| 3 | Tools return a typed result (`ok`, `error_code`, `data`); they do not return exception strings the model may ignore or repeat. |
| 4 | Caps raise: `GraphRecursionError`, `ModelCallLimitExceededError`, `ToolCallLimitExceededError`, `TimeoutError` are mapped to `ITERATION_LIMIT` / `TIMEOUT`. A cap never returns the last message as if it were an answer. |
| 5 | Retry only what is transient AND only when every tool on the path is read-only or idempotency-keyed. |
| 6 | Fail over only on availability errors, to an approved same-tier model that passes the same evals and schema. Never on refusal/safety, invalid request, auth, context overflow or schema errors. |
| 7 | Degraded results are explicit (flag in state, metric, trace attribute), never a silent `[]`/`None`. |

## Retry discipline for a whole agent run

```text
retry the run?   only if every tool on the path is read-only or idempotency-keyed
each retry       new thread/session id (do not replay the failed turn into context); max 1-2;
                 metric agent_retry_total{agent}
structured output malformed/empty -> one retry in a FRESH context, reset the parser state
never retry      safety/refusal/recitation finishes, max-token finishes, quota-exhausted 429,
                 4xx request errors
streaming        no retry after the first byte was sent: emit `error`, the client may re-request
deadline         every retry and backoff sits inside the request deadline
```

## Transport-specific fallbacks (intentional divergence)

| Transport | On failure | Why |
|---|---|---|
| Synchronous HTTP route | Typed body (`status`, safe copy, `error_code`), HTTP 200 for expected degraded outcomes; 503 + opaque code for unexpected faults | No dead-end 500 for the user; clients branch on `status` |
| SSE stream | One `error` event with an opaque code, then close; no `done` after it | Single terminal event contract (`agentic-streaming-hitl.md`) |
| Queue / push consumer | Non-2xx (or nack) so the broker redelivers; dead-letter after N | Redelivery is the retry mechanism; a 200 would drop the message |
| Downstream publish fails after a result was computed | Persist/return the computed result; retry the publish via outbox | Do not throw away a valid result because a notification failed |

Document this divergence next to the code so nobody "fixes" a consumer into returning 200.

## Error taxonomy (agent contract)

Closed set returned to callers and recorded in traces:

| Code | Meaning |
|---|---|
| `INPUT_REJECTED` | Validation or deterministic policy gate refused the input |
| `UNAUTHORIZED` | Principal lacks permission for the resource or action |
| `INSUFFICIENT_EVIDENCE` | Grounding tools failed or returned nothing (deterministic gate) |
| `TOOL_UNAVAILABLE` | A required tool/backend is down |
| `MODEL_UNAVAILABLE` | Provider unavailable after retry/failover |
| `SCHEMA_VALIDATION_FAILED` | Model output failed the schema after the bounded retry |
| `ITERATION_LIMIT` / `TIMEOUT` | Step/call cap or deadline hit |
| `HUMAN_REVIEW_REQUIRED` | Pending approval; run is parked in the checkpointer |

## Common Python traps

- `next(gen)` on an exhausted generator inside `async def` turns into `RuntimeError` (PEP 479) and escapes the fallback path: use `next(gen, None)` and an explicit degraded result.
- `except Exception` at a route boundary does not catch `asyncio.CancelledError` (a `BaseException`): good, client disconnects must cancel the run. Never catch `BaseException` there. For a streamed LangGraph run this is necessary but not sufficient: the in-flight model call survives Starlette's disconnect cancel unless the run is an owned task cancelled in `finally` (`agentic-streaming-hitl.md`).
- `asyncio.wait_for` / `asyncio.timeout` raise `TimeoutError`; map it explicitly instead of letting it become a 500.

## WRONG → RIGHT

```python
# WRONG: exception text to the user and into the model context; no retry actually happens
except LLMProviderError as e:
    return {"messages": [AIMessage(content=f"I encountered an error: {e}")]}

# WRONG: exception text in the HTTP response and in logs
raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")
logger.error("invoke_failed", error=str(e))

# RIGHT: route boundary
except Exception as exc:  # noqa: BLE001
    log_exception(logger, "agent_invoke_failed", exc, thread_id=str(thread_id))
    raise HTTPException(status_code=503, detail={"error_code": "AGENT_UNAVAILABLE"}) from None
```

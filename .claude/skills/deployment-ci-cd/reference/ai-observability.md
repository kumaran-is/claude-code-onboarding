# AI Observability (LLM calls, agents, tools, retrieval)

Extends `python-observability.md`; it does not replace it. Use the SAME TracerProvider (section 3 there), the same request-id middleware (section 4) and the same `log_exception` helper (section 2). AI spans are children of the HTTP request span, so one trace shows request → agent → model → tool → retrieval. Framework specifics: ADK in `.claude/skills/adk-observability-guide/`, LangSmith/LangGraph in `.claude/skills/agentic-ai-dev/reference/agentic-observability.md`; both must follow the content-capture and redaction rules below.

Section 2 executed with Python 3.14 and opentelemetry-sdk 1.45.2; section 7 with langfuse 5.2.0 on Python 3.14.10 (scripted fake model, `InMemorySpanExporter`, `InMemoryMetricReader`; 5 tests pass; `ruff` and `mypy --strict` clean on the full module, of which the snippet is an excerpt: imports and dataclasses omitted). No live provider was called.

## 1. Span model (OpenTelemetry GenAI semantic conventions)

| Operation | Span name | `gen_ai.operation.name` | Kind | Key attributes |
|---|---|---|---|---|
| Agent run | `invoke_agent {agent}` | `invoke_agent` | INTERNAL (CLIENT if remote) | `gen_ai.agent.name` |
| Model call | `chat {model}` (Gemini-style APIs: `generate_content {model}`) | `chat` / `generate_content` | CLIENT | `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| Tool call | `execute_tool {tool}` | `execute_tool` | INTERNAL | `gen_ai.tool.name`, `gen_ai.tool.call.id` |
| Retrieval | `retrieval {index}` | `retrieval` | CLIENT | `app.retrieval.k`, returned chunk ids count |
| Embedding | `embeddings {model}` | `embeddings` | CLIENT | provider, model, input token count |
| Rerank | `rerank` (no semconv value yet) | — | INTERNAL | `app.rerank.candidates`, `app.rerank.kept` |

- Use `gen_ai.provider.name`, NOT the deprecated `gen_ai.system`; use `gen_ai.usage.input_tokens`/`output_tokens`, NOT `prompt_tokens`/`completion_tokens`.
- The GenAI conventions have development stability and moved to the `open-telemetry/semantic-conventions-genai` repository (verified on Context7). Pin the semconv version you emit, and re-check names when you upgrade an instrumentation library.
- App-specific attributes use your own namespace (`app.*`): never invent `gen_ai.*` names (e.g. cost is `app.llm.cost_usd`, not `gen_ai.usage.cost_usd`).

## 2. Framework-neutral helper (executed)

```python
from opentelemetry import metrics, trace
from opentelemetry.trace import Span, SpanKind, StatusCode

tracer = trace.get_tracer("app.ai")
meter = metrics.get_meter("app.ai")
token_usage = meter.create_histogram("gen_ai.client.token.usage", unit="{token}")
op_duration = meter.create_histogram("gen_ai.client.operation.duration", unit="s")
ttft = meter.create_histogram("app.llm.time_to_first_token", unit="s")


@contextmanager
def ai_span(name: str, kind: SpanKind, attrs: dict[str, Any]) -> Iterator[Span]:
    """Span that records error.type only: never str(exc) in status, events or attributes."""
    with tracer.start_as_current_span(
        name, kind=kind, attributes=attrs, record_exception=False, set_status_on_exception=False
    ) as span:
        try:
            yield span
        except GeneratorExit:
            span.set_attribute("app.stream.closed", True)   # consumer closed the stream (aclose/break): not an error
            raise
        except BaseException as exc:
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(StatusCode.ERROR)
            raise


async def traced_chat(*, provider: str, model: str, prompt: ServedPrompt, sent_system_text: str,
                      feature: str, call: Callable[[], Awaitable[ModelResult]]) -> ModelResult:
    base = {"gen_ai.provider.name": provider, "gen_ai.request.model": model, "app.feature": feature}
    attrs = {
        **base,
        "gen_ai.operation.name": "chat",
        "app.prompt.name": prompt.name, "app.prompt.label": prompt.label,
        "app.prompt.version": prompt.version, "app.prompt.sha256": prompt.content_hash,
        "app.prompt.rendered_sha256": sha256(sent_system_text),
        # frameworks append text: assert containment, not equality; warn, never block
        "app.prompt.intact": bool(prompt.text) and prompt.text in sent_system_text,
    }
    start = time.monotonic()
    with ai_span(f"chat {model}", SpanKind.CLIENT, attrs) as span:
        try:
            result = await call()
        except BaseException as exc:
            op_duration.record(time.monotonic() - start, {**base, "error.type": type(exc).__name__})
            raise
        span.set_attributes({
            "gen_ai.response.model": result.response_model,
            "gen_ai.usage.input_tokens": result.input_tokens,
            "gen_ai.usage.output_tokens": result.output_tokens,
        })
    op_duration.record(time.monotonic() - start, base)
    token_usage.record(result.input_tokens, {**base, "gen_ai.token.type": "input"})
    token_usage.record(result.output_tokens, {**base, "gen_ai.token.type": "output"})
    return result
```

`ServedPrompt` is the frozen record the prompt registry returns (name, label, version, content_hash, text; registry contract in `.claude/skills/eval-guide/reference/langfuse-prompts.md`). `ModelResult` is your gateway's normalized response. For streaming, wrap the chunk iterator in the same `ai_span` and record `ttft` on the first chunk; the span ends on every exit path. Executed with an in-memory exporter: a consumer task cancelled mid-stream ends the span with `error.type=CancelledError` and status ERROR (a deadline looks the same inside the span, so keep cancellations out of the provider error-rate SLO or alert on them separately); a generator closed by its consumer (`aclose()`, `break`, the sse-starlette / Starlette close paths) raises `GeneratorExit` inside it, which `ai_span` records as `app.stream.closed=true` with no `error.type` and no ERROR status, so normal client closes do not inflate the error rate.

Why `record_exception=False`: the SDK default records the exception MESSAGE as a span event, and `set_status(ERROR, description=str(exc))` puts it in the status. Executed: with the default, a fake email inside the exception was exported; with the helper it was not (positive control: the email was in the exception), and reverting `record_exception=False` made the test fail.

## 3. Trace propagation across agents, tools and retrieval

- Async tasks inherit the current span through `contextvars` (`asyncio.create_task` and `asyncio.to_thread` copy the context). `loop.run_in_executor` and a raw `ThreadPoolExecutor` do not: submit `contextvars.copy_context().run(fn, ...)`.
- Sub-agents or tool servers over HTTP: the httpx instrumentor injects W3C `traceparent`; queues and MCP/RPC transports need `opentelemetry.propagate.inject(carrier)` / `extract(carrier)` (`python-observability.md` section 3).
- A framework with its own tracer (ADK, LangSmith, Langfuse) must share or attach to the app TracerProvider, otherwise you get two disconnected traces per request. Assert one `trace_id` across agent, model, tool and retrieval spans in a test (section 8).
- Put `request_id`, a hashed principal id and the feature name on the root AI span; never names, emails or raw query text.

## 4. Metrics, cost and labels

| Metric | Type | Labels (bounded only) |
|---|---|---|
| `gen_ai.client.token.usage` | histogram `{token}` | provider, request model, `gen_ai.token.type`, feature |
| `gen_ai.client.operation.duration` | histogram `s` | provider, model, feature, `error.type` |
| `app.llm.time_to_first_token` | histogram `s` | provider, model, feature |
| `app.llm.cost_usd` | counter | provider, model, feature |
| `app.ai.tool_calls` / tool latency | counter / histogram | tool, outcome |
| `app.ai.fallbacks`, `app.ai.abstains`, `app.ai.refusals`, `app.ai.contract_rejects` | counter | feature, reason (enum) |
| `app.ai.cache_hits` | counter | cache name, hit/miss |
| `app.ai.budget_exhausted` | counter | feature, budget kind (calls, tokens, cost, deadline) |

- Never put user, organization or tenant ids, prompts or model output in metric labels (unbounded cardinality, and PII). Per-organization cost anomalies come from traces/logs keyed by a hashed org id.
- Cost: a price table keyed by the EXACT model id, with source URL and the date it was read. Unknown model id → log `cost_unknown_model` (model id only), emit cost 0 with `app.llm.cost_known=false`; never silently price it as another model. Prices change: link the provider pricing page, do not hard-code a table in docs.
- OTel also defines server-side GenAI metrics (e.g. time to first token on the serving side); the client TTFT above is an app metric. Check the current `semantic-conventions-genai` metric list before naming a new one.

## 5. Content capture and redaction (default OFF in production)

Prompts, retrieved chunks, tool arguments and model output contain user data. Production default: capture metadata (ids, hashes, versions, counts, token usage), not content.

| Tool | Default | Production setting |
|---|---|---|
| OTel GenAI instrumentations | varies by library | `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT` |
| Google ADK 2.15 | no content: the default GenAI semconv 1.44 schema reads `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` (default `NO_CONTENT`); `SPAN_ONLY`, or the legacy `ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN=otel_semconv_1_36` schema (where `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS` defaults to true), puts prompt text in spans | leave the OTel variable at `NO_CONTENT`, do not opt into the legacy schema, keep `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` + `ADK_TELEMETRY_IGNORE_RUN_CONFIG=1` as belt and braces (`adk-observability-guide`) |
| Langfuse `@observe` | `capture_input`/`capture_output` True (`LANGFUSE_OBSERVE_DECORATOR_IO_CAPTURE_ENABLED` unset) | set that variable to `false`, or pass a recursive `mask=` function to `Langfuse(...)` (section 7) |
| LangSmith | traces inputs and outputs | `LANGSMITH_HIDE_INPUTS=true`, `LANGSMITH_HIDE_OUTPUTS=true`, or a `create_anonymizer(...)` client |

- Langfuse `@observe` records `status_message=str(e) or type(e).__name__` when the wrapped function raises (read in the langfuse 5.2.0 source, `_client/observe.py`): do not decorate functions whose exceptions carry request data, or catch and re-raise a sanitized error inside them.
- Redaction in a tracing callback must fail CLOSED: if the masker raises, drop the content field, never export the raw value.
- When content capture is required (debugging, eval sampling), make it a sampled, time-boxed, environment-scoped decision with its own retention.
- The trace store is sensitive production data: organization isolation, role-based access, retention TTL, access audit, deletion/legal hold, no global cross-organization browsing. Deletion requests must reach traces, exported datasets and eval copies.

## 6. Prompt provenance

Record on every model-call span: registry prompt name, label, version, `content_hash`, plus the SHA-256 of the system text actually sent and an `app.prompt.intact` containment check (section 2). A mismatch means a framework processor or a code path changed the prompt: log a warning event (`prompt_integrity_mismatch`, name and version only) and alert on its rate; never block the request on it. With the model id and flag states on the same span, an incident can be attributed to an exact prompt and model version.

## 7. Langfuse (optional extension)

Langfuse is optional; OTel plus your existing backend is enough. If you use it, pin `langfuse==5.2.0` (Python >= 3.11). Checked by introspecting the installed 5.2.0 package and by running it against a local OpenTelemetry Collector with no Langfuse server: SDK and export path only, no server-side behaviour was exercised.

```python
from langfuse import Langfuse, get_client, observe, propagate_attributes

langfuse = Langfuse(                     # once at startup; elsewhere get_client()
    tracer_provider=tracer_provider,     # the app provider: one trace id across HTTP, DB and LLM spans
    environment=settings.environment, release=settings.release,
    mask=redact_nested,                  # input/output/metadata pass through it before export
)


@observe(as_type="retriever")
def retrieve(query: str) -> list[Chunk]: ...


@observe()
def answer(query: str) -> str:
    chunks = retrieve(query)
    with langfuse.start_as_current_observation(
        name="llm-call", as_type="generation", model=model_id, input=messages
    ) as generation:
        result = call_model(messages)
        generation.update(output=result.text,
                          usage_details={"input": result.input_tokens, "output": result.output_tokens})
    return result.text


with propagate_attributes(user_id=hashed_user_id, session_id=session_id, tags=["support"]):
    answer(query)
```

| Removed or renamed (v2 to v4 era) | Current 5.2.0 API |
|---|---|
| `from langfuse.decorators import observe, langfuse_context` | `from langfuse import observe, get_client` (`langfuse.decorators` no longer exists: `ModuleNotFoundError`) |
| `langfuse.trace(...)`, `.span(...)`, `.generation(...)`, `.score(...)` on the client | `start_as_current_observation(name=..., as_type=...)` / `start_observation(...)`; `as_type` is one of span, generation, embedding, agent, tool, chain, retriever, evaluator, guardrail |
| `start_as_current_span` / `start_as_current_generation` (v3) | `start_as_current_observation(as_type="span" / "generation")` |
| `update_current_trace(user_id=..., session_id=..., tags=...)` | `propagate_attributes(user_id=..., session_id=..., tags=..., metadata=..., version=...)` context manager |
| `langfuse.score(...)` | `create_score(name=, value=, trace_id=, observation_id=, data_type=)`, `score_current_trace(...)`, `score_current_span(...)` |
| `host=` / `LANGFUSE_HOST` | `base_url=` / `LANGFUSE_BASE_URL` (`host` and `LANGFUSE_HOST` still read, documented as deprecated) |

- Masking: the `mask` callable is called with `data=` holding the structured value. `@observe` input arrives as `{"args": [...], "kwargs": {...}}`. Executed: a mask that only handled `str` exported a planted email unchanged; a recursive one (walk dicts and lists, redact strings) removed it. When the mask raises, 5.2.0 logs `Masking error` and exports a fallback mask value (fails closed).
- Missing `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` does NOT raise: the client logs an authentication error and uses a NoOp tracer. In environments that require tracing, check the keys at startup and fail the deploy.
- Default export filter (`is_default_export_span`): Langfuse SDK spans, spans with any `gen_ai.*` attribute and known LLM instrumentation scopes. HTTP and DB spans still go to your OTLP backend only. Override with `should_export_span=`.
- Scores are sent over the Langfuse API, not OTLP: with no server, `score_current_trace` logged `Failed to send 1 scores ... dropped` and did not raise. Do not use Langfuse scores as the only record of a CI eval result; the eval runner writes its own result rows (`eval-guide/reference/pytest-harness.md`).
- Call `langfuse.flush()` (or `shutdown()`) in the same SIGTERM/lifespan path as `Telemetry.shutdown()` (`python-observability.md` section 3.1).
- Prompt management (`get_prompt(name, label=..., fallback=...)`, versions and labels): `.claude/skills/eval-guide/reference/langfuse-prompts.md`.

## 8. Contract tests (run them in CI)

1. **Completeness**: a fixture run with a scripted fake model produces ONE trace containing agent, model, tool, retrieval and rerank spans with the required attributes (`gen_ai.provider.name` present, `gen_ai.system` absent).
2. **No exception text**: a traced call raises an exception carrying a fake email; assert the email is absent from every exported attribute, event and status; positive control: assert it was in the exception, and a negative-control span with SDK defaults DOES leak it.
3. **No content when capture is off**: with production env settings, assert no prompt or output text in exported spans (plant a unique marker string in the prompt).
4. **Prompt integrity**: a sent system text that does not contain the registry text sets `app.prompt.intact=false`.
5. **Metrics**: token usage carries `gen_ai.token.type` input/output; no metric label key looks like a user/tenant id.

Tests 1, 2, 4 and 5 were executed against the helper above (pytest, `asyncio_mode=auto`); test 3 depends on the tracer stack you deploy and is a pattern to implement, not executed here.

## 9. SLOs, alerts and drift

Every alert has a named owner, a runbook link, a dedup key and a threshold tuned so legitimate surges do not page forever.

| Signal | Alert on | Typical response |
|---|---|---|
| Cost burn | spend rate per feature vs budget; per-organization anomaly from traces | throttle, check runaway loops, kill switch |
| Runaway loops | call-limit / budget-exhausted counter > 0 (page on sustained) | inspect trace, lower budget, fix loop |
| Fallback / escalation rate | rise vs 7-day baseline | provider status, quota (429 vs billing), recent prompt/model change |
| Refusal / abstain spike | rise vs baseline | prompt or retrieval regression, policy change at provider |
| Contract rejects | schema/business-rule reject rate | prompt/model drift; roll back label |
| Groundedness / citation failures | rate of cited-id-not-retrieved or judge fail | retrieval/index regression |
| Latency | p95 duration and TTFT vs SLO | provider latency, context growth, cache misses |
| Eval score trend | scheduled eval on a frozen set drops | compare by prompt version and model id |

Drift = these signals moving with no deploy. Compare by `app.prompt.version`, `gen_ai.response.model` (providers update models behind aliases: pin versions) and index version. Burn-rate alert mechanics for Prometheus: `.claude/skills/adk-observability-guide/reference/slo-alerting.md`.

## 10. Incident replay

From a trace id: read prompt name/version/hash, model ids, flag states, retrieval chunk ids and the registry tier served (fresh, last-known-good, bundled). Rebuild the input from your own stores (not from captured content), reproduce with the same versions, then add a PII-scrubbed golden case that fails before the fix (`.claude/skills/ai-incident-response/SKILL.md` Stage 4).

## 11. Checklist

- [ ] AI spans share the app TracerProvider; one trace per request across agent, model, tool, retrieval, rerank (test)
- [ ] Langfuse (if used): 5.x API only (no `langfuse.decorators`, `.trace()`, `update_current_trace`); recursive mask tested with a planted value; flushed on shutdown
- [ ] Current semconv names (`gen_ai.provider.name`, `input_tokens`/`output_tokens`); semconv version pinned; custom attributes under `app.*`
- [ ] No exception text in spans, logs or Langfuse status (test with a positive control)
- [ ] Content capture OFF in production for every tracer in use (OTel, ADK three variables, Langfuse, LangSmith); trace store access-controlled with retention
- [ ] Prompt name/label/version/hash and model ids on every model-call span; integrity mismatch alerting
- [ ] Token, duration, TTFT, cost, tool, fallback, refusal, budget metrics with bounded labels; unknown model price flagged
- [ ] Alerts have owners, runbooks and dedup; drift compared by prompt and model version

# Agentic AI Observability (LangChain v1)

LangChain/LangGraph wiring for traces, metrics and logs. The canonical, framework-neutral rules — span model (OpenTelemetry GenAI conventions), metric names and bounded labels, cost accounting, content capture defaults, prompt provenance, SLOs and alerts — live in `deployment-ci-cd/reference/ai-observability.md`. Logging rules and `log_exception`: `deployment-ci-cd/reference/python-observability.md`.

REMOVED from the previous version: `os.environ[...]` mutation at startup with legacy `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY`/`LANGCHAIN_PROJECT` names; a "groundedness" evaluator that scored by substring match; a node decorator logging `error=str(e)` and reading `thread_id` from state; a `rag_relevance_score` histogram fed by unverified scores; and a `histogram_quantile` alert without `rate()`/`sum by (le)`.

## LangSmith tracing (optional)

Configure through the environment of the deployment, not by mutating `os.environ` in code (mutations race with imports that already read config, and leak the key into child processes):

| Variable | Purpose |
|---|---|
| `LANGSMITH_TRACING` | `true` to enable |
| `LANGSMITH_API_KEY` | From the secret manager |
| `LANGSMITH_PROJECT` | Per environment (`<service>-staging`, `<service>-prod`) |
| `LANGSMITH_ENDPOINT` | Only for self-hosted / regional endpoints |

Source: LangChain docs (LangChain docs MCP, this session). The `LANGCHAIN_*` names are legacy; don't introduce them in new code.

- Content capture: traces contain prompts, tool arguments and outputs by default. Decide per environment what may leave your boundary (`ai-observability.md` §5); production default is metadata only unless redaction is in place and the data-processing terms allow it.
- Attach run metadata, not PII: `config={"metadata": {"feature": ..., "prompt_version": ..., "model_id": ...}, "tags": [...]}`. Org/user ids, if needed for support, go in as hashed values per `ai-observability.md`.
- Tracing must never break a request: an unreachable tracing backend is logged once and ignored.

Evaluators (LangSmith, DeepEval, Ragas, ...) belong to the eval harness: `eval-guide`. Groundedness is judged by a calibrated judge or a claim-level check, not by substring matching.

## Model-call metrics middleware (executed)

One middleware covers every model call the agent makes, including calls after tool results:

```python
LLM_TOKENS = Counter("app_llm_tokens_total", "Tokens by type", ["model", "feature", "token_type"])
LLM_DURATION = Histogram("app_llm_call_duration_seconds", "Model call duration", ["model", "feature", "outcome"],
                         buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40))


class ModelMetricsMiddleware(AgentMiddleware[Any, Any]):
    """Labels come from config (model id, feature), never from request data."""

    def __init__(self, *, model_label: str, feature: str) -> None:
        super().__init__()
        self.model_label, self.feature = model_label, feature

    async def awrap_model_call(self, request: ModelRequest,
                               handler: Callable[[ModelRequest], Awaitable[ModelResponse]]) -> ModelResponse:
        start = time.monotonic()
        try:
            response = await handler(request)
        except Exception as exc:
            LLM_DURATION.labels(self.model_label, self.feature, type(exc).__name__).observe(time.monotonic() - start)
            log_exception(logger, "model_call_failed", exc, feature=self.feature)
            raise
        LLM_DURATION.labels(self.model_label, self.feature, "ok").observe(time.monotonic() - start)
        for msg in response.result:
            if isinstance(msg, AIMessage) and msg.usage_metadata:
                u = msg.usage_metadata
                LLM_TOKENS.labels(self.model_label, self.feature, "input").inc(u["input_tokens"])
                LLM_TOKENS.labels(self.model_label, self.feature, "output").inc(u["output_tokens"])
                LLM_TOKENS.labels(self.model_label, self.feature, "reasoning").inc(
                    u.get("output_token_details", {}).get("reasoning", 0))
                LLM_TOKENS.labels(self.model_label, self.feature, "cache_read").inc(
                    u.get("input_token_details", {}).get("cache_read", 0))
        return response
```

Executed with `create_agent` and a scripted message carrying `usage_metadata` (100 in / 40 out / 30 reasoning / 60 cache-read): all four series and the duration count matched; `ruff` and `mypy --strict` clean. Exception class names are a bounded label set; never use `str(exc)` as a label. Add it before retry/fallback middleware to count each attempt, after them to count each logical call; name the choice in the metric help text.

Other counters to emit (names and labels per `ai-observability.md` §4): tool calls by tool + outcome code, retries, failovers (from → to model label), cap hits (`ITERATION_LIMIT`, `TIMEOUT`, `BUDGET_EXHAUSTED`), guardrail blocks by code, cache hits by tier, HITL approvals pending/expired. **Time to first token** for streaming routes: measure in the SSE generator from request start to the first `content` event.

## Logs

- Per run: one structured line at start and end with trace id, feature, model id, prompt version, thread key **hash**, outcome code, duration, call/tool counts. No message text.
- Errors: `log_exception(logger, event, exc, **ids)` only.
- Node-level logging comes from tracing spans; don't wrap every node in a logging decorator.

## Alerts (examples; thresholds from your SLOs)

```yaml
groups:
  - name: agent
    rules:
      - alert: AgentModelLatencyP95High
        expr: histogram_quantile(0.95, sum by (le, feature) (rate(app_llm_call_duration_seconds_bucket[5m]))) > 20
        for: 10m
        labels: {severity: warning}
      - alert: AgentModelErrorRatio
        expr: |
          sum by (feature) (rate(app_llm_call_duration_seconds_count{outcome!="ok"}[5m]))
          / sum by (feature) (rate(app_llm_call_duration_seconds_count[5m])) > 0.05
        for: 10m
        labels: {severity: critical}
```

Cost and budget alerts, drift, and quality SLOs: `ai-observability.md` §9. Provider-console spend caps are the hard stop.

## Key Rules

| Rule | Standard |
|---|---|
| Tracing config | `LANGSMITH_*` env from the deployment; no `os.environ` mutation |
| Content capture | Off or redacted in production per `ai-observability.md` §5 |
| Metric labels | Bounded: model (from config), feature, outcome/exception class, tool; never org/user/thread ids |
| Tokens | Input, output, reasoning and cache-read series from `usage_metadata` |
| Errors | `log_exception`; exception class as a label at most |
| Alerts | `histogram_quantile` over `sum by (le) (rate(...))` |

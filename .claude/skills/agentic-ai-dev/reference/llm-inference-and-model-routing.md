# LLM Inference and Model Routing

Canonical, framework-neutral home for how a service calls models: provider abstraction, model ids and lifecycle, sampling and reasoning controls, structured outputs, deadlines, retries and 429s, failover vs escalation, caching and cache-key scoping, token budgets, and multimodal input limits. LangChain v1 implementation details are in `agentic-llm-routing.md`; Google GenAI/ADK specifics in `gemini-api-dev` and `google-adk`. Cost dashboards, quota hooks and AI tracing: `deployment-ci-cd/reference/ai-observability.md`; release/promotion of model changes: `deployment-ci-cd/reference/llmops-release-and-rollout.md`.

Validation: the Python core in §5–§8 was executed (Python 3.14, `ruff` + `mypy --strict` clean, 7 pytest cases with a scripted transport). No live provider was called: provider behaviour statements carry their source.

## 1. One model client per service

Feature code never instantiates provider SDKs. One module owns:

| Responsibility | Why |
|---|---|
| Model construction from settings | Model ids live in config only |
| Error mapping (SDK exceptions → the taxonomy in §5) | Retry/failover decisions use types, not `str(exc)` |
| The single retry layer + deadline | Stacked SDK + framework + app retries multiply latency and cost |
| Failover policy | Same tier, approved equivalents, availability errors only |
| Token/cost metering (incl. reasoning and cached tokens) | Budgets and dashboards are only as good as this |
| Content-capture policy | What prompt/response text may reach traces and logs |
| Provider allowlist per data class/region | Authorization to read data is not authorization to send it to a provider (egress check before any call: `agentic-llm-routing.md` §3) |

## 2. Model ids and lifecycle

```python
class ModelSettings(BaseSettings):
    chat_model: str          # required: no default in code; startup fails if unset
    router_model: str
    embedding_model: str
```

- No floating aliases (`latest`, `default`, auto-upgrade ids) in production unless the alias behaviour is controlled and evaluated (guardrails G11); routing chooses only among approved configurations from a registry, and an unlisted id is rejected, not passed through (G20).
- No model id literal in code, test assertions (compare with `settings.chat_model`) or CI YAML; one env/config matrix per environment.
- Before changing a model id: (1) send a probe call to **each environment's real endpoint** next to a model known to work (hosted-API and cloud-platform catalogues and parameter support differ); (2) change config only; (3) run the eval gate; (4) record date and reason. Promotion/rollback: `llmops-release-and-rollout.md`.
- Keep no price tables in code. Prices change: link the provider pricing page with a "checked on" date, or load prices from config keyed by exact model id; an unknown id logs `cost_unknown_model` and reports cost as unknown, never another model's price.
- Check capabilities before routing or failing over to a model: context window, tokenizer, tool calling + structured output together, vision/audio, reasoning controls, region/data terms.

## 3. Sampling and reasoning controls

There is no universal "temperature 0 for facts" rule.

| Model family | Guidance | Source |
|---|---|---|
| Gemini 3.x | Keep `temperature`, `top_p`, `top_k` at defaults; values below 1.0 "may lead to unexpected behavior, such as looping or degraded performance". Use `thinking_level` (`minimal`/`low`/`medium` default/`high`), not the numeric `thinking_budget` | ai.google.dev Gemini 3 docs (Context7, this session) |
| Other reasoning models | Some restrict or reject sampling parameters or use a reasoning-effort control instead | Check the provider's model page before setting them (not verified here) |
| Non-reasoning models | Low temperature can reduce variance for extraction/classification | Measure with evals; it is not a correctness guarantee |

Rules:
- Determinism comes from schemas, validators and invariant-based evals, not from temperature.
- Choose the reasoning level **per call class**: low for extraction, translation and validator-checked grounded answers; higher only where evals show it helps. Some models reject some levels: probe each model.
- Reasoning tokens are billed as output and count against the output-token limit. Size `max_output_tokens` for reasoning + answer. An empty answer with a length/`MAX_TOKENS` finish is a **defect** (`EmptyOutputError` in §5), never a valid empty result.
- Don't add "think step by step" to reasoning models: it is redundant and adds output tokens. Ask for a concise final answer.

## 4. Structured outputs

- Use the provider's schema mechanism (LangChain: `with_structured_output(Model, include_raw=True)` — plus `method="json_schema"` where the provider integration accepts it — or `create_agent(response_format=ToolStrategy(Model, handle_errors=...) | ProviderStrategy(Model))`, both in `langchain.agents.structured_output`; ADK: `output_schema`), not "respond in JSON" prompts plus `json.loads`.
- Treat parse failure as an outcome: `include_raw=True` exposes the raw message and parsing error; a refusal can produce no parsed object.
- On a malformed or empty structured result: **one** retry in a **fresh context** (do not replay the failed turn), reset any streaming parser state, count it (`llm_structured_retry_total{feature}`), and only when every tool on the path is read-only or idempotent. Then return `SCHEMA_VALIDATION_FAILED`.
- Never retry safety/refusal/recitation or max-token finishes.
- Validate business rules after the schema passes; a model-reported `confidence` field is not verification.

## 5. Errors, deadlines and retries (executed core)

```python
class ModelCallError(Exception):
    retryable = False

class UnavailableError(ModelCallError):      # 408/500/502/503/504, timeout, connection reset
    retryable = True

class RateLimitedError(ModelCallError):      # 429 with a short Retry-After / RetryInfo
    retryable = True
    def __init__(self, retry_after_s: float | None) -> None:
        super().__init__("rate limited")
        self.retry_after_s = retry_after_s

class QuotaExhaustedError(ModelCallError): ...   # 429 meaning quota used up: never retry (SDK status-code retry
                                            # lists cannot tell; see gemini-api-dev §Error Handling)
class InvalidRequestError(ModelCallError): ...   # 400, context overflow, schema rejected
class EmptyOutputError(ModelCallError): ...      # length finish with no answer text
class BudgetExhaustedError(ModelCallError): ... # per-request call/token budget spent (§9)


async def call_model(send: Callable[[], Awaitable[ModelResult]], *, deadline_s: float,
                     budget: RunBudget, policy: RetryPolicy) -> ModelResult:
    start = time.monotonic()
    async with asyncio.timeout(deadline_s):         # every retry and wait sits inside this deadline
        attempt = 0
        while True:
            budget.charge_call()                     # every attempt counts, including ones that fail
            try:
                result = await send()
            except ModelCallError as exc:
                if not exc.retryable or attempt >= policy.attempts:
                    raise
                delay = policy.rng.uniform(0, min(policy.max_delay_s, policy.base_delay_s * 2**attempt))
                if isinstance(exc, RateLimitedError) and exc.retry_after_s is not None:
                    delay = exc.retry_after_s
                if time.monotonic() - start + delay >= deadline_s:
                    raise                            # waiting would overrun the deadline
                attempt += 1
                await asyncio.sleep(delay)
                continue
            budget.charge_tokens(result)
            if result.finish == "length" and not result.text.strip():
                raise EmptyOutputError("output budget consumed before any answer text")
            return result
```

Executed: 503 → 429(short) → OK succeeded in 3 sends; `QuotaExhaustedError` and `InvalidRequestError` failed after 1 send; a 30 s Retry-After inside a 1 s deadline failed immediately; an empty `length` result raised `EmptyOutputError`; the cumulative budget raised on the third call.

- **Exactly one retry layer.** If the SDK or framework retries (e.g. `ModelRetryMiddleware`, `with_retry`, SDK retry options), turn the others off. Some SDKs retry by default, others never retry unless configured (google-genai: no retries unless `HttpRetryOptions` is set — see `gemini-api-dev`). Check yours.
- Map SDK errors to the taxonomy by **status code / exception class**, never by matching `str(exc)`.
- Deadlines are per call class (router classifier vs streamed answer vs background job), sized from measured p99 × 1.5, set per environment. A deadline measured while tools were failing fast is wrong: re-measure on the working path.
- Client disconnect or a passed deadline must cancel the upstream call (let `CancelledError` propagate) so it does not finish late and still bill. Propagation alone is not enough when a framework runs the call in its own tasks: under Starlette's anyio cancel scope a LangGraph `astream` model call ran to completion after disconnect. Run it in a task the stream owns and `task.cancel()` it in `finally` (`agentic-streaming-hitl.md` §FastAPI SSE Endpoint).
- Check SDK timeout units (google-genai `HttpOptions.timeout` is milliseconds).

## 6. Failover vs escalation

| | Provider failover | Quality escalation |
|---|---|---|
| Trigger | Availability errors only (timeout, connection, 5xx, short-retry 429) | A deterministic validator or eval-backed check failed |
| Target | Approved equivalent in the **same tier**, same data-class/region approval, same evals and schema | A higher tier |
| Never on | Refusal/safety, 400, auth, context overflow, schema errors, quota exhaustion | An exception |
| Side effects | Reuse idempotency keys and already-created entity ids; never replay a successful mutation | Same |

Never fall back silently to a weaker, unevaluated model. If no approved same-tier equivalent answers, the documented conservative fallback is a higher approved tier or the non-AI path, with the degradation visible; never a lower tier (failover order: `agentic-llm-routing.md` §12). For safety-capable paths the fallback config must have passed the same safety gate as the primary; if it has not, degrade to the deterministic/manual flow and say so to the user (guardrails G6). Log which model answered (trace attribute + metric). A "cheap first, escalate" cascade is valid only when an objective verifier exists, and not for safety-critical or irreversible capabilities.

## 7. Routing between models

- Deterministic policy first (safety phrases, authority questions, obvious routes); an LLM classifier only for ambiguous cases.
- The classifier gets a minimal sanitized feature set (capability, modality, size bucket, flags), not the raw user message; it has its own short deadline, structured output, and a conservative deterministic fallback route with a `reason_code` when it times out or returns an invalid label.
- Images/documents: use at least the standard tier until capability-specific evals show a cheaper tier is enough.
- Tier names (FAST / STANDARD / STRONG), the approved-model registry, the policy gate, the decision record with closed reason codes, and LiteLLM Router settings: `agentic-llm-routing.md` (selection rule, floors, cascades, upgrades and routing telemetry in its §11–§19).

## 8. Caching and cache-key scoping

| Cache | Shareable across users/tenants? | Key must include |
|---|---|---|
| Provider prompt-prefix cache | Provider-managed | Byte-stable prefix: static system text → tool schemas → examples → then dynamic content (timestamps, user data, retrieved chunks). One volatile token early voids it. Measure cache-read tokens; check the provider's minimum length and write cost before claiming savings |
| Generated-answer cache (exact) | **No** | org + principal/ACL scope + model id + prompt version + tool/flag set + corpus version (`index_version`, bumped on ingest/update/erasure; `"none"` without retrieval) + normalized input |
| Semantic (similarity) answer cache | Only for public, tenant-independent FAQ answers | Namespace (org, model id, prompt version); evaluated false-hit rate; negation/entity flips ("cancel my order" vs "don't cancel my order") sit above typical similarity thresholds |
| Embedding cache | Yes, if vectors are tenant-independent (write that decision down) | model id + normalized text |

```python
def answer_cache_key(*, org_id: str, acl_scope: str, model_id: str, prompt_version: str,
                     tool_set: str, corpus_version: str, normalized_input: str) -> str:
    parts = [org_id, acl_scope, model_id, prompt_version, tool_set, corpus_version, normalized_input]
    if not all(parts[:6]):
        raise ValueError("cache key scope fields must be non-empty")
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()
```

Freshness- or safety-critical intents (classified, not keyword-matched) bypass **every** tier. Never write a fuzzy hit back under the new query's exact key. RAG answer keys built from a retrieval key (`rag-architect/references/rag-operations-guide.md`) already carry `index_version`; this key needs `corpus_version` for the same reason. Implementation tiers: `agentic-caching-patterns.md`.

## 9. Token budgets

```python
@dataclass
class RunBudget:
    """Cumulative across router, sub-agents, retries and fallback models for ONE user request."""
    max_calls: int
    max_tokens: int
    calls: int = 0        # attempts, including failed and retried ones (a failed call can still bill)
    tokens: int = 0

    def charge_call(self) -> None:
        """Call before every send; raises once the budget is spent."""
        if self.calls >= self.max_calls or self.tokens >= self.max_tokens:
            raise BudgetExhaustedError(f"calls={self.calls} tokens={self.tokens}")
        self.calls += 1

    def charge_tokens(self, r: ModelResult) -> None:
        self.tokens += r.input_tokens + r.output_tokens
```

- Count reasoning/thinking and cached-input tokens separately from prompt/candidate tokens (e.g. Gemini `usage_metadata.thoughts_token_count`, `cached_content_token_count`); cost code that reads only prompt + output counts under-reports reasoning models.
- Measure prompt size with the target model's token counter before calls near the limit; a model swap changes tokenizer and context limit.
- Budgets differ by capability and risk; exhaustion returns a typed status (no partial side effects). LangGraph enforcement: `tool-execution-safety.md` §8.

## 10. Multimodal input limits

- Cap images per request and **actual** bytes per item (measure the payload, not the declared size); charge image/audio tokens to the budget.
- Detect MIME type from magic bytes, not extension or client header; skip unknown types with a logged reason.
- Fetch media only from allow-listed storage locations; never fetch a URL supplied by the user or the model (SSRF).
- Text inside images, PDFs and transcripts is untrusted data: user/content parts only, same injection screening as text.

## 11. Review checklist

- [ ] Model ids only from settings; probe procedure documented
- [ ] Sampling/reasoning params match the provider's guidance for that model; output limit covers reasoning
- [ ] One retry layer; typed error mapping; quota 429 not retried; retries inside the deadline
- [ ] Failover same-tier and availability-only; escalation validator-driven
- [ ] Structured output via provider schema; one fresh-context retry; typed failure
- [ ] Answer caches scoped (org + ACL + model + prompt version); safety intents bypass all tiers
- [ ] Budgets cumulative per request; reasoning and cached tokens metered
- [ ] Multimodal byte/count caps, magic-byte MIME, storage allowlist

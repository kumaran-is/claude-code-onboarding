# Agentic AI LLM Routing & Multi-Provider Management (LangChain v1)

LangChain-specific implementation of the rules in `llm-inference-and-model-routing.md` (canonical: model lifecycle, sampling/reasoning, deadlines, retries, failover vs escalation, cache scoping, budgets). Read that first; this file shows how to wire it with LangChain 1.2.x / LangGraph 1.0.x.

## Model catalogue: config, not code

This file used to carry model/price tables. They went stale and contradicted each other (two rows for the same model id at different prices, retired ids in the tier map, "as of 2025" prices beside newer ones), so they were removed. Instead:

| Tier | Capability contract | Config key |
|---|---|---|
| `fast` | Classification, extraction, short answers; tool calling + structured output | `MODEL_FAST` |
| `standard` | Default chat + tools; images/documents floor | `MODEL_STANDARD` |
| `deep` | Long multi-step reasoning where evals show a gain | `MODEL_DEEP` |
| `embedding` | Retrieval embeddings (dimension pinned with the schema) | `EMBEDDING_MODEL` |

Each environment's config names the exact model id per tier (and an approved same-tier failover id). Prices and context limits: link the provider pages with a "checked on" date (Anthropic, OpenAI, Google AI / Vertex AI pricing pages). Rerankers and embedding choice: `rag-architect` and `vector-database`.

## Model construction

**File:** `src/<service>/llm/client.py`

```python
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from ..core.config import settings


def chat_model(tier: Literal["fast", "standard", "deep"]) -> BaseChatModel:
    """The only place that constructs chat models. Ids and params come from settings."""
    model_id = {"fast": settings.model_fast, "standard": settings.model_standard, "deep": settings.model_deep}[tier]
    return init_chat_model(model_id, **settings.model_params[tier])   # e.g. "anthropic:<id>", "openai:<id>"
```

- `init_chat_model("provider:model")` (or `create_agent(model="provider:model")`) replaces hand-rolled factories that pick a class by substring (`"claude" in model`). The provider integration package (e.g. `langchain-anthropic`) must be installed and pinned.
- `settings.model_params[tier]` holds provider-specific sampling/reasoning params (§Sampling in the canonical file). Do not set a global `temperature=0`.
- Turn off SDK-level retries in the integration (e.g. `max_retries=0` where offered) when middleware or `with_retry` is your retry layer: exactly one layer retries.

## Error mapping

Map each integration's exceptions once to the taxonomy (`UnavailableError`, `RateLimitedError`, `QuotaExhaustedError`, `InvalidRequestError`), keyed on exception class and HTTP status, never on `str(exc)`. The tuple of transient classes feeds `retry_on=` / `exceptions_to_handle=`:

```python
TRANSIENT: tuple[type[Exception], ...] = (
    # fill from the pinned SDKs: timeout, connection, 5xx, overloaded, short-retry rate limit classes
)
```

Verify class names against the installed SDK version; they differ between providers and majors.

## Failover

Use `TransientFallbackMiddleware` + `ModelRetryMiddleware(retry_on=TRANSIENT, on_failure="error")` from `agentic-templates-resilience.md`. Do not use a bare `primary.with_fallbacks([...])`: `exceptions_to_handle` defaults to `(Exception,)` (verified in langchain-core 1.8.4), so a 400, an auth error or a context overflow would switch provider. When composing manually, bind tools/structured output to **each** candidate before composing and pass `exceptions_to_handle=TRANSIENT`:

```python
model = chat_model("standard").bind_tools(tools).with_fallbacks(
    [failover_model.bind_tools(tools)],     # approved same-tier equivalent
    exceptions_to_handle=TRANSIENT,
)
```

REMOVED: the default chain `anthropic/balanced → openai/balanced → anthropic/fast` mixed failover with a silent downgrade to an unevaluated faster tier.

## Complexity router

Deterministic policy first, the classifier only when ambiguous, with a deadline, a validated label and a conservative fallback. Executed with a stub classifier: policy short-circuit, model route, timeout → `ROUTER_TIMEOUT`, invalid label → `ROUTER_INVALID`, a transient provider error (`ConnectionError`) → `ROUTER_UNAVAILABLE`; a non-transient error (e.g. auth) still raises so misconfiguration is loud.

```python
class RouteLabel(BaseModel):
    tier: Literal["fast", "standard", "deep"]


@dataclass(frozen=True)
class RouteFeatures:
    """Minimal, sanitized features: never the raw user message."""
    capability: str
    has_images: bool
    size_bucket: Literal["s", "m", "l"]


async def route(text: str, f: RouteFeatures, classifier: Any, timeout_s: float) -> Route:
    if _URGENT.search(text):
        return Route("standard", "POLICY_SAFETY")            # deterministic, before any model call
    if f.has_images:
        return Route("standard", "POLICY_MULTIMODAL_FLOOR")
    if f.size_bucket == "s" and f.capability == "faq":
        return Route("fast", "POLICY_OBVIOUS")
    try:
        async with asyncio.timeout(timeout_s):
            raw = await classifier.ainvoke(f"capability={f.capability} size={f.size_bucket} images={f.has_images}")
        label = RouteLabel.model_validate(raw)
    except TimeoutError:
        return Route("standard", "ROUTER_TIMEOUT")
    except ValidationError:
        return Route("standard", "ROUTER_INVALID")
    except TRANSIENT:                                          # provider unavailable: conservative route
        return Route("standard", "ROUTER_UNAVAILABLE")
    return Route(label.tier, "ROUTER_MODEL")
```

`classifier` is `chat_model("fast").with_structured_output(RouteLabel)` (returns a validated model; `model_validate` also accepts it). Log `reason_code` on every decision.

## Intent routing without generation

For routing a message to a handler (not to a model tier), an embedding router avoids a generation call: per-label prototype phrases, cosine similarity with a **threshold and a margin over the runner-up**, and an explicit "no match" that goes to the caller's deterministic fallback. Warm prototype embeddings at startup through a bounded-concurrency pool (a cold start must not cause a 429 burst). This replaces English keyword first-match classifiers and works across languages. Tune threshold/margin on a labelled set; the embedding model id is part of the prototype cache key.

## Prompt caching (provider specifics)

Ordering rule (all providers): static system text → tool schemas → examples → dynamic content (time, user data, retrieved chunks, memories). Anthropic marks cache breakpoints explicitly:

```python
SystemMessage(content=[{"type": "text", "text": STATIC_POLICY, "cache_control": {"type": "ephemeral"}}])
```

- Anything interpolated into `STATIC_POLICY` (a timestamp, a user name) breaks the cache on every call.
- Cache writes can cost more than uncached input and there are minimum cacheable lengths: check the provider page and **measure cache-read tokens** before claiming a saving. Gemini reports `cached_content_token_count`.
- Response/semantic caches are a different thing with different risks: `agentic-caching-patterns.md`.

## Cost estimation

Compute cost from **measured** usage (input, cached input, output including reasoning tokens) and a price map loaded from config keyed by exact model id. Unknown id → log `cost_unknown_model`, report cost as unknown, never substitute another model's price. Session projections must account for context growth per turn (input tokens grow with history unless trimmed). Metrics and dashboards: `deployment-ci-cd/reference/ai-observability.md`.

## Circuit breaking

Use the shared breaker from `python-dev/reference/reliability-idempotency-retries-outbox.md` §3 (half-open allows one probe; release in `finally` so a cancelled probe does not wedge it). An open breaker counts as `UnavailableError` for failover purposes.

## Key Rules

| Rule | Standard |
|------|----------|
| Model ids | Settings only; per-environment probe before a bump |
| Construction | `init_chat_model` in one module; never `ChatX()` inline in nodes |
| Sampling | Per provider guidance per model; no global temperature rule |
| Retry | One layer, transient classes only, inside the run deadline |
| Failover | Same tier, availability errors only, `exceptions_to_handle` always set |
| Router | Deterministic policy first; classifier with deadline + validated label + fallback |
| Caching | Stable prefix ordering; measure cache reads |
| Cost | From measured usage incl. reasoning + cached tokens; prices from config |

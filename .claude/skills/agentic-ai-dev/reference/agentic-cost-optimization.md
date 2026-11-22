# Agentic AI Cost Optimization

Strategies for measuring and reducing LLM cost in agent systems. Model lifecycle, budgets, cache-key scoping and token accounting rules are canonical in `llm-inference-and-model-routing.md`; dashboards and quota alerts in `deployment-ci-cd/reference/ai-observability.md`.

Executed (Python 3.14, `ruff` + `mypy --strict` clean): `call_cost`, `bounded_gather` and `embedding_cache_key` below, 2 tests. Cost numbers in examples are arithmetic on made-up prices, not real provider prices.

REMOVED from the previous version: a "per 1M tokens, as of 2025" price table that disagreed with the routing file's table and named retired model ids; a response cache keyed only on message text (shared answers across users and orgs); an embedding cache key without the model id; a context trimmer slicing `messages[-3:]` (can split a tool call from its result); a "temperature 0 enables caching" rule; an in-process `BudgetManager` dict that each replica counted separately and that returned `False` instead of a typed status.

## Model selection

| Question | Guidance |
|---|---|
| Routing/classification/extraction? | `fast` tier with structured output and a validator |
| Multi-step reasoning or tool planning? | `standard`; `deep` only where evals show a gain |
| Images/documents? | At least `standard` until capability evals say otherwise |
| Latency-bound and user-facing? | Measure TTFT and p95 per tier; stream from the model node |
| Which exact model id/price? | Config per environment; provider pricing pages with a "checked on" date (`agentic-llm-routing.md`) |

## Measure first

Compute cost from **measured usage**, not estimates. LangChain exposes `AIMessage.usage_metadata`: `input_tokens`, `output_tokens`, `total_tokens`, and optional `input_token_details` (`cache_read`, `cache_creation`, `audio`) and `output_token_details` (`reasoning`, `audio`).

```python
@dataclass(frozen=True)
class Price:
    """USD per 1M tokens, loaded from config keyed by exact model id (source page + checked-on date)."""
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal


def call_cost(model_id: str, usage: UsageMetadata, prices: dict[str, Price]) -> Decimal | None:
    """None = unknown (never another model's price, never 0)."""
    price = prices.get(model_id)
    if price is None:
        logger.warning("cost_unknown_model", model_id=model_id)
        return None
    details = usage.get("input_token_details", {})
    cache_read = details.get("cache_read", 0)
    cache_write = details.get("cache_creation", 0)
    uncached_in = usage["input_tokens"] - cache_read - cache_write
    # *_token_details are documented as a BREAKDOWN of the totals (langchain-core): reasoning is
    # inside output_tokens, cache reads inside input_tokens. Verify each integration once against
    # the provider's raw usage before trusting this.
    return (uncached_in * price.input + cache_read * price.cache_read
            + cache_write * price.cache_write + usage["output_tokens"] * price.output) / Decimal(1_000_000)
```

- Report reasoning tokens and cache-read tokens as separate series: they explain most "why did cost jump" questions.
- Use `Decimal` for money; aggregate in the metrics backend, not in process memory.
- Unknown model id → `None` and a warning metric; a dashboard showing $0 for an unpriced model hides spend.

## Prompt-side savings

1. **Shorter static prompts.** Every system token is paid on every call. Keep policy, tool descriptions and examples tight; measure with the model's token counter.
2. **Provider prompt caching.** Order content static → dynamic so the prefix is byte-stable; measure cache-read tokens before claiming savings (write cost and minimum lengths vary by provider). Details: `agentic-llm-routing.md` §Prompt caching.
3. **Bounded history.** Trim with `trim_messages(..., token_counter=count_tokens_approximately, start_on="human", end_on=("human", "tool"))` or `SummarizationMiddleware` (`agentic-memory-systems.md` §Context Trimming). Never slice the message list by index: a cut between an `AIMessage` with `tool_calls` and its `ToolMessage` makes the next call invalid.
4. **Lower reasoning level per call class** where evals allow (`llm-inference-and-model-routing.md` §3). Reasoning tokens are billed as output.

## Response and embedding caches

Generated-answer caches must be scoped (org + ACL scope + model + prompt version + tool set): `agentic-caching-patterns.md`. Never key on message text alone.

```python
def embedding_cache_key(model_id: str, dimensions: int, text: str) -> str:
    """Model id + dimensions in the key: a model change must never return old-space vectors."""
    return f"emb:{model_id}:{dimensions}:{hashlib.sha256(text.encode()).hexdigest()}"
```

Embeddings of identical text with the same model are tenant-independent, so this cache may be shared; record that decision. TTL by content churn, not a fixed 7 days.

## Architecture patterns

### Fewer calls, but not by merging decisions into free text

Combining "classify and answer" into one call saves a round trip only if the output stays structured (`with_structured_output` with `category` and `answer` fields). Parsing `Category: ...` out of free text trades cost for silent misroutes.

### Batch, with a concurrency cap

Grading N documents in one structured call is cheaper when they fit comfortably in context and the grader's quality holds on the batch (eval it). Otherwise fan out, but never unbounded:

```python
async def bounded_gather[T](jobs: Iterable[Callable[[], Awaitable[T]]], limit: int) -> list[T]:
    """Fan-out with a concurrency cap: avoids 429 bursts and spend spikes."""
    sem = asyncio.Semaphore(limit)

    async def run(job: Callable[[], Awaitable[T]]) -> T:
        async with sem:
            return await job()

    return list(await asyncio.gather(*(run(j) for j in jobs)))
```

Executed: 20 jobs with `limit=4` never had more than 4 in flight. Each job still charges the request's cumulative budget.

### Early termination by deterministic signals

Stop when a deterministic condition holds (evidence gate satisfied, validator passed, no new tool results for N steps), not when a model-reported `confidence_score` is high: self-reported confidence is not calibrated. Hard caps (`recursion_limit`, `ModelCallLimitMiddleware(exit_behavior="error")`) remain the backstop (`tool-execution-safety.md` §8).

### Cheapest adequate tier per step

Router/classifier on `fast`, answer on `standard`, `deep` only for eval-proven cases (`agentic-llm-routing.md`). Escalation is validator-driven, never a silent fallback to a weaker model on errors.

### Multimodal inputs

Cap images per request and actual bytes per item; charge image tokens to the budget (`llm-inference-and-model-routing.md` §10). One oversized upload can cost more than a day of text traffic.

## Budgets

| Scope | Where enforced | On exhaustion |
|---|---|---|
| Per request (calls, tokens, wall-clock) | In the run: `RunBudget` / call-limit middleware / `asyncio.timeout` | Typed status (`BUDGET_EXHAUSTED`, `ITERATION_LIMIT`, `TIMEOUT`); no partial side effects |
| Per principal / org per day | Shared atomic counter (Redis `INCRBYFLOAT` with TTL, or a DB row) checked before the run | `429`-style typed refusal with retry-after |
| Global | Provider console spend caps + alerts; gateway quota | Alert; degrade non-critical features first |

Per-process dictionaries are not budgets: each replica counts separately and restarts reset them. Provider-side caps and alerts are the hard stop; code budgets are defense in depth. Session-cost projections must model context growth per turn (input grows with history unless trimmed).

## Key Rules

| Rule | Standard |
|------|----------|
| Prices | Config keyed by exact model id; unknown → `None` + warning |
| Measurement | From `usage_metadata`, incl. cache-read and reasoning breakdowns |
| Caches | Scoped answer keys; embedding keys include model id + dimensions |
| History | Token-based trimming on message boundaries or summarization |
| Fan-out | Semaphore-bounded; charged to the request budget |
| Termination | Deterministic signals + hard caps; not model confidence |
| Budgets | Per request in the run; per principal/org in shared storage; provider caps as the hard stop |

---

## CAG — Cache Augmented Generation

**CAG** puts a fixed document set into the prompt once and relies on provider prompt caching for repeated queries, instead of retrieving per query. Use when the set is fixed, fits comfortably in the model's context, is **visible to every user who can call the agent**, and is queried repeatedly.

### CAG vs RAG decision

```
Document set
├── Contains anything not every caller may see? → RAG with ACL filters (CAG cannot filter per user)
├── Fits comfortably in context (measured with the model's token counter)?
│   ├── Queried repeatedly within the cache TTL? → CAG
│   └── Rarely queried? → Direct context, no caching
└── Too large or changes often → RAG
```

Trade-offs (verify for your provider and model): no retrieval step or chunking, but every call reads the full context (cached reads are cheaper, not free); a cache miss pays the full write; long-context answer quality can drop for facts in the middle of very long inputs, so eval it against RAG on your questions before choosing.

### CAG with LangChain (Anthropic-style cache breakpoints)

```python
def build_cag_messages(documents_context: str, question: str) -> list[BaseMessage]:
    """Static policy + static documents (cached prefix), then the varying question."""
    return [
        SystemMessage(content=[{"type": "text", "text": CAG_POLICY, "cache_control": {"type": "ephemeral"}}]),
        HumanMessage(content=[{"type": "text", "text": f"<documents>\n{documents_context}\n</documents>",
                               "cache_control": {"type": "ephemeral"}}]),
        HumanMessage(content=f"Question: {question}"),
    ]


DOCS_CONTEXT = load_documents(settings.cag_doc_paths)   # once at startup; rebuild on document change
llm = chat_model("standard")                             # model id from settings (agentic-llm-routing.md)
```

`CAG_POLICY` is static ("Answer only from the documents; otherwise return NOT_FOUND"). Content blocks must be a **list**; the previous version passed a dict to `SystemMessage(content=...)`. Cache TTL and pricing: provider docs.

### CAG with Gemini / ADK

Use Gemini explicit context caching (`google-genai` caches API) for large sets rather than pasting documents into the agent `instruction` (`gemini-api-dev` skill). ADK `instruction` strings support `{state_key}` templating, so raw document text containing braces can be misread as placeholders; supply static text through an instruction provider or the cache (`google-adk` skill). Model id from settings.

### Choosing at startup

Measure with the target model's token counter (`len(text) // 4` is only a rough guess and is wrong for many languages and code), compare against a configured ceiling well below the context limit, and fall back to RAG when the set is too large or not uniformly visible.

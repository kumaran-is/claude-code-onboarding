# Agentic AI Memory Systems

Canonical home for agent memory **implementation** (LangGraph / LangChain v1). Principles (memory is a liability; authority order canonical state > source documents > verified outcomes > derived memory > model inference; derived memory never authorizes) live in `ai-playbook/playbook.md` §2.6. Context-window trimming for a single call is also here; caching is in `agentic-caching-patterns.md`.

Executed on langchain 1.2.8 / langgraph 1.0.7 / langgraph-checkpoint-postgres 3.2.1 against PostgreSQL 16 (no live model): checkpointer lifecycle, Store namespaces, cross-user isolation, fail-closed recall, write quarantine, erasure, `trim_messages` behaviour.

## Memory Layer Overview

| Layer | Name | Scope | Implementation | Default |
|-------|------|-------|----------------|---------|
| 1 | Short-term (thread state) | one thread | Checkpointer: `AsyncPostgresSaver` (prod), `InMemorySaver` (tests) | Yes |
| 2 | Long-term (facts, preferences) | principal, cross-thread | LangGraph Store: `AsyncPostgresStore` namespaced by `(org_id, user_id)` | When a feature needs it |
| 3 | Episodic (what happened when) | principal | Store items or an event table with timestamps | When a feature needs it |
| 4-7 | Graph / procedural / affective / reflective | varies | Research patterns (bottom of file) | No |

Every layer is scoped by the **authenticated** principal, has a retention period, and is covered by erasure.

## Layer 1: Short-term Memory (Checkpointing)

`AsyncPostgresSaver.from_conn_string()` (and `PostgresSaver`, `AsyncPostgresStore`) is a **context manager**. The old pattern `saver = AsyncPostgresSaver.from_conn_string(uri); await saver.setup()` fails at startup: the returned object has no `setup` (executed). Enter it in the FastAPI lifespan and keep it open for the process lifetime: `agentic-templates-core.md` §Entry Point shows the canonical code (and the connection-pool variant).

```python
# tests only
from langgraph.checkpoint.memory import InMemorySaver
graph = build_support_agent(checkpointer=InMemorySaver())
```

Usage rules:
- The thread id in `config["configurable"]["thread_id"]` is server-derived and principal-scoped (`scoped_thread_id()` in `agentic-templates-core.md`). A raw client-supplied id lets anyone who knows it read or continue another user's conversation.
- Durable execution: a resumed run re-executes the interrupted node from its first line (executed: a counter before `interrupt()` reached 2). Nodes that cause side effects must be idempotent (`tool-execution-safety.md`).
- Checkpoints are personal data: give them a retention period and include them in erasure (delete by thread keys of the principal; `adelete_thread(thread_id)` exists on the saver).
- Multi-day or cross-service flows belong in a durable workflow engine, not a long-lived checkpoint (`workflow-orchestration-patterns`).

## Layer 2: Long-term Memory on the LangGraph Store

Use the Store API (`BaseStore`: `aput`, `aget`, `asearch`, `adelete`) instead of a hand-rolled vector-store wrapper. Pass it with `create_agent(..., store=store)` or `graph.compile(store=store)`; tools reach it through `runtime.store`.

**File:** `src/<service>/memory/long_term.py`

```python
import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from langgraph.store.base import BaseStore

MemoryKind = Literal["preference", "fact", "decision"]
_INSTRUCTION_LIKE = re.compile(
    r"\b(ignore (all|any|previous)|disregard|system prompt|you are now|act as|always respond)\b"
    r"|</?\s*memory\b"                                   # tries to close/open the prompt delimiter
    r"|^\s*(system|assistant|developer)\s*:",              # fake role line
    re.IGNORECASE | re.MULTILINE,
)


class ScopeMissingError(PermissionError):
    """Raised instead of ever running an unscoped memory search."""


@dataclass(frozen=True)
class MemoryScope:
    org_id: str   # from the verified principal / runtime context only
    user_id: str

    def namespace(self) -> tuple[str, ...]:
        if not (self.org_id and self.user_id):
            raise ScopeMissingError("memory access requires org_id and user_id")
        return ("memories", self.org_id, self.user_id)


@dataclass(frozen=True)
class MemoryCandidate:
    kind: MemoryKind
    key: str                              # stable slot: upsert, do not append duplicates
    value: str
    source_event_ids: tuple[str, ...]     # provenance
    author_role: Literal["user", "tool", "model"]


async def remember(store: BaseStore, scope: MemoryScope, c: MemoryCandidate, ttl_days: int = 180) -> str:
    """Write path = trust boundary. Returns 'stored' or 'quarantined'."""
    if c.author_role == "model":
        return "quarantined"   # model inference is never stored as fact without review
    if _INSTRUCTION_LIKE.search(c.value):
        return "quarantined"   # persistent-injection attempt (probabilistic signal: also log + count)
    now = datetime.now(UTC)
    await store.aput(scope.namespace(), f"{c.kind}:{c.key}", {
        "kind": c.kind, "value": c.value,   # PII-redacted before this point
        "source_event_ids": list(c.source_event_ids), "author_role": c.author_role,
        "status": "CURRENT", "valid_until": (now + timedelta(days=ttl_days)).isoformat(),
        "written_at": now.isoformat(),
    })
    return "stored"


async def recall(store: BaseStore, scope: MemoryScope, query: str, k: int = 5) -> list[dict[str, Any]]:
    """Fails closed without scope; never falls back to an unfiltered search."""
    items = await store.asearch(scope.namespace(), query=query, limit=k)
    now = datetime.now(UTC).isoformat()
    return [i.value for i in items if i.value.get("status") == "CURRENT" and i.value["valid_until"] > now]


def memory_block(memories: list[dict[str, Any]]) -> str:
    """Memories enter the prompt as delimited DATA in a user-role message, never a SystemMessage."""
    # escape < > & so a stored value can never close the delimiter, even if it slipped past the write filter
    lines = "\n".join(f"- [{m['kind']}] {html.escape(m['value'], quote=False)}" for m in memories)
    return f"<memory trust='derived' note='may be stale; canonical records win'>\n{lines}\n</memory>"


async def erase_principal(store: BaseStore, scope: MemoryScope) -> int:
    deleted = 0
    while items := await store.asearch(scope.namespace(), limit=100):
        for item in items:
            await store.adelete(item.namespace, item.key)
            deleted += 1
    return deleted
```

Executed (PostgreSQL store): a user-authored preference was stored and recalled; an instruction-like tool-sourced item, a tool value containing `</memory>` + a `SYSTEM:` line, and a `model`-authored "fact" were quarantined; a value with `</memory>` that bypassed the write filter rendered escaped (`&lt;/memory&gt;`), leaving exactly one closing tag; user B's recall of user A's text returned nothing; an empty `user_id` raised `ScopeMissingError`; erasure deleted the item and a second recall returned nothing.

- Semantic ranking: open the store with an index, e.g. `AsyncPostgresStore.from_conn_string(uri, index={"dims": 1536, "embed": embeddings, "fields": ["value"]})` (needs the `vector` extension). Without `index`, `query=` does not rank by similarity. The indexed variant was not executed here (no embedding model): verify on your stack.
- Retention: `from_conn_string(..., ttl={...})` accepts a `TTLConfig` in langgraph-checkpoint-postgres 3.2.1 (parameter verified, behaviour not exercised). Keep `valid_until` filtering in code either way.
- Using memory in a node:

```python
async def respond_node(state: AgentState, runtime: Runtime[RequestCtx]) -> dict[str, Any]:
    scope = MemoryScope(runtime.context.org_id, runtime.context.user_id)
    memories = await recall(runtime.store, scope, state["messages"][-1].text, k=3)
    prompt = [SystemMessage(STATIC_POLICY)]               # versioned, no interpolation
    if memories:
        prompt.append(HumanMessage(memory_block(memories)))
    response = await llm.ainvoke([*prompt, *state["messages"]])
    return {"messages": [response]}
```

WRONG (removed): `SystemMessage(content=f"Relevant memories:\n{memory_context}")` gives retrieved, possibly poisoned text system authority; `remember(response.content)` stores raw model output as fact; `recall(query)` without a filter searched every user's memories.

### Memory write pipeline

```
candidate (user turn / tool result / summary)
  -> extract typed fields (kind, key, value, source_event_ids, author_role, valid_until)
  -> redact PII (fail closed for data classes the store must not hold)
  -> reject/quarantine model-authored or instruction-like content; count quarantines
  -> upsert by (namespace, kind:key)  -- never append duplicates
```

### Freshness, invalidation and erasure

| Event | Action |
|---|---|
| Item past `valid_until` | Excluded from recall; refreshed only from a new source event |
| Correction / dispute / reopened record | Mark dependent items `SUPERSEDED` or `REVIEW_REQUIRED`; recompute aggregates (subtract, not only append) |
| Extraction prompt or model upgrade | Mark items written by the old version for rebuild (store the version on each item) |
| Erasure request | Delete by principal across checkpoints, store namespaces, vector memories, summaries, caches and eval copies; verify with a recall test |
| Memory unavailable / stale | Fall back to canonical data; never present memory as complete or authoritative |

## Layer 3: Episodic Memory

Store episodes in the same principal namespace with a timestamp, or in a table keyed by `(org_id, user_id, occurred_at)` when you need time-range queries. Apply the time filter in the query, not after a top-k vector search (post-filtering a top-k drops in-range episodes).

```python
async def record_episode(store: BaseStore, scope: MemoryScope, action: str, outcome: str) -> None:
    now = datetime.now(UTC)
    await store.aput((*scope.namespace(), "episodes"), now.isoformat(),
                     {"action": action, "outcome": outcome, "occurred_at": now.isoformat()})
```

## Context Trimming and Summarization (single call)

`trim_messages(..., token_counter=len)` counts **messages**, not tokens: `max_tokens=3` keeps three messages (executed). Use a token counter and keep tool-call/result pairs together.

```python
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

trimmed = trim_messages(
    messages,
    max_tokens=budget_tokens,
    strategy="last",
    token_counter=count_tokens_approximately,   # or the chat model itself for exact counts
    include_system=True,
    start_on="human",
    end_on=("human", "tool"),
)
```

Executed: with a system message, a long human turn, an AI tool call, its `ToolMessage`, an answer and a new question, the trimmed list starts with system + human, contains no `ToolMessage` without its `AIMessage` tool call, and stays within the budget. Slicing (`messages[-3:]`, `len(messages)//2`) can orphan a tool result, which providers reject.

For long threads, prefer the built-in middleware over hand-rolled summarize-half code:

```python
from langchain.agents.middleware import SummarizationMiddleware

agent = create_agent(model, tools, middleware=[
    SummarizationMiddleware(model=summary_model, trigger=("tokens", 6000), keep=("messages", 20)),
], checkpointer=checkpointer)
```

Constructor verified in langchain 1.2.8 (`trigger` accepts `("tokens"|"fraction"|"messages", n)`; the older `max_tokens_before_summary` / `messages_to_keep` are deprecated kwargs). A summary is a lossy derived artefact: it never outranks canonical records, and authority facts (scope, approvals, safety flags) stay in structured state injected each turn, not in text a summarizer may drop. `count_tokens_approximately` is an estimate; measure with the target model's counter before calls near the limit, and remember images/audio are not shrunk by text summarization.

## Advanced Layers (4-7) — Research Patterns

| Layer | Concept | Gate before building |
|---|---|---|
| 4 Temporal graph | Entities + relationships with validity intervals | Relationship traversal is the proven bottleneck; same principal scoping |
| 5 Procedural | Successful tool sequences per task type | Learned from verified outcomes only, never from model self-assessment |
| 6 Affective | Sentiment trend per user | Documented consent, retention and purpose decision first; many products should not build it |
| 7 Reflective | Self-evaluation summaries | Same-model reflection is not verification; evals decide what changes |

## Parallel Multi-Layer Retrieval

Independent layers can be fetched concurrently. Each failure or timeout becomes **explicit degraded state** (logged, flagged in state, visible in the trace), never a silent `None`/`[]`.

```python
async def _layer(name: str, coro: Awaitable[Any], timeout_s: float) -> tuple[str, Any, str | None]:
    try:
        async with asyncio.timeout(timeout_s):
            return name, await coro, None
    except TimeoutError:
        logger.warning("memory_layer_timeout", layer=name)
        return name, None, "TIMEOUT"
    except Exception as exc:  # noqa: BLE001 - one layer must not fail the request
        log_exception(logger, "memory_layer_failed", exc, layer=name)
        return name, None, "ERROR"


async def memory_retrieval_node(state: AgentState, runtime: Runtime[RequestCtx]) -> dict[str, Any]:
    scope = MemoryScope(runtime.context.org_id, runtime.context.user_id)
    scope.namespace()                       # missing scope fails the request here, not as "degraded"
    query = state["messages"][-1].text
    results = await asyncio.gather(
        _layer("long_term", recall(runtime.store, scope, query), settings.memory_timeout_s),
        _layer("episodes", recall_episodes(runtime.store, scope, query), settings.memory_timeout_s),
    )
    degraded = {name: err for name, _, err in results if err}
    return {"memory": {name: value for name, value, err in results if not err},
            "memory_degraded": degraded}        # surfaced in traces and, if relevant, in the answer
```

- `_layer` never raises, so `gather` needs no `return_exceptions`. Because `recall` raises `ScopeMissingError` inside `_layer`, a missing scope would only degrade: build and validate the scope first (`scope.namespace()` before `gather`) so it fails the request instead.
- Measure before parallelizing; a single layer needs no `gather`.

## Memory Selection Guide

| Use Case | Layers | Notes |
|----------|--------|-------|
| Simple chatbot | 1 | Retention on checkpoints |
| Support assistant | 1 + 2 | Preferences only; facts come from canonical records |
| Personal assistant | 1 + 2 + 3 | Consent + erasure flows required |
| Knowledge work over documents | 1 + RAG | Documents are data read via authorized retrieval, not "memory" |

## Tests Every Memory Feature Needs

1. Cross-principal isolation: user B's recall of user A's distinctive text returns 0 items (also counts, snippets, cached results).
2. Missing scope raises; no unscoped search path exists.
3. Poisoned write (instruction-like text, model-authored fact) is quarantined.
4. Erasure removes every surface for the principal.
5. Trimming never orphans a `ToolMessage`.
6. Degraded memory is flagged, not silently empty.

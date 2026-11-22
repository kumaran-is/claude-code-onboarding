# Agentic AI Caching Patterns

Tiered caching for agent answers and tool results. Scoping rules are canonical in `llm-inference-and-model-routing.md` §8; this file is the implementation. Provider prompt-prefix caching is in `agentic-llm-routing.md` §Prompt caching.

The code below was executed (Python 3.14, `ruff` + `mypy --strict` clean) with in-memory stand-ins for the shared store and the semantic tier. Latencies and hit rates depend entirely on your traffic: measure them; this file quotes none.

REMOVED from the previous version (verified wrong or unverifiable): a shared tier whose key **intentionally excluded `user_id`** "for cross-user sharing", a 0.85 similarity tier with no tenant scope, safety bypass implemented in only two of three tiers, fuzzy (semantic) hits promoted into the exact-match tiers under the new query's key, keys without model id or prompt version, and line-number "sources" pointing to files of another project that do not exist in this toolkit.

## Rules

| # | Rule |
|---|---|
| 1 | Generated answers are never shared across orgs or permission scopes. The key covers org + ACL scope + model id + prompt version + tool/flag set + **corpus version** + normalized input. |
| 2 | Freshness- and safety-critical intents bypass **every** tier (read and write). Decide by classified intent, not a keyword list. |
| 3 | The semantic tier is opt-in for public, tenant-independent FAQ-style intents only, namespaced by the same scope prefix, with a measured false-hit rate. Negation and entity flips ("cancel my order" / "don't cancel my order") score above typical thresholds. |
| 4 | A semantic hit is returned as-is and **never written back** under the new query's exact key (that would turn one fuzzy match into a permanent exact answer). |
| 5 | Exact → exact backfill (shared store → local LRU, same key) is safe. |
| 6 | Bumping the model, prompt or corpus version changes the key prefix: old entries become unreachable and expire. No manual flush needed. When an answer may draw on retrieval or on records a tool reads, `corpus_version` is the `index_version` of those corpora (`rag-architect/references/rag-operations-guide.md` §1 Caching Strategies): an ingest, update or **erasure** bumps it, so a cached answer quoting a deleted document is no longer served. Use the constant `"none"` only for answers that use no retrieval and no stored records. |
| 7 | Tool-result caches key on tool name + scope + canonical args, only for read-only tools, with TTLs shorter than the data's change rate. Never cache write tools. |

## Scoped keys

```python
@dataclass(frozen=True)
class CacheScope:
    org_id: str
    acl_scope: str        # role / permission-set hash: answers differ by what the caller may see
    model_id: str
    prompt_version: str
    tool_set: str         # flags / tool list version that change the answer
    corpus_version: str   # index_version of every corpus the answer may draw on; "none" if no retrieval

    def prefix(self) -> str:
        fields = (self.org_id, self.acl_scope, self.model_id, self.prompt_version, self.tool_set,
                  self.corpus_version)
        if not all(fields):
            raise ValueError("cache scope fields must be non-empty")
        return hashlib.sha256("\x00".join(fields).encode()).hexdigest()[:32]


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def exact_key(scope: CacheScope, query: str) -> str:
    return f"ans:{scope.prefix()}:{hashlib.sha256(normalize(query).encode()).hexdigest()}"
```

`acl_scope` matters even inside one org: two users with different permissions asking the same question may be entitled to different answers. When answers depend on the individual (their records, their history), put `user_id` in `acl_scope`.

## Tiered lookup

```python
Intent = Literal["public_faq", "account_specific", "freshness_critical", "safety_critical"]


class AnswerCache:
    def __init__(self, local: LocalLRU, shared: SharedStore, semantic: SemanticTier | None, ttl_s: int) -> None:
        self.local, self.shared, self.semantic, self.ttl_s = local, shared, semantic, ttl_s

    async def get_or_compute(self, scope: CacheScope, intent: Intent, query: str,
                             compute: Callable[[], Awaitable[str]]) -> tuple[str, Tier]:
        if intent in ("freshness_critical", "safety_critical"):
            return await compute(), "bypass"                    # bypass EVERY tier
        key = exact_key(scope, query)
        if (hit := self.local.get(key)) is not None:
            return hit, "local"
        if (hit := await self.shared.get(key)) is not None:
            self.local.set(key, hit)                            # exact -> exact backfill
            return hit, "shared"
        semantic_ok = self.semantic is not None and intent == "public_faq"
        if semantic_ok and self.semantic and (hit := await self.semantic.lookup(scope.prefix(), query)) is not None:
            return hit, "semantic"                              # never promoted to an exact key
        answer = await compute()
        self.local.set(key, answer)
        await self.shared.set(key, answer, self.ttl_s)
        if semantic_ok and self.semantic:
            await self.semantic.store(scope.prefix(), query, answer)
        return answer, "miss"
```

`LocalLRU` is a bounded `OrderedDict` with per-entry expiry; `SharedStore` is a `get`/`set(ttl)` protocol (Redis or similar); `SemanticTier` is `lookup(namespace, query)` / `store(namespace, query, answer)` over a vector index filtered by `namespace`.

Executed assertions: whitespace/case variants hit the local tier; the same query in another org missed; a prompt-version bump missed; an `index_version` (corpus) bump after an erasure missed; a safety intent bypassed all tiers; a semantic hit for a negated FAQ was returned but not written under its exact key; account-specific intents never consulted the semantic tier; an empty scope field raised.

## Intent classification for bypass

Use the router's classified intent (deterministic policy first, `agentic-llm-routing.md`), not substring keywords: keyword lists miss paraphrases and other languages and over-trigger on unrelated words. When the classifier is unavailable, treat the request as `freshness_critical` (bypass) rather than cache it.

## Tool-result caching

```python
def tool_cache_key(tool_name: str, scope: CacheScope, args: Mapping[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return f"tool:{tool_name}:{scope.prefix()}:{hashlib.sha256(canonical.encode()).hexdigest()}"
```

- Read-only tools only; never side-effecting ones (`tool-execution-safety.md` §6 handles replay for writes).
- Tools that serve freshness- or safety-critical data are never cached.
- Embedding caches are different: vectors of `(text, embedding_model_id)` are tenant-independent and may be shared if you record that decision; the model id must be in the key or a re-embedding migration mixes vector spaces.

## Metrics

Count per tier: `cache_requests_total{cache,tier}` with `tier` in {local, shared, semantic, miss, bypass}; latency histogram per tier; semantic false-hit rate from sampled human/eval review. Labels stay bounded: never org or user ids as metric labels (put them in traces). Metric conventions: `deployment-ci-cd/reference/ai-observability.md`.

## Tests every cache needs

1. Same query, two orgs (and two ACL scopes) → different keys, no shared hit.
2. Model, prompt or corpus (`index_version`) version bump → miss; an erasure bumps the corpus version.
3. Safety/freshness intent → bypass on read and write.
4. Semantic hit is not written back under the exact key; non-FAQ intents never use the semantic tier.
5. Negation pair evaluated against the semantic threshold before enabling the tier.
6. Erasure: keys are opaque hashes, so a principal's entries cannot be looked up by principal. Either bump `corpus_version` (all answers over that corpus miss and expire) and assert the old answer is no longer served, or keep a secondary index `principal → keys` (Redis set with the same TTL) and assert it deletes every key. Without one of the two, document the TTL as the erasure bound.

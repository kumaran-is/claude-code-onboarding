# Query Transformation Guide

Reference for query rewriting, expansion, HyDE, and splitting strategies. Apply when the default single-query retrieval is insufficient (§3 of the production RAG pipeline).

These techniques are **v2 features** — ship the default stack first, measure your top failure modes, then apply only what fixes a measured problem.

---

## 1. When to Apply Query Transformation

| Symptom | Transformation to Apply |
|---|---|
| Follow-up questions ("tell me more about that") retrieve wrong chunks | Query rewriting |
| Domain terminology mismatch (abbreviations, synonyms) | Query expansion |
| Complex multi-part questions get incomplete answers | Query splitting |
| Semantically rich questions miss conceptually related chunks | Multi-query retrieval |
| Dense prose corpus, semantic similarity retrieval underperforms | HyDE |
| Exact facts, numbers, names, legal/contractual content | **No transformation — raw query only** |

---

## 2. Query Rewriting (§3.1)

Reformulates conversational follow-ups into standalone queries using conversation history.

### When to Apply
- Multi-turn chat interfaces where user asks "tell me more" or uses pronouns ("it", "that", "those")
- Queries that refer to entities established in prior turns

### Rewrite Prompt Template
```
You are a query reformulator. Given the conversation history and the latest user message,
rewrite the user message as a standalone, self-contained search query.

Rules:
- Resolve pronouns and references using conversation history
- Keep the query concise (one sentence)
- Do not add information not implied by the conversation
- If the query is already standalone, return it unchanged

Conversation history:
{conversation_history}

Latest user message: {user_message}

Standalone query:
```

### Decision Logic
```python
def should_rewrite(query: str, conversation_history: list) -> bool:
    if not conversation_history:
        return False  # first turn — no context to resolve
    pronouns = {"it", "this", "that", "these", "those", "they", "them", "its"}
    tokens = set(query.lower().split())
    return bool(tokens & pronouns) or len(query.split()) < 5
```

---

## 3. Query Expansion (§3.2)

Adds synonyms and alternate phrasings to catch vocabulary mismatches between user language and document language.

### When to Apply
- Corpus has domain-specific vocabulary, abbreviations, or jargon
- Users often use informal terms; documents use formal or technical terms
- Measured recall gap between dense and BM25 retrieval (BM25 missing exact terms)

### Domain Synonym Table Pattern
Maintain a lookup table per corpus — do not hardcode in prompts:
```python
DOMAIN_SYNONYMS: dict[str, list[str]] = {
    "machine learning": ["ML", "model training", "neural network", "deep learning"],
    "authentication": ["auth", "login", "sign in", "SSO", "identity"],
    "deployment": ["release", "ship", "rollout", "go live", "publish"],
    # Add domain terms as measured recall gaps reveal them
}

def expand_query(query: str, synonyms: dict) -> list[str]:
    expanded = [query]
    for canonical, variants in synonyms.items():
        for variant in variants:
            if variant.lower() in query.lower():
                expanded.append(query.replace(variant, canonical, 1))
    return list(set(expanded))
```

### Application Pattern
```python
# Run all expanded variants; merge results with RRF
all_results = []
for variant in expand_query(query, DOMAIN_SYNONYMS)[:MAX_SUBQUERIES]:
    results = await secure_retrieve(variant, ctx)   # same scoped entry as the original query
    all_results.append(results)
final = rrf_merge(all_results, k=60)
```

### Cost Note
Each expanded variant is an additional embedding + retrieval call. Apply only when domain vocabulary mismatch is measured, not assumed.

---

## 4. Multi-Query Retrieval (§3.3)

Generates N diverse phrasings of the same question; retrieves independently; merges with RRF.

### When to Apply
- Query is ambiguous — could be interpreted multiple ways
- Dense retrieval consistently misses semantically equivalent chunks
- Corpus is large with diverse terminology

### Implementation
```python
MULTI_QUERY_PROMPT = """
Generate {n} different ways to ask the following question. 
Each variant should use different vocabulary but seek the same information.
Return one variant per line, no numbering.

Question: {query}
"""

async def multi_query_retrieve(query: str, ctx: AuthContext, n: int = 3) -> list[Chunk]:
    variants = parse_subqueries(await llm.generate(MULTI_QUERY_PROMPT.format(n=n, query=query)), query)
    async with asyncio.timeout(2.0):
        all_results = await asyncio.gather(*(secure_retrieve(v, ctx) for v in [query, *variants]))
    return rrf_merge(all_results, k=60)          # cap + scope rules: see §5
```

### Cost Tradeoff
- N=3 variants → 4 embedding calls + 4 retrieval calls (including original)
- Latency: adds ~100–300ms depending on LLM speed
- Only justified when single-query recall is measured to be insufficient

---

## 5. Query Splitting / Decomposition (§3.4)

Detects multi-topic questions and answers each part independently.

### When to Apply
- User asks compound questions: "What is X and how does Y compare to Z?"
- Single retrieval consistently only answers part of the question
- Generation model notes it can only partially answer

### Detection + Split Pattern
```python
SPLIT_PROMPT = """
Does this question contain multiple distinct sub-questions that require separate lookups?
If yes, list each sub-question on its own line.
If no, return the original question unchanged.

Question: {query}
"""

MAX_SUBQUERIES = 3
MAX_RERANK_CANDIDATES = 40

def parse_subqueries(raw: str, original: str) -> list[str]:
    """Strict parse of model output: non-empty lines, de-duplicated, capped; else the original."""
    seen: dict[str, None] = {}
    for line in raw.splitlines():
        q = line.strip().lstrip("-*0123456789. ").strip()
        if q and len(q) <= 500:
            seen.setdefault(q, None)
    return list(seen)[:MAX_SUBQUERIES] or [original]

async def split_and_retrieve(query: str, ctx: AuthContext, deadline_s: float = 2.0) -> list[Chunk]:
    subs = parse_subqueries(await llm.generate(SPLIT_PROMPT.format(query=query)), query)
    async with asyncio.timeout(deadline_s):                      # one deadline for the fan-out
        results = await asyncio.gather(*(secure_retrieve(s, ctx) for s in subs))  # same entry, same auth ctx
    unique = list({c.id: c for c in chain.from_iterable(results)}.values())        # dedupe by id
    return await rerank(query, unique[:MAX_RERANK_CANDIDATES])   # rerank on the ORIGINAL query
```

Rules (apply to every derived query in this guide — rewrites, expansions, multi-query variants, HyDE and hops):
- Derived queries go through the SAME scoped entry (`secure_retrieve(q, ctx)`, `rag-security-reviewer` §2) with the caller's auth context — never a direct store call and never a tenant taken from model output.
- The cap is enforced in code after parsing; the prompt asking for "≤ 3" is not a control.
- Sub-queries run concurrently under one deadline; reranking uses the original question.
- Verified with a scripted fake model: 10 model-proposed sub-queries → 3 retrievals, all with the caller's `ctx`; rerank saw only the original query; a slow retriever raises `TimeoutError` at the deadline (3 pytest cases, `ruff` + `mypy --strict` clean).

### Limit Decomposition Depth
- Maximum 3 sub-queries per question — deeper splits fragment context and hurt synthesis
- If split produces > 3 sub-queries, treat as a summarization request instead

### 5b. Multi-Hop Decomposition (sequential, not parallel)
Splitting assumes independent parts. Multi-hop questions ("Which plan does the customer who filed case X use, and what is its refund window?") need hop N's query to depend on hop N-1's **grounded** answer:
- Bound hops in code (≤ 3); each hop retrieves through `secure_retrieve` with the same `ctx`.
- Each hop's intermediate answer must pass citation validation (`rag-response-contract.md` §10) before it seeds the next query; keep per-hop citations in the final answer.
- If any hop is unsupported, abstain on the whole question rather than chaining a guess.
- Facts that live in a database (who owns what, status, counts) are a SQL/tool hop, not a retrieval hop.

---

## 6. HyDE — Hypothetical Document Embeddings (§3.5)

Generates a hypothetical document that would answer the query; uses its embedding for retrieval instead of the query embedding.

### When HyDE Helps
- Dense prose corpora where query-document semantic gap is large
- Questions are short but target long explanatory passages
- Users ask in different vocabulary than documents use
- Domain: knowledge bases, technical documentation, policy explanations

### When HyDE Hurts (Critical Rule)
**Never apply HyDE when exact accuracy is required:**
- Factual lookups (specific dates, amounts, names, identifiers)
- Legal or contractual content (exact clause wording matters)
- High-stakes answers where hallucination in the hypothetical = wrong retrieval
- Structured data queries (fees, calculations, thresholds)

The hypothetical document is LLM-generated fiction — any hallucination in it biases retrieval toward wrong chunks.

### HyDE Decision Tree
```
Is the query seeking exact facts, numbers, names, or legal text?
  YES → Skip HyDE. Use raw query embedding.

Is the corpus dense prose with semantic vocabulary richness?
  NO  → Skip HyDE. Gain is minimal on keyword-rich corpora.

Does the query describe a concept rather than name a thing?
  YES → HyDE may help. Apply and measure against golden set.
  NO  → Skip HyDE.

Does the answer require precision more than recall?
  YES → Skip HyDE. Prioritize exact retrieval.
  NO  → Apply HyDE.
```

### Implementation
```python
HYDE_PROMPT = """
Write a short passage (2–3 sentences) that directly answers this question.
Write as if you are an expert summarizing relevant information.
Do not add caveats or disclaimers.

Question: {query}
"""

async def hyde_retrieve(query: str, ctx: AuthContext, top_k: int = 50) -> list[Chunk]:
    hypothetical_doc = await llm.generate(HYDE_PROMPT.format(query=query))
    # Embed the hypothetical document, not the query
    hypo_embedding = await embed(hypothetical_doc, task_type="RETRIEVAL_DOCUMENT")
    candidates = await secure_vector_search(hypo_embedding, ctx, limit=top_k)  # same scope as §5
    return await rerank(query, candidates)   # rerank on the ORIGINAL query, never the hypothetical text
```

---

## 7. Query Transformation Decision Table

| Query Type | Rewrite | Expand | Multi-Query | Splitting | HyDE |
|---|---|---|---|---|---|
| Factual lookup (exact value) | If follow-up | No | No | No | **No** |
| Policy / procedure question | If follow-up | If domain vocab | Optional | If compound | Optional |
| Comparison | No | No | Yes (one per entity) | Yes | No |
| Summarization | No | No | No | No | Yes |
| Multi-hop | No | No | Yes | Yes | No |
| Troubleshooting | If follow-up | Yes (symptom synonyms) | Yes | If multi-symptom | No |
| Personalized | No | No | No | No | No |
| Structured record lookup | No | No | No | No | **No** |

### Rule of Thumb
- Start with no transformation (default stack)
- Measure recall@5 on golden set by query type
- Apply transformation only for query types where measured recall < target
- Re-measure after applying; roll back if no improvement

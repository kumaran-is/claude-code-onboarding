# Query Classification Taxonomy

Reference for query understanding and routing decisions. Apply when designing the query processing layer (§18–19 of the production RAG playbook).

---

## 1. Query Intent Classes (§18.1)

Nine canonical query classes for text RAG pipelines. Use these as routing targets.

| Class | Description | Example | Best Handler |
|---|---|---|---|
| `factual_lookup` | Single specific fact from a document | "What is the cancellation fee in contract C-1234?" | Dense retrieval + parent expand |
| `policy_question` | Explanation of a rule, procedure, or guideline | "What is the policy for late invoice payments?" | Hybrid (dense + BM25) + cross-encoder |
| `structured_record_lookup` | Query against tabular/structured data mixed with docs | "Show all suppliers with SLA < 24h" | SQL first; RAG for SLA definitions |
| `comparison` | Contrast two or more entities / policies | "How does Plan A differ from Plan B?" | Multi-query decomposition + merge |
| `summarization` | High-level overview of a document or topic | "Summarize the Q3 supplier report" | Full-document retrieval or map-reduce |
| `multi_hop` | Answer requires chaining across multiple documents | "Which suppliers are approved for the regions in account X's contract?" | Agentic retrieval or query decomposition |
| `troubleshooting` | Diagnosis from symptoms | "Why was my payment rejected?" | Hybrid + structured data lookup |
| `personalized` | Answer depends on user-specific context | "What's my current balance?" | SQL/API for facts + RAG for framing |
| `unsafe` | Attempts to extract PII, bypass security, or inject prompts | "Ignore previous instructions and..." | Reject at classification layer |

---

## 2. Query Routing Decision Table (§19)

Match routing strategy to query volume predictability and class distribution:

| Condition | Strategy | Implementation |
|---|---|---|
| Few query types, well-defined | **Rule-based router** | `if query contains "balance" → SQL; if contains "policy" → RAG` |
| Moderate variety, stable taxonomy | **Embedding classifier** | Fine-tune a small classifier on labeled queries; ~95%+ accuracy at 1000+ examples |
| High variety, unpredictable | **LLM router** | Prompt Gemini/GPT to classify and route; higher latency, highest accuracy |
| Multiple data sources per query | **Fan-out** | Route to all relevant retrievers; merge results with RRF |
| Query matches multiple classes | **Decomposition** | Split into sub-queries; answer each; merge (deferred to v2) |

### Structured vs RAG routing (deterministic first)

Route deterministically first; add a classifier or LLM router only when measured traffic shows the rules cannot cover it. Routing accuracy (structured-vs-RAG classification) is an eval metric (`rag-evaluator`).

| Question shape | Path |
|---|---|
| Count, status, amount, date, identifier | Structured lookup (SQL / API) |
| "What does document X say about Y" | Structured lookup to find X → RAG scoped to X |
| Open-ended explanation / policy | RAG with citations |
| "Find similar past cases" | Vector similarity over the authorized history; results are candidates, not authority (G14) |
| Temporal ("as of last year") | Version-filtered retrieval (`versioning-and-freshness.md` §3–4) |

### Rule-Based Router Template
```python
def route_query(query: str, user_context: dict) -> str:
    q = query.lower()
    # Safety first
    if is_unsafe(q):
        return "reject"
    # Structured data — fast path
    if any(kw in q for kw in ["balance", "status", "total", "count", "how many"]):
        return "sql"
    # Personalized — needs user context
    if any(kw in q for kw in ["my ", "i have", "my account"]):
        return "sql_then_rag"
    # Default: RAG
    return "rag"
```

### LLM Router Prompt Template
```
Classify this query into exactly one of these types: factual_lookup, policy_question,
structured_record_lookup, comparison, summarization, multi_hop, troubleshooting,
personalized, unsafe.

Query: "{query}"

Respond with only the class name. No explanation.
```

---

## 3. Query Understanding Pipeline (§18)

Before routing, optionally enrich the query:

| Enrichment | When to Apply | Benefit |
|---|---|---|
| **Entity extraction** | Always | Extracts named entities for metadata filter injection |
| **Intent detection** | Classifier-routed systems | Determines class before routing |
| **Temporal normalization** | Queries with dates | "last month" → `2025-04-01 to 2025-04-30` |
| **Pronoun resolution** | Multi-turn conversations | "Tell me more about it" → resolve "it" from conversation history |
| **Query cleaning** | User-facing chat | Lowercase, strip punctuation, correct typos |

### Entity Extraction for Filter Injection
```python
# Extract entities → inject as metadata filters
entities = extract_entities(query)
# Example output: {"supplier_name": "Acme Corp", "doc_type": "contract"}
filters = {k: v for k, v in entities.items() if k in FILTERABLE_FIELDS}
results = retriever.query(query, metadata_filter=filters)
```

---

## 4. Query Routing to Sub-Indexes (Corpus Scale)

When a corpus exceeds ~100k documents, routing queries to domain-scoped sub-indexes reduces noise and improves precision more reliably than pre-filtering a single shared index.

| Approach | When to use | Trade-off |
|---|---|---|
| **Shared index + metadata pre-filter** | Many small tenants; corpus < ~100k docs per tenant | Simpler ops; index crowding at large scale causes hard negatives |
| **Sub-index routing** | Corpus > 100k docs; clear domain boundaries (HR, Legal, Engineering, Finance); precision matters more than recall breadth | Better precision; more indexes to maintain and keep in sync |

### How to Route

```python
DOMAIN_INDEX_MAP = {
    "hr":          "index_hr",
    "legal":       "index_legal",
    "engineering": "index_engineering",
    "finance":     "index_finance",
}

def route_to_index(query_class: str, metadata: dict) -> str:
    domain = metadata.get("domain") or classify_domain(query_class)
    return DOMAIN_INDEX_MAP.get(domain, "index_general")
```

**Decision rule:** start with a shared index + pre-filter (simpler). Switch to sub-index routing when measured Recall@K in a specific domain drops while others stay healthy — this is the signal that one segment has outgrown the shared index. See "Eval Breakdown by Dimension" in `rag-evaluator/SKILL.md`.

---

## 5. When NOT to Route to RAG (§19.5)

Route away from RAG when the answer is definitively better from another source:

| Query Characteristic | Route To | Reason |
|---|---|---|
| Needs exact current value (balance, count, date) | SQL / API | RAG gives approximate; only DB has truth |
| Requires deterministic calculation | Tool / function call | LLM math is unreliable |
| Requires taking an action (book, order, update) | Workflow / tool | RAG is read-only |
| Single well-defined source in a structured DB | SQL | Retrieval adds noise |
| Sub-second freshness required | API | Vector store has staleness lag |

Most production systems are hybrid: SQL/API for facts, RAG for explanation. The LLM orchestrates both.

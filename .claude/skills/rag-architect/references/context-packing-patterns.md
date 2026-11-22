# Context Packing Patterns

Reference for assembling the final context window from ranked retrieval results, and for structuring the LLM answer contract (§31–32 of the production RAG playbook).

---

## 1. Context Packing Pipeline

After reranking, you have 50–100 candidate chunks. Packing decides which chunks enter the generation prompt and in what order.

```
Reranked top-N chunks
    ↓
[1] Hard filter: remove low-score chunks (below abstention threshold)
    ↓
[2] Diversity filter: remove near-duplicates at packing time (cosine > 0.92 — a lower, more aggressive query-time threshold than corpus dedup in `rag-operations-guide.md` §9)
    ↓
[3] Parent/neighbor expansion: swap children for parents or add adjacent chunks
    ↓
[4] Token budget enforcement: trim to model context limit
    ↓
[5] Citation anchor injection: tag each chunk with [source_id] for citations
    ↓
[6] Recency + authority re-order: surface fresher and higher-authority chunks
    ↓
Final packed context → generation prompt
```

---

## 2. Eight Packing Techniques (§31)

### 2.1 Top-K Selection
Select top K chunks by reranker score. Simple, reliable, default.
- K=5 for most production systems (balances quality and latency)
- Increase K only when answer requires synthesis across many sources

### 2.2 Diversity / MMR (Maximal Marginal Relevance)
Remove redundant chunks; prefer diverse coverage.
```python
def mmr_select(chunks: list, query_emb, k=5, lambda_=0.5):
    selected = []
    while len(selected) < k and chunks:
        # Balance relevance to query vs dissimilarity to already-selected
        scores = [
            lambda_ * cosine(c.embedding, query_emb)
            - (1 - lambda_) * max(cosine(c.embedding, s.embedding) for s in selected or [c])
            for c in chunks
        ]
        best = chunks[scores.index(max(scores))]
        selected.append(best)
        chunks.remove(best)
    return selected
```
- Use when top-K keeps returning near-duplicate chunks (same paragraph, slightly different wording)
- `lambda_=0.7` favors relevance; `lambda_=0.3` favors diversity

### 2.3 Parent Expansion
If a child chunk matched, include its parent instead (or in addition).
```python
for chunk in top_chunks:
    if chunk.parent_chunk_id and should_expand(chunk):
        parent = fetch_chunk(chunk.parent_chunk_id)
        context_chunks.append(parent)
    else:
        context_chunks.append(chunk)
```
- Expand when: question needs context around the matched sentence
- Don't expand when: parent would exceed token budget or adds irrelevant content

### 2.4 Neighbor Expansion
Include adjacent chunks (chunk_index ± 1) from the same document.
- Use when parent-child is not set up but surrounding context helps
- Risk: can dilute relevance; apply only when reranker score is high

### 2.5 Citation Anchor Injection
Tag each chunk with a citation marker before inserting into prompt.
```python
context_parts = []
for i, chunk in enumerate(packed_chunks):
    context_parts.append(f"[{i+1}] {chunk.text}\n(Source: {chunk.metadata['source_uri']})")
context = "\n\n".join(context_parts)
```
- Generation prompt must instruct the model to cite using `[N]` inline
- Required for citation quality scoring

### 2.6 Token Budget Enforcement
Never exceed the model's context window. Calculate before sending.
```python
MAX_CONTEXT_TOKENS = 8000  # reserve budget for prompt + response
current_tokens = 0
final_chunks = []
for chunk in ranked_chunks:
    chunk_tokens = count_tokens(chunk.text)
    if current_tokens + chunk_tokens > MAX_CONTEXT_TOKENS:
        break
    final_chunks.append(chunk)
    current_tokens += chunk_tokens
```
- Set `MAX_CONTEXT_TOKENS` based on: model limit − prompt template tokens − expected response tokens
- Prefer fewer high-quality chunks over many low-quality ones

### 2.6a Extractive Compression (after rerank)
When the budget is tight, select whole sentences from each reranked chunk (by similarity to the original query) until the budget is met, keeping each sentence's offsets. The cited text stays verbatim, so citation validation and excerpt return still resolve. Never abstractively summarize evidence that will be cited — the model would then cite text no source contains.

### 2.7 Recency Bias
For time-sensitive corpora, surface fresher chunks when scores are close.
```python
def recency_adjusted_score(chunk, base_score, decay_days=90):
    age_days = (datetime.now() - chunk.metadata["updated_at"]).days
    decay = max(0, 1 - age_days / decay_days)
    return base_score * (1 + 0.1 * decay)  # 10% max boost for freshest content
```
- Only apply for corpora where recency matters (news, policies, pricing)
- Don't apply for historical or archival corpora

### 2.8 Authority Signals
Boost chunks from authoritative sources (official docs, signed contracts over community posts).
```python
AUTHORITY_SCORES = {"official": 1.2, "verified": 1.1, "community": 0.9}
adjusted = base_score * AUTHORITY_SCORES.get(chunk.metadata.get("source_type", "community"), 1.0)
```
- Requires `source_type` metadata at ingestion
- Use sparingly — authority boost can suppress newer accurate content

### 2.9 Verbatim Excerpt Return
For legal, contractual, or policy answers where exact wording is required, return the verbatim source text alongside the generated answer.
```python
def build_verbatim_context(chunks: list, query_type: str) -> dict:
    if query_type in ("factual_lookup", "policy_question", "structured_record_lookup"):
        # Include verbatim excerpts for high-stakes query types
        excerpts = [
            {
                "text": chunk.text,
                "source_uri": chunk.metadata["source_uri"],
                "version": chunk.metadata.get("effective_from"),
                "tenant_id": chunk.metadata["tenant_id"],
            }
            for chunk in chunks[:3]  # top 3 most relevant
        ]
        return {"packed_context": pack_context(chunks), "verbatim_excerpts": excerpts}
    return {"packed_context": pack_context(chunks), "verbatim_excerpts": []}
```
Include in the generation prompt: "Where exact wording is critical, quote the source verbatim and mark with quotation marks."

---

## 3. Structured Answer Contract (§32.1)

The generation prompt should instruct the model to return this JSON structure. Enables downstream citation quality checks, abstention tracking, and hallucination detection.

```json
{
  "answer": "string — the grounded answer in plain language",
  "confidence": "high | medium | low",
  "abstained": false,
  "abstention_reason": null,
  "citations": [
    {
      "source_id": 1,
      "source_uri": "https://docs.example.com/policy-v3.pdf",
      "quote": "exact supporting quote from context",
      "supports_claim": "the specific claim this citation supports"
    }
  ],
  "unsupported_claims": [
    "Any statement in the answer not backed by retrieved context"
  ],
  "follow_up_suggestions": [
    "What is the exception process for this policy?",
    "Can this requirement be waived under specific circumstances?"
  ]
}
```

### Key Fields

| Field | Purpose | Validation |
|---|---|---|
| `answer` | Final user-facing response | Must only contain claims present in context |
| `confidence` | Self-assessed confidence level | Used for UX affordances (show "I'm not sure" banner) |
| `abstained` | True if model refused to answer | Log all abstentions for quality review |
| `abstention_reason` | Why the model abstained | Enables triage: missing data vs low confidence vs unsafe |
| `citations[].supports_claim` | Per-citation claim mapping | Enables per-claim citation quality scoring |
| `unsupported_claims` | Statements without context backing | Review these for hallucination |
| `follow_up_suggestions` | Proactive related questions | UX enhancement; optional |

### Generation Prompt Template
```
You are a grounded assistant. Answer only using the provided context.

Context:
{packed_context_with_citation_anchors}

Question: {query}

Rules:
- Cite every factual claim with [N] matching the source number above.
- If the context doesn't contain enough information, set abstained=true and explain.
- List any claims you made that aren't directly supported in unsupported_claims.
- Return valid JSON matching the answer contract schema.
```

---

## 4. Abstention Patterns (§30)

| Pattern | How | When to Use |
|---|---|---|
| **Reranker top-1 threshold** | Abstain if top-1 score < calibrated_threshold | Primary mechanism — calibrate on golden set |
| **Score gap** | Abstain if top-1 and top-2 scores are close (< 0.05 gap) | Prevents confident answers when evidence is ambiguous |
| **Coverage check** | Abstain if query entities not found in any retrieved chunk | Catches "answer exists but not in corpus" |
| **LLM self-check** | Ask the model "is this fully answered by the context?" | Last-resort; highest latency |
| **High-stakes escalation** | Detect answer type; route to human or refuse | When answer could cause harm if wrong |

### Escalation Decision Table
Certain answer categories should trigger refusal or human escalation, not a low-confidence answer:

| Condition | Action |
|---|---|
| Multiple retrieved chunks directly contradict each other | Abstain + note conflict: "Sources disagree on this point" |
| Query involves financial, legal, or safety decisions | Add disclaimer: "Verify with an authorised source before acting" |
| Top-1 reranker score < abstention threshold AND query is high-stakes | Hard refuse: do not hallucinate a low-confidence answer |
| Query asks for a calculation or prediction (not retrieval) | Route to tool/SQL instead of RAG answer |
| User explicitly says "this is urgent" or "I need to be sure" | Escalate: "I recommend confirming with [human/official source]" |

**Calibration is mandatory.** Do not set abstention thresholds by intuition:
```python
# Use your golden set to find the threshold where precision ≥ target
thresholds = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]
for t in thresholds:
    abstained = [q for q in golden_set if top1_score(q) < t]
    precision = precision_at_k(non_abstained, k=5)
    abstention_rate = len(abstained) / len(golden_set)
    print(f"threshold={t}: precision={precision:.2f}, abstention_rate={abstention_rate:.2f}")
# Pick lowest threshold where precision >= target
```

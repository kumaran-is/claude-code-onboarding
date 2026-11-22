# RAG Response Contract

Reference for designing the API response contract for a production RAG backend. Covers payload separation, status enum, confidence model, span-level grounding, safety, streaming, versioning, and domain extensions.

**Cross-reference:** `context-packing-patterns.md §3` covers the *generation-side* answer contract — what the LLM is instructed to return. This file covers the *API response contract* — what the backend returns to clients (browser, mobile, backend-to-backend).

---

## 1. Design Principles

Five principles that should be decided at contract design time, before writing any code:

1. **Separate user-facing payload from internal payload.** Never leak retriever internals (raw scores, trace IDs, reranker metadata, chunk IDs) into the browser response. Users cannot act on them; leaking them exposes system internals and inflates payload size.

2. **Use closed enums for any field that drives UI or business logic.** `status`, `confidence_level`, `evidence_type`, `quote_policy`, `redaction_mode`, `warning_flags` — all must come from a closed set, not free LLM generation. Free generation drifts; closed enums are testable.

3. **Bake in `schema_version` from day one.** The contract will change within months. Adding fields is backward-compatible; removing or repurposing is not. Frontends should reject unknown `schema_version` values rather than guess.

4. **Derive confidence from evidence signals, not from the LLM's self-report.** LLM self-confidence is miscalibrated. Compute confidence from retrieval scores, rerank scores, citation coverage, freshness, and conflict detection.

5. **RAGAS-style faithfulness evals run async on sampled traffic, never in the synchronous response.** They require a second LLM call, doubling latency and cost. Attach scores to the trace store keyed by `trace_id`; alert on regressions per `prompt_version`.

---

## 2. Three-Tier Payload Separation

Every field in the system belongs to exactly one tier:

| Tier | Goes to | Fields |
|---|---|---|
| **User-facing** | Browser / mobile client | `schema_version`, `status`, `answer`, `answer_spans`, `confidence_level`, `citations` (title, section, page, quote, quote_policy, evidence_type), `assumptions`, `limitations`, `follow_up_questions`, `suggested_actions`, `safety`, `extensions`, `clarification_reason` |
| **Internal trace** | Logs + trace store (e.g. Langfuse, Phoenix, or your observability platform) | `confidence` (score, components, gates, warning_flags), `retrieval_metadata` (retriever, reranker, top_k, embedding_model, chunker_version), `trace` (trace_id, prompt_version, generated_at, tenant_id), `usage` (tokens, latency, cost), `relevance_score` per citation |
| **Async eval** | Eval pipeline, sampled 1–10% of traffic | RAGAS faithfulness, context precision, answer relevance — keyed by `trace_id` and `prompt_version` |

**Key rule:** The `confidence` object (with raw float, components, gates) is internal. The `confidence_level` band (`high`/`medium`/`low`) is user-facing. Never expose the float to users — it is pseudo-precision that erodes trust when users see `0.79` vs `0.81`.

---

## 3. Status Enum

Seven values. Each has a precise meaning; avoid using one as a substitute for another.

| Status | Meaning | Notes |
|---|---|---|
| `answered` | Confident answer grounded in retrieved context | Normal success path |
| `partial` | Some sub-questions answered; others lack evidence | Use when a multi-part query is partially satisfiable |
| `abstained` | No sufficient evidence; system refuses to guess | See `abstention-decision-framework.md` for triggers |
| `clarification_needed` | Query is ambiguous; cannot retrieve without disambiguation | Requires `clarification_reason` field explaining why |
| `tool_error` | Retriever, reranker, or vector store failed | Surface to oncall; do not show internal error to user |
| `policy_blocked` | Safety or compliance policy prevented the answer | Use `safety` block to explain what was withheld |
| `no_retrieval` | Query bypassed retrieval (pure LLM fallback) | **Must be explicitly policy-governed.** Teams often add this as a silent fallback — it quietly bypasses RAG, erodes grounding, and hides retrieval failures. Treat `no_retrieval` as a production alert, not a convenience path. |

**Stale retrieval is not a status.** Staleness is a quality issue surfaced via `warning_flags.stale_source` and a confidence band downgrade. The status remains `answered` or `partial`.

---

## 4. Confidence Model

### Derivation Formula (Internal)

```
confidence_score = w1 * retrieval_score
                 + w2 * rerank_score
                 + w3 * citation_coverage
                 + w4 * source_diversity      # penalize if all citations from one doc
                 + w5 * freshness             # temporal decay against doc age
                 - penalty_if_conflict_detected
```

Calibrate weights against a labeled golden set, not by intuition.

### Two-Track Split

Split the internal score into two floats — they fail differently:

| Track | Measures | Failure mode |
|---|---|---|
| `retrieval_confidence` | Was the right context found? | Bad retrieval + plausible answer = grounding problem (retrieval layer) |
| `answer_confidence` | Given the context, is the answer faithful and well-supported? | Good retrieval + bad answer = generation/faithfulness problem |

Collapsing both into one score hides which layer is broken. The user-facing `confidence_level` is still a single band — showing two indicators in UI confuses users.

### Faithfulness as a Gate, Not a Feature

If `faithfulness < faithfulness_threshold` (typically ~0.7), **clamp the band to `low`** regardless of the weighted retrieval score. Strong retrieval should not rescue an unfaithful answer.

```python
def compute_confidence_band(score: float, faithfulness: float, threshold: float = 0.7) -> str:
    if faithfulness < threshold:
        return "low"   # faithfulness gate — hard clamp
    if score >= 0.80:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"
```

### Banding Table

| Band | Score range | UI treatment |
|---|---|---|
| `high` | ≥ 0.80 | Show answer normally with citations |
| `medium` | 0.55–0.79 | Show answer with soft hedge or "verify" CTA |
| `low` | < 0.55 | Prefer abstention or clarification |

Calibrate thresholds against real user outcomes, not offline metrics.

### Warning Flags (Closed Enum)

Six named flags that travel with the internal confidence object. UI can render these as banners or tooltips on medium/low answers:

| Flag | Meaning |
|---|---|
| `single_source_dominance` | One document supplies >80% of cited context |
| `date_discrepancy` | Cited sources disagree on a relevant date |
| `stale_source` | At least one citation is older than the freshness threshold |
| `low_rerank_separation` | Top reranked chunks scored within a small margin of each other |
| `cross_document_conflict` | Two citations make contradictory claims |
| `faithfulness_gate_failed` | Faithfulness below threshold; band was clamped to `low` |

---

## 5. Span-Level Grounding

Link specific spans of the answer text back to their supporting citations using character offsets.

```json
"answer_spans": [
  { "start": 0, "end": 121, "citations": ["C1"] },
  { "start": 122, "end": 244, "citations": ["C2"] }
]
```

### Offset Encoding

Use **UTF-16 code units** — this matches JavaScript's native `String.length` and `String.prototype.substring`. Every browser frontend uses UTF-16 natively, avoiding off-by-one bugs when text contains emoji, accented characters, or non-Latin scripts. Document the chosen encoding in `schema_version` notes; never leave it implicit.

If the frontend is not JS (Swift, Kotlin, Python), convert at the consumer boundary.

Alternative: sentence indices. Less precise but encoding-agnostic. Pick one approach per contract version and do not mix.

### Evidence Type Enum

Every citation carries an evidence type. UI rendering differs per type:

| Type | Meaning | UI rendering |
|---|---|---|
| `direct` | Source directly states the cited claim | Solid underline on span |
| `inferred` | Claim follows by short inference from the cited source | Dashed underline on span |
| `contextual` | Source provides background but doesn't directly support claim | Sidebar reference only |

### Quote Policy Enum

Controls whether the raw quote text is included in the citation:

| Policy | Meaning |
|---|---|
| `full` | Full quote included in response |
| `excerpt` | Short excerpt only; user must open source for full text |
| `withheld` | No quote; pointer to source only |

Use `withheld` for content that cannot be excerpted due to licensing, PII, or legal constraints.

---

## 6. Safety & Redaction Block

Required field on every response. A missing `safety` block is not the same as `safety: {}`.

- `safety: {}` means "checked, nothing to flag"
- Missing `safety` means "not computed" — consumers must treat this as an error

```json
"safety": {
  "contains_pii": true,
  "redaction_mode": "masked",
  "redactions": [
    {
      "type": "ssn",
      "span": [342, 353],
      "mode": "masked",
      "replaced_with": "[REDACTED-SSN]"
    }
  ],
  "policy_flags": []
}
```

### Redaction Mode Enum

| Mode | Meaning |
|---|---|
| `none` | No redactions applied |
| `masked` | Sensitive spans replaced with placeholders inline in the answer |
| `partial` | Some content masked; some withheld entirely |
| `withheld` | Sensitive content removed; no inline placeholder |

The frontend needs the mode to render appropriate indicators. `policy_blocked` status uses the `safety` block to explain what was withheld.

---

## 7. Streaming Event Model

A canonical event model. SSE (browser) and NDJSON (backend-to-backend) are two encodings of the same events.

| Event | Emitted when |
|---|---|
| `status` | Once, at the start |
| `answer_delta` | Repeatedly, during generation |
| `citation` | As citations resolve |
| `warning_flag` | As the pipeline detects issues |
| `answer_span` | After generation is complete — see note below |
| `done` | Once, at the end; carries finalized full response |

**Do not emit `answer_span` mid-stream.** UTF-16 offsets into a partial string shift as the LLM produces more tokens. Compute spans once the answer text is finalized, then emit them before `done`.

### SSE (Browser)

```
event: status
data: {"status": "answered"}

event: answer_delta
data: {"text": "According to the policy, the user is responsible "}

event: citation
data: {"citation_id": "C1", "title": "Company Policy Document", "evidence_type": "direct"}

event: answer_span
data: {"start": 0, "end": 121, "citations": ["C1"]}

event: done
data: {"confidence_level": "high", "safety": {"contains_pii": false, "redaction_mode": "none", "redactions": [], "policy_flags": []}}
```

### NDJSON (Backend-to-Backend)

```
{"type":"status","status":"answered"}
{"type":"answer_delta","text":"According to the policy, the user is responsible "}
{"type":"citation","citation_id":"C1","title":"Company Policy Document","evidence_type":"direct"}
{"type":"answer_span","start":0,"end":121,"citations":["C1"]}
{"type":"done","confidence_level":"high","safety":{...}}
```

---

## 8. Schema Versioning

```json
"schema_version": "2026-05-23"
```

Use date-based or semver. Rules:

| Change type | Backward-compatible? | Required action |
|---|---|---|
| Adding a new optional field | Yes | Increment version in release notes |
| Adding a new enum value | Yes — if consumers handle unknown values gracefully | Document per-version enum values |
| Removing a field | **No** | Major version bump; deprecation period |
| Repurposing a field | **No** | Major version bump |
| Changing offset encoding | **No** | Major version bump |

**Frontends must reject unknown `schema_version` values** rather than guess at field semantics. Document offset encoding, enum values, and gate thresholds per version.

---

## 9. Domain Extensions Pattern

Keep the core contract domain-agnostic. Push domain-specific fields into a namespaced extension. This lets the core contract survive being reused across products without modification.

```json
"extensions": {
  "your_domain": {
    "related_entities": { ... },
    "citations_meta": { ... },
    "suggested_actions_enum_version": "v1"
  }
}
```

**Rules for extensions:**
- Core contract defines only shape: `suggested_actions: [{ action: string, label: string, params?: object }]`
- Extension provides the enum values for `action` — versioned independently (`suggested_actions_enum_version`)
- Different products plug in different enums without breaking the core
- Extension fields do not appear in internal trace or async eval tiers — they are user-facing only
- Version your extension enums separately from `schema_version`

---

## 10. Runtime Citation Validation

Offline citation metrics (`rag-evaluator`) do not stop a bad answer in production. Validate every answer before it ships. The general output-contract rule lives in `ai-playbook` (output contract section); this is the RAG-specific runtime check.

1. **Membership (deterministic):** collect the chunk ids actually retrieved in THIS request; any cited id outside that set → return the `abstained`/fallback shape. Log the bad ids only, never chunk text.
2. **Support (probabilistic):** per claim, check entailment of the claim by its cited chunk (NLI model, LLM judge, or a managed grounding API). Below threshold → abstain or escalate. The judge prompt treats the answer and the chunks as data, not instructions.
3. **Checker unavailable:** degrade visibly — ship with `verified=false` (surface it as a warning flag), never pass silently.

```python
async def validate_answer(answer: Answer, chunks_by_id: Mapping[str, str],
                          support_check: SupportCheck, threshold: float, abstain: Answer) -> Answer:
    if answer.status == "abstained":
        return answer
    if not answer.citations:
        return abstain                                   # ungrounded
    retrieved = set(chunks_by_id)
    if [c.chunk_id for c in answer.citations if c.chunk_id not in retrieved]:
        return abstain                                   # cited something not retrieved
    score = await support_check(answer.citations, chunks_by_id)
    if score is None:
        return replace(answer, verified=False)           # degrade visibly
    return abstain if score < threshold else answer
```

Unit-test the five paths with a scripted checker: ghost id → abstain; supported → ships verified; low support → abstain; checker returns `None` → ships `verified=False`; no citations → abstain. (Verified: 6 pytest cases pass, `ruff` and `mypy --strict` clean, against a scripted fake checker — no live model.)

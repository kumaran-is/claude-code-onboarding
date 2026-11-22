# Abstention Decision Framework

Reference for deciding when a RAG system should refuse to answer, ask for clarification, or answer with citations. Apply when designing the generation layer or reviewing abstention behavior in production.

**Implementation note:** For calibration code (threshold tuning on golden set), see `context-packing-patterns.md §4`.

---

## 1. Why Abstention Matters

RAG systems are often used in domains where users act on the answer. A confident but unsupported answer creates real business risk.

| Problem | Meaning |
|---|---|
| **Hallucination** | The model invents unsupported facts |
| **Fake confidence** | The answer sounds correct but is not grounded in retrieved context |
| **Wrong policy answer** | The system gives incorrect rules, fees, or obligations |
| **Bad user action** | User acts on an answer that was never supported by source data |
| **Trust failure** | Users lose confidence in the system after a single wrong answer |

**Core principle:** Abstention is not a failure. It is a trust-preserving behavior. A system that says "I don't have enough context" is more trustworthy than one that guesses confidently.

---

## 2. Behavioral Taxonomy

Four distinct behaviors — only one of them is correct for each situation:

| Behavior | Meaning | Example |
|---|---|---|
| **Hallucination** | Model answers without retrieved support | "The fee is $50" when no fee was retrieved |
| **Abstention** | Model refuses to guess | "I do not have enough context to answer" |
| **Clarification** | Model asks for the missing detail | "Which document or policy section should I check?" |
| **Grounded Answer** | Model answers from retrieved evidence with citations | "According to the policy, notice is required 30 days in advance [source: policy-v3.pdf §4.2]" |

**Decision rule:**
```
No strong context  → Abstain
Incomplete context → Ask for clarification (preferred over guessing)
Strong context     → Answer with citations
```

---

## 3. When to Abstain — 8 Triggers

A RAG system should abstain when any of these conditions hold:

1. **No relevant chunks retrieved** — retriever returned nothing meaningful
2. **Retrieved chunks are off-topic** — chunks retrieved but semantically unrelated to the question
3. **Context does not directly answer the question** — related context exists but the specific fact is absent
4. **Conflicting information across documents** — two retrieved sources give different answers to the same question
5. **Citations cannot support the generated answer** — answer would require claims not present in any retrieved chunk, cites a chunk id that was not retrieved in this request, or fails the claim-support check (runtime enforcement: `rag-response-contract.md` §10)
6. **Retrieved evidence is stale** — chunks exist but are from a superseded version; current answer unknown
7. **High-stakes domain without source support** — legal, financial, medical, or policy question with no grounding source
8. **Required document was not retrieved** — the answer depends on a specific document that isn't in the context window

---

## 4. Common Triggers Table

Concrete trigger → example → correct behavior:

| Trigger | Example | Correct Behavior |
|---|---|---|
| **No context** | No relevant clause retrieved for the question | Abstain |
| **Low relevance** | Password reset question retrieves vacation policy | Abstain |
| **Missing clause** | Policy retrieved but the specific section is absent | Abstain |
| **Conflicting docs** | Two source documents give different answers to the same question | Explain conflict; ask which is authoritative |
| **No citation** | Answer cannot be mapped to any source chunk | Do not answer |
| **Low confidence** | Reranker top-1 score below calibrated threshold | Ask for more context or abstain |
| **High-risk domain** | Legal, financial, medical, or policy question without grounding | Require strong evidence before answering |

---

## 5. Abstention Decision Matrix

Use context quality and risk level together to choose the action:

| Context Quality | Risk Level | Action |
|---|---|---|
| Strong context + citations available | Low | Answer with citations |
| Strong context + citations available | High | Answer carefully; include every citation; note limits |
| Related but incomplete context | Low | Ask for clarification — preferred over guessing |
| Related but incomplete context | High | Abstain; explain what's missing |
| No relevant context retrieved | Any | Abstain |
| Conflicting context across documents | Any | Explain the conflict; ask user to identify the authoritative source |
| No citation support for the answer | Any | Abstain |

---

## 6. Message Templates

Use these verbatim or adapt for your domain. The key properties: specific about what is missing, not apologetic, tells the user what to provide next.

### Missing Context
```
I do not have enough information in the retrieved context to answer that reliably.
Please provide the relevant document or policy section.
```

### Weak Context
```
The retrieved context is related, but it does not directly answer the question.
I need the specific clause or policy before giving an answer.
```

### Conflicting Context
```
I found conflicting information in the retrieved documents.
Please confirm which document should be treated as the source of truth.
```

### High-Risk Question
```
Because this question depends on legal, policy, or contractual language,
I cannot answer without supporting source text.
Please provide the relevant document or clause.
```

---

## 7. Abstention Accuracy Grading

Abstention itself must be evaluated — a system that abstains too aggressively or too rarely both fail.

### Good Abstention ✅
The system refuses when context is genuinely missing or weak. User is correctly told the answer cannot be given from available evidence.

### Bad Abstention ⚠️
The system refuses even though the retrieved context clearly contains the answer. This is over-refusal — reduces usefulness, erodes trust in a different way.
- **Symptom:** High false abstention rate; users complain "it never answers anything"
- **Fix:** Lower abstention threshold; check if retriever is returning relevant chunks but reranker scores are miscalibrated

### Dangerous Failure ❌
The system answers confidently when it should have abstained. The model guesses without grounding.
- **Symptom:** High false answer rate; users act on wrong information
- **Fix:** Raise abstention threshold; add per-claim citation check; strengthen grounding prompt

### Priority Ranking
```
Best:   Answer when grounded. Abstain when not grounded.
Bad:    Abstain too often (false abstention).
Worst:  Guess confidently without evidence (false answer).
```

---

## 8. Rule of Thumb

**For normal questions:**
Answer when retrieved context is strong and citations are available.
Ask for clarification when context is incomplete.

**For high-risk questions** (legal, financial, policy, contractual):
Do not answer unless the retrieved context clearly supports the answer with specific citations.
Silence is safer than a confident wrong answer.

**For production RAG systems:**
```
Retrieve → Rerank → Check context relevance → Check faithfulness
    → Answer with citations  (if strong context)
    → Ask for clarification  (if incomplete context)
    → Abstain                (if no or conflicting context)
```

**Track both failure modes in your golden set:**
- False abstention rate — refused when answer was available
- False answer rate — answered when it should have abstained

The dangerous failure is always the false answer. Over-refusal is frustrating; under-refusal is a trust-destroying incident.

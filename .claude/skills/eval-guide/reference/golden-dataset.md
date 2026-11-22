# Golden Dataset Discipline

> The golden dataset is release evidence. **Never modify a case to make a test pass**: fix the agent, or classify the red as a TEST/EVALUATOR error and fix the assertion through review.
> Case-count floors by risk tier: `ai-eval-designer` agent (canonical). ADK evalset JSON schema: `adk-eval-guide`.

## Example layout

```
tests/golden/
├── dataset_manifest.yaml        # ONE manifest: version, per-file sha256, case counts, approvers
├── <flow>/cases.json            # per flow (answer, classify, search, ...): dev | heldout split per case
├── <flow>/critical_cases.json   # critical-path cases, gated at 100%
├── security/                    # hard CI blockers (ci-tiers.md), restricted set
├── isolation/                   # tenant, session and memory isolation
├── multi-turn/
└── regression/                  # incident-derived cases
```

## Three sets, never mixed

| Set | Use | Changes |
|---|---|---|
| dev / tuning | inspect freely while iterating | any time |
| held-out regression | release evidence only | add cases; fix failures only with general changes |
| restricted safety | security/safety release gate | only via security review |

Never present tuning-set results as release evidence. Overfitting tell: the tuning pass rate climbs while held-out stalls or drops.

## No ground-truth leakage, no case-shaped fixes

- Feedback while iterating names the failed criterion ("expected 504, got 500"), never the expected output. A pass obtained after the expected answer entered the agent's context is a debugging run: re-run clean (fresh session) before recording any number. Simulated users never see it.
- Case inputs, answers and ids never appear in prompts, few-shot examples, retrieval corpora or tool fixtures; no keyword branch whose only purpose is a case. Before merging a fix:

```bash
grep -rnF "<distinctive phrase from the failing case>" <agent-src> prompts/ <corpus-dir>   # must be empty
```

## Manifest and run metadata

```yaml
# tests/golden/dataset_manifest.yaml
version: "2026.11.1"
files:
  - path: answer/cases.json
    sha256: "<sha256 of the file>"
    cases: 120
  - path: security/cases.json
    sha256: "<sha256>"
    cases: 18
review_policy:
  requires_pr_review: true
  approvers: ["<team or role>"]
```

CI recomputes hashes and counts and fails on mismatch. Every result row records: `eval_run_id, git_sha, dataset_version (manifest version + sha256), prompt name + version + content hash, model id, judge model + rubric version, corpus/index version, embedding model, reranker version, seed, trial_count, tier`. Compare runs only when dataset version, judge and tier match.

## Closed case schema (unknown keys fail)

An expectation key the runner does not read is silently ignored, so a case that checks nothing passes. Validate cases with a closed schema (executed: a misspelled `forbiden_tools` raises `ValidationError`):

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Expectations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_calls: list[dict[str, object]] | None = None   # asserted on the tool-call log
    forbidden_tools: list[str] = []
    persisted_rows_unchanged: list[str] = []
    required_facts: list[str] = []                      # authored, each traced to source_ids
    must_not_claim: list[str] = []                      # violating claims, not topic words
    abstain: bool = False

class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    split: Literal["dev", "heldout", "safety"]
    category: Literal["happy_path", "edge", "adversarial", "negative", "isolation", "regression"]
    input: str
    source_ids: list[str] = []
    expect: Expectations
    added_by: str = Field(pattern=r"^(human|synthetic|incident-[\w-]+)$")
    xfail_blocker: str | None = None                    # must cite an OPEN issue when set
```

**Positive control per assertion:** feed a synthetic result that violates the new assertion; the case must go red. An assertion that never fails proves nothing.

## Assertion design

- **Assert pre-answer effects at their boundary.** A correct refusal text can hide that private data was already retrieved or a write already happened. Assert on the tool-call log, retrieval span and routing record.
- **Side effects are asserted on persisted state** after the session: zero unauthorized rows or actions, decision/audit record present even on denial. A correct final answer reached through an unauthorized write is FAIL.
- **A model or judge label may stop an action, never authorize it.** Authorization, tenant scoping, tool allowlists and budgets are deterministic code.
- **Shape prohibitions around the violating claim** ("you are entitled to ...", "done, refund issued"), not topic words: a topic ban also matches the compliant refusal. Test every guard against the expected refusal text.
- **Assert only floors the product contract promises** (no relevancy floor on an abstention turn; no section-attribution claim on a sentence-level metric). A red against a fabricated floor is a TEST/EVALUATOR fix, never agent tuning.
- **Negative acceptance is owed coverage:** out-of-domain, abusive input, ambiguity / not found, dependency failure with no false success, mixed supported + unsupported input decomposed. A verdict lists owed vs excluded dimensions with a reason.

## Isolation, memory and side effects

| Case | Assert |
|---|---|
| Tenant isolation | Caller in org A never receives org B ids in tool args, tool results, retrieved chunks or persisted rows |
| Session / thread isolation | Session B never sees session A's messages, checkpoints or memory entries (assert on store reads and tool args, not answer text) |
| User memory isolation | User B's memory search returns zero of user A's entries, including under a prompt that asks for "other users' notes" |
| Memory correctness | A corrected fact supersedes the stale one: current state beats stale memory |
| Deletion | Deleting a user/document removes it from memory stores, caches, indexes and eval artifacts |
| Indirect injection | An instruction planted in a retrieved document or tool output does not produce a tool call or exfiltrating argument |

Memory design: `agentic-ai-dev/reference/agentic-memory-systems.md`.

## Landing a fix without buying a regression

Measure the whole case population in both directions (fixed vs newly broken), count over- vs under-triggering separately, keep a positive control (revert the fix → the intended case goes red), and re-run happy paths after a negative-case fix. A required safety class that the deterministic taxonomy has no category for is a PRODUCT gap: never add a pattern that matches only the one failing utterance.

## Hard rules

- PR review for every change under `tests/golden/`; the manifest names approvers.
- Golden data is versioned in Git, never ephemeral.
- Critical cases are tracked separately and gated at 100%.
- **Regression flywheel:** a production incident becomes a regression case **before** the fix merges, PII-scrubbed, with provenance `added_by: incident-<id>`, and it must fail before the fix.
- Production-sampled cases are redacted before they leave the service; sampling rate comes from config (default off).

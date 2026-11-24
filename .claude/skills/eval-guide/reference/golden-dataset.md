# Golden Dataset Discipline

> The golden dataset is release evidence. **Never modify a case to make a test pass**: fix the agent, or classify the red as a TEST/EVALUATOR error and fix the assertion through review.
> Case-count floors by risk tier: `ai-eval-designer` agent (canonical). ADK evalset JSON schema: `adk-eval-guide`.

## Layout (one manifest per dataset directory)

```
tests/golden/
  features/<feature>/   golden.jsonl  edge_cases.jsonl  adversarial.jsonl  multi_turn_*.jsonl  dataset_manifest.yaml
  rag/                  <corpus>_golden.csv  dataset_manifest.yaml
  tools/                contract_cases.jsonl  schema_negative_cases.jsonl  isolation_cases.jsonl  unsafe_call_cases.jsonl  dataset_manifest.yaml
  security/             prompt_injection.yaml  jailbreak.yaml  data_exfiltration.yaml  <compliance>_bypass.yaml  dataset_manifest.yaml
  production_regressions/  INC-YYYY-NNN.yaml  dataset_manifest.yaml
  baselines/            current.json  previous_release.json  anchor.json      # eval_result.schema.json shape
tests/eval/             thresholds.yaml  r1-routing.yaml
```

A working, validator-clean copy of this tree: `assets/golden-scaffold/` (generic `support-answer` feature, one write tool, three red-team cases, one regression file). It is deliberately below the default minimum sizes, so the validator reports REVIEW items for it.

| Dataset type (`dataset_type`) | Covers | Read by |
|---|---|---|
| `happy_path_trajectory` | correct tools + response on typical input | framework eval |
| `edge_cases` | empty, max-length, ambiguous, multilingual | framework eval + judge |
| `adversarial_security` | injection, jailbreak, exfiltration | red-team runner (`red-teaming.md`) |
| `data_isolation` | scope A asks for scope B's data, 10+ phrasings | deterministic tests + red team |
| `domain_compliance` | regulated-rule bypass + paraphrase attacks | tests + red team + policy rubric |
| `rag_grounding` | question, required + **forbidden** context ids, expected answer | RAG eval library |
| `tool_contract` | per-tool contract, auth, behaviour, security | tool suite |
| `production_regressions` | sanitized real failures, one file per incident | whichever tool the incident touched |
| `multi_turn` | flows | multi-turn runner |

## Three sets, never mixed

| Set | Use | Changes |
|---|---|---|
| dev / tuning | inspect freely while iterating | any time |
| held-out regression | release evidence only | add cases; fix failures only with general changes |
| restricted safety / protected canary | security/safety release gate; protected canaries (below) | only via security review |

Never present tuning-set results as release evidence. Overfitting tell: the tuning pass rate climbs while held-out stalls or drops.

## No ground-truth leakage, no case-shaped fixes

- Feedback while iterating names the failed criterion ("expected 504, got 500"), never the expected output. A pass obtained after the expected answer entered the agent's context is a debugging run: re-run clean (fresh session) before recording any number. Simulated users never see it.
- Case inputs, answers and ids never appear in prompts, few-shot examples, retrieval corpora or tool fixtures; no keyword branch whose only purpose is a case. Before merging a fix:

```bash
grep -rnF "<distinctive phrase from the failing case>" <agent-src> prompts/ <corpus-dir>   # must be empty
```

- Prompt few-shot examples are never eval inputs, in either direction. `validate_prompts.py prompts --golden-root tests/golden` (prompt-engineering-patterns) BLOCKs on an overlap (`PC_EXAMPLE_EVAL_OVERLAP`). The input text in these case shapes lives in `input.user_message`, `input.turns[]` and `input.planted_content` (trajectory, red-team, regression cases) and the CSV `question` column (RAG); an overlap check that reads other keys sees nothing, so prove it with a planted duplicate before trusting a clean run.

## Schemas and validator

| File | Schema (closed: unknown keys fail) |
|---|---|
| `dataset_manifest.yaml` | `assets/schemas/dataset_manifest.schema.json` |
| trajectory / multi-turn JSONL line | `assets/schemas/trajectory_case.schema.json` |
| RAG CSV row (8 required columns in fixed order, then optional `query_type`, `scope`, `expected_outcome`, `high_stakes`; lists `\|`-separated). `query_type` is the RAG golden-set slice (factual, identifier, broad, multi-part, vague, temporal, comparison, high-stakes) and needs `high_stakes: true` when it is `high-stakes`; `expected_outcome` is the answer-contract outcome (ANSWERED, PARTIAL, NOT_FOUND, CONFLICTED, STALE, HUMAN_REVIEW) | `assets/schemas/rag_case.schema.json` |
| tool JSONL line | `assets/schemas/tool_case.schema.json` |
| red-team YAML (`cases:`) | `assets/schemas/redteam_case.schema.json` |
| `INC-YYYY-NNN.yaml` | `assets/schemas/regression_case.schema.json` |
| eval result / baseline | `assets/schemas/eval_result.schema.json` |
| thresholds, R1 routing | `assets/schemas/thresholds.schema.json`, `r1_routing.schema.json` |

```bash
uv run --script .claude/skills/eval-guide/scripts/validate_golden.py tests/golden \
    --base-root "$BASE_CHECKOUT/tests/golden" --json reports/golden-validation.json   # exit 0 pass, 1 findings, 2 bad input
uv run --script .claude/skills/eval-guide/scripts/validate_golden.py hash tests/golden/rag        # sha256 + counts to paste
uv run --script .claude/skills/eval-guide/scripts/validate_golden.py --selftest
```

`--base-root` points at the merge-base checkout of the same tree (e.g. `git worktree add`) and enables the SemVer check. Rules: GD001 case data without a manifest · GD002 manifest schema · GD003 listed file missing · GD004 sha256 mismatch · GD005 case count mismatch · GD006 case file not in the manifest · GD007 case schema · GD008 duplicate case id · GD009 case feature differs from manifest · GD010 fewer cases than `minimum_required_cases` · GD011 dataset not in `nightly` + `release` · GD012 critical cases outside `ci` · GD013 PII pattern · GD014 feature or tool with zero red-team cases · GD015 write tool without an audit-record case · GD016 context id both required and forbidden · GD017 regression file name/timestamps/SLA · GD018 default minimum sizes (REVIEW) · GD019 version bump too small · GD020 protected-canary review overdue (REVIEW). BLOCK fails; REVIEW fails only with `--strict`.

## Manifest, versioning and run metadata

```yaml
# tests/golden/features/support-answer/dataset_manifest.yaml
dataset_name: support-answer-golden
version: 1.4.0                      # SemVer, see bump table
owner: support-ai-team              # team or role
feature: support-answer
dataset_type: happy_path_trajectory
source: expert_authored             # synthetic | expert_authored | sanitized_production | incident_regression
# synthetic_provenance:             # required when source: synthetic (data governance standard §13)
#   generator: case-gen
#   generator_version: 1.2.0
#   seeded_from_real_data: false     # true requires privacy_review: <memorization / nearest-neighbour check ref>
#   reviewed_by: support-ai-team     # human owner; synthetic cases are never sole release evidence (G7)
schema_version: "1.0"
minimum_required_cases: 8
tags: [trajectory, multi_turn]
splits: [smoke, ci, nightly, release]
files:
  - {path: golden.jsonl, sha256: "<sha256>", cases: 48, case_schema: trajectory}
review: {requires_pr_review: true, approvers: [support-ai-team, ai-security-reviewers]}
protection: {class: heldout, access: restricted}
```

| Bump | When (enforced by GD019 against the base tree) |
|---|---|
| PATCH | typo / metadata fix (tags, owner, risk wording) |
| MINOR | new cases, nothing existing changed |
| MAJOR | schema or scoring change, a removed case, or an existing case's input or expected behaviour changed |

**Every eval result records** `feature_version, prompt_name, prompt_version, model_name, tool_surface_hash, dataset_name, dataset_version, eval_run_id` (required by `eval_result.schema.json`), plus `tier`, `git_sha` and the judge model + rubric version + trial count when a judge ran. Also record corpus/index version, embedding model, reranker version and seed where they apply. Compare runs only when dataset version, judge and tier match: `eval_gate.py` fails closed otherwise (EG008).

## Selection: which cases run when

| Stage | Selection |
|---|---|
| Local smoke | `smoke`-tagged cases + critical cases for the changed feature |
| Local full | all cases for the changed feature + sampled others |
| PR / CI (R1) | all cases for the changed feature + **all** critical security/compliance/isolation cases + all regressions for the area (`eval_gate.py route`) |
| Nightly | everything |
| Pre-release | everything + baseline comparison + zero critical regressions |
| Production | ~1% sampled traces to managed eval; confirmed failures become regression files |

Regression cases for an area always run when that area changes, and critical cases are never sampled out (GD012; `always` suites in `r1-routing.yaml`).

## Baselines (triple) and the gate

| Baseline | Updated | Catches | Gate behaviour |
|---|---|---|---|
| Current (last green main) | every green merge | PR regressions | drop > `max_drop` (e.g. 2 pp) on a thresholded metric blocks (EG009); P95 latency or cost > 1.2× blocks (EG011) |
| Previous release | every release tag | drift over a sprint | same checks; required in `--release` mode |
| Anchor (first launch) | only by explicit decision + ADR | slow long-term drift | > 5% relative drop raises an alert (EG012, REVIEW), never a silent pass |

Store results under `reports/evals/<date>/<feature>/`. Baseline files are results of the same schema, written only by a reviewed step. Any critical, isolation, compliance, tool-auth or security case that is not PASS blocks (EG003) regardless of the aggregate.

## Closed case schema (unknown keys fail)

An expectation key the runner does not read is silently ignored, so a case that checks nothing passes. The committed-file contract is the JSON Schema set above (`validate_golden.py`); inside a Python runner, load cases into a closed model as well (executed: a misspelled `forbiden_tools` raises `ValidationError`):

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
    partition: Literal["dev", "heldout", "restricted"]
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

## Data flywheel: production failure → permanent test

```
alert / complaint / canary → replay trace, export case → identify prompt + model + tool-surface versions
→ sanitize PII → commit production_regressions/INC-YYYY-NNN.yaml → case FAILS on pre-fix code, PASSES on post-fix
→ added to the CI matrix for the area, forever
```

An incident closes only when all of that is true. The regression schema requires `versions`, the signed `sanitization` checklist, `pre_fix_ref`, `post_fix_ref` and `ci_matrix_area` (route it in `r1-routing.yaml`); GD017 checks the file name and the detection → dataset time:

| Severity | Detection → dataset | Dataset → green CI |
|---|---|---|
| P0 safety / compliance / data leak | ≤ 24 h | ≤ 24 h |
| P1 critical misclassification | ≤ 72 h | ≤ 72 h |
| P2 accuracy drop > 5% | ≤ 1 week | ≤ 1 sprint |
| P3 minor quality | ≤ 1 sprint (`--sprint-days N` to check) | next sprint |

Prove fail-before/pass-after by running the case on both refs; the validator checks the refs are recorded, not that the runs happened.

## Minimum sizes (defaults, ADAPT)

| Dataset | Day 1 | Pre-launch (`--stage prelaunch`) |
|---|---|---|
| Each implemented feature | 8 | 50+ (100+ for high-variance classifiers) |
| Each planned feature | 3–5 smoke | 25–50 |
| Critical-case set | all critical categories × 3 phrasings | same, expanded |
| RAG features | 10 | 100+ |
| Compliance adversarial | 25 | 100+ |
| Isolation | 10 | 50+ |
| Tool suite | 5 per tool: happy, auth-fail, schema-invalid, scope-mismatch, downstream-timeout | same for every planned tool |
| Prompt injection | 10 | 100+ |
| Multi-turn | 3 per flow | 15 per flow |

GD018 reports shortfalls as REVIEW (a project may set different floors with a recorded decision; `--strict` makes them fail). Planned-feature and critical-category counts are not computed: the validator cannot know your plan or category list. `minimum_required_cases` in a manifest is the project's binding floor (GD010, BLOCK).

## PII sanitization (non-negotiable)

Replace names with aliases (`user_a`), emails with `@example.com`, phones with reserved test ranges (e.g. NANP 555-0100 to 555-0199, UK 07700 900000 to 900999), addresses with fictitious ones, ids with sequential aliases; remove payment data entirely; reword free text so it keeps the pattern but none of the original wording; replace images with synthetic ones of the same category. The sanitization checklist is signed off in every regression-case PR (schema: all items `true`, `signed_off_by` set).

GD013 is a deterministic backstop, not proof of sanitization: it flags emails outside reserved domains (RFC 2606/6761 `example.*`, `.test`, `.invalid`, `.localhost`), phone numbers outside the reserved ranges above, US SSN patterns, Luhn-valid card numbers and mod-97-valid IBANs. It cannot detect names, addresses or reworded free text; the checklist and review cover those.

## Protected canary datasets

A dataset with `protection.class: protected_canary` must declare (schema-enforced): `access: restricted`, `labels_hidden: true`, `excluded_from_training: true` (separate training and evaluation pipelines), `contamination_check {method, last_run}`, `refresh_review_due`, `provenance` and `access_review {reviewer_role, last_review}`; versioning is the manifest SemVer. GD020 raises REVIEW when the refresh review is overdue or the contamination check or access review is older than a quarter (recommended baseline: review relevance quarterly; refresh on contamination, material drift or new capabilities). Restricting storage access, keeping labels out of the runner's view and running the independent access review are platform and organisational controls: the manifest records them, it does not enforce them.

## Ten non-negotiable rules → enforcement

| Rule | Enforced by |
|---|---|
| 1. Golden datasets live in Git | layout + GD001 (case data must sit under a manifest) |
| 2. Every case has a stable `case_id` | schemas (pattern) + GD008 (unique) + GD019 (a changed case needs MAJOR) |
| 3. Every case has an owner, feature, risk level and tags | schemas (feature, risk, tags required; owner per case or from the manifest) |
| 4. Every incident creates or updates a regression case before it closes | regression schema + GD017; closing the incident is a process check |
| 5. No real PII is committed | GD013 backstop + signed sanitization checklist |
| 6. Critical cases always run in PR CI | GD012 + `always` suites in `r1-routing.yaml` |
| 7. Full datasets run nightly and before every release | GD011 (`nightly` + `release` splits) |
| 8. Every result records dataset, prompt, model and tool-surface versions | `eval_result.schema.json` (gate input fails with exit 2 without them) |
| 9. Releases are approved against a specific dataset version | `eval_gate.py check --release --approved-dataset NAME@VERSION` (EG013) |
| 10. No AI feature ships without its golden baseline passing | `--release` requires current + previous-release baselines and passes them (EG013, EG009) |

## Hard rules

- PR review for every change under `tests/golden/`; the manifest names approvers.
- Golden data is versioned in Git, never ephemeral.
- Critical cases are tracked separately and gated at 100%.
- **Regression flywheel:** a production incident becomes a regression case **before** the fix merges, PII-scrubbed, with provenance `added_by: incident-<id>`, and it must fail before the fix.
- Production-sampled cases are redacted before they leave the service; sampling rate comes from config (default off).

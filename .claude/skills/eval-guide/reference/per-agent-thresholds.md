# Per-Flow Thresholds (example) and Rollback Triggers

> Every number here is an **ADAPT default**, not a universal value. A threshold blocks merge only once it is **ratified**: written per feature from the inventory (`eval-program-adoption.md`), calibrated after the first ~50 real traces, and recorded with `status: ratified`, `ratified_by`, `ratified_on` and a `decision_ref` in `tests/eval/thresholds.yaml` (schema `../assets/schemas/thresholds.schema.json`). `status: proposed` thresholds are reported as advisories by `../scripts/eval_gate.py`, never as gates, and no "TBD" may remain in a merge gate at Day 1.
> Never lower a gate, drop cases or switch metric mode to obtain a pass, and never lower one by repeated re-baselining; review thresholds quarterly against the anchor baseline (`golden-dataset.md`). Classify a red first (`../SKILL.md` Process). Flow names below are examples; keep the metric directions.

## Score directions (read before copying a threshold)

| Metric | Range | Direction | Gate form |
|---|---|---|---|
| ADK `hallucinations_v1` | 0-1 | higher = more sentences supported | `threshold` = minimum mean score, e.g. `≥ 0.9`; never `= 0` or `≤ 0.05` (those are inverted: they pass a fully hallucinating agent or fail a perfect one) |
| ADK `response_evaluation_score` | **1-5** | higher = more coherent | a 0-1 threshold such as 0.8 passes every score; ADK does not range-check thresholds |
| ADK `tool_trajectory_avg_score`, `final_response_match_v2`, `safety_v1` | 0-1 | higher is better | minimum |
| Ragas `Faithfulness`, `FactualCorrectness` | 0-1 | higher is better | minimum, both must clear |
| Deterministic isolation / injection / schema checks | count | 0 violations | `== 0`, hard blocker |

## Example threshold table

| Flow | Trajectory | Final response | RAG | Security / other |
|-------|-----------|----------------|-----|------------------|
| `classify_flow` | `tool_trajectory_avg_score ≥ 0.7` | `final_response_match_v2 ≥ 0.85` | n/a | critical-label cases 100%; p99 latency budget |
| `ranker_flow` | `tool_trajectory_avg_score ≥ 0.7` | top-1 ≥ 0.9 | Recall@10 ≥ 0.85 | isolation 100% (0 foreign ids) |
| `multi_turn_flow` | flow pass ≥ 0.95 on critical flows | goal accuracy ≥ 0.9 (`multi_turn_task_success_v1` or DeepEval `GoalAccuracyMetric`) | n/a | turn cap; simulator never sees the expected answer |
| `search_flow` | `ToolCallAccuracy(strict_order=True) ≥ 0.9` | top-1 match ≥ 0.9 | Recall@10 ≥ 0.85 (canonical definition) | tenant isolation 0 violations |
| `answer_flow` | n/a | `hallucinations_v1 ≥ 0.9` | `Faithfulness ≥ 0.9`; context precision ≥ 0.8; `FactualCorrectness(mode="recall", atomicity="high") ≥ 0.85`; per-slice Recall@5 | cited chunk ids ⊆ retrieved ids (0 violations) |
| `dashboard_flow` | `final_response_match_v2 ≥ 0.8` | — | n/a | isolation probe 0 leaks (deterministic, not `TopicAdherence`) |
| `extraction_flow` | `final_response_match_v2 ≥ 0.8` | field accuracy ≥ 0.9 | n/a | schema validity 100% |
| `ingestion_flow` | n/a | — | n/a | idempotency 100%; chunk dedup |
| unlisted flows | `final_response_match_v2 ≥ 0.80` | — | — | hard blockers always apply |

Retrieval metric definitions (Recall@K, Precision@K, MRR, nDCG, zero-relevant handling): `llm-evaluation/reference/evaluation-metrics.md` §2. A threshold must name which definition it uses.

## Critical-path sub-threshold

For the highest-risk flow, an aggregate ≥ 85% is insufficient for critical-path cases (safety-critical classifications, irreversible actions). Critical cases live in their own file and gate at **100%**: one miss in any declared trial blocks the merge regardless of the aggregate. Remember the resolution limit: at N=100, a pass rate of 0.85 has a ±0.07 95% CI. Mark those rows `case_class: critical` (or `isolation`, `compliance`, `tool_auth`, `security`) in the result file: `eval_gate.py check` blocks on any non-PASS case of those classes whatever the aggregate (executed: one failed critical case gave `EG003` and exit 1 alongside an accuracy of 0.5). With ADK, declare the trials in `eval_config.json` and gate critical cases on reliability, not capability: `"multi_run_config": {"num_runs": 3, "cross_run_criteria": [{"method": "pass_hat_k", "k": 3, "threshold": 1.0}]}` (google-adk 2.15.0, executed with a scripted model: one bad run in three failed the case, exit 1; `pass_rate` with threshold 0.6 passed the same runs).

## Other zero-tolerance gates

| Scope | Gate |
|-------|------|
| Answer flows | `hallucinations_v1 ≥ 0.9` and `Faithfulness ≥ 0.9`; any unsupported claim on a critical case = FAIL |
| Policy-gated flows | policy detector fires on 100% of the adversarial set |
| Any multi-tenant flow | 0 cross-tenant reads (CI blocker #1), 0 leaks in R4 probes |

---

## Production rollback triggers

Apply after a version is serving traffic. If any trigger fires, move the prompt/model label back to the previous version (registry keeps all versions) and follow `deployment-ci-cd/reference/llmops-release-and-rollout.md`.

| Signal | Trigger | Source |
|--------|---------|--------|
| Task success rate | drops > 10% from the 7-day baseline | trace/metric aggregation per flow |
| Critical-path case | any miss | R4 probe |
| Tenant isolation violation | any | isolation probe; page immediately |
| Policy detector miss on known adversarial input | any | red-team probe re-run on deploy |
| Tool-call error rate | +5 points over baseline | span attributes |
| p99 latency | +30% over baseline | service metrics |
| Cost per task | +20% over baseline | token metrics per session |
| `hallucinations_v1` on sampled traffic | mean below the release threshold | scheduled judge run on redacted samples |

### Rollback process

1. Alert fires → identify the changed prompt/model/index version from span attributes (`app.prompt.version`, model id).
2. Move the label back to N-1; wait for the registry TTL; confirm the served version in traces.
3. Run the R1 gate and the critical-case probe against the rolled-back version.
4. Record trigger, metric value, version diff and reproduction; add the failing input as a regression case (must fail on the bad version).
5. Do not redeploy the failed version without a new eval cycle and `eval-reviewer` approval.

Alert routing (pages vs chat), dashboards and SLOs: `deployment-ci-cd/reference/ai-observability.md`.

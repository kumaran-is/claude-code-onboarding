---
name: eval-guide
description: "AI eval process and infrastructure: golden datasets, prompt registry, CI eval tiers (R1–R4), promotion gates, verdict precedence, judge trials, fake-model test layers, pytest harness; DeepEval, Ragas, Giskard, Promptfoo, Langfuse, Phoenix, adk eval, Vertex GenAI Eval. Use when writing eval code or eval CI. Metric formulas → llm-evaluation."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: deepeval, ragas, giskard, promptfoo, langfuse, phoenix, PromptRegistry, prompt registry, golden dataset, evalset, redteam, MCPUseMetric, Faithfulness, ToolCallAccuracy, hallucinations_v1, tests/golden, dataset_manifest, R1 gate, R2 nightly, R3 pre-release, R4 canary, ci tier, eval threshold, ArenaGEval, set_default_generator, promptfooconfig.yaml, Scenario, Suite, eval-reviewer, golden case, asyncio_mode, InMemoryRunner, fake model, scripted model, judge trials, median-of-3, evidence accounting, prompt regression, promotion gate, memory isolation test, prompt lifecycle
  related-skills: llm-evaluation, rag-evaluator, adk-eval-guide, google-adk, agentic-ai-dev, python-dev, adk-observability-guide
  domain: agentic-ai
  role: specialist
  scope: evaluation
  output-format: code
last-reviewed: "2026-11-23"
---

# Eval Guide

## Iron Law

**Deterministic checks decide; an LLM judge only scores semantic quality and never upgrades a case. A case that did not run, or whose judge errored, is never PASS.**

- **Never write eval-tool code from memory.** Query Context7 (`ragas`, `deepeval`, `giskard`, `promptfoo`, `langfuse`) before every metric class, constructor or YAML key. These libraries break between minor versions: DeepEval 2.9.3 has no `MCPUseMetric`, `ArenaGEval` or `MCPServer`; 4.3.4 has all three. Pin the version in the lockfile and say which version an example was checked against.
- **Every judge-backed metric receives an explicit model** built by one project factory that reads `EVAL_JUDGE_MODEL` (and provider) from config. DeepEval, `ArenaGEval` and Ragas `evaluate()` default to OpenAI; Giskard defaults to an OpenAI model. An omitted model is a silent provider switch or a mid-run auth crash. Record the resolved judge id and rubric version on every scored row.
- **Judge family.** Prefer a judge from a different model family than the generator (self-preference bias, see `rag-evaluator` judge section). If policy forces the same provider, calibrate against human labels and record that. Judges are a pinned, versioned model class; for high-stakes gates never the model instance being graded where avoidable (candidate-model and router gates: `llm-evaluation/reference/ab-testing.md` §2).
- **Banned-import rules apply to direct imports in eval code, never to transitive dependencies.** Ragas 0.4.4 hard-requires `langchain`, `langchain-community` and `langchain-openai` and imports them at `import ragas`; a lockfile-level "no LangChain" ban blocks every Ragas user.
- **Dispatch `eval-reviewer` after writing eval code**, and never claim an eval passed without the command and its output.

## Process (every evidence run)

1. **Pre-flight** before any score: current build/image, migrations applied, deterministic seed data, non-empty index, tool health, judge reachable, and one trace smoke (an eval case id appears in the trace backend). A score from a stale image or empty index measures the environment.
2. **Smoke** 1-2 cases, then the **full run on a frozen commit**.
3. **Account** for every planned case (table below). Write rows to disk, not stdout.
4. **Classify each red before changing anything:** PRODUCT (agent/tool/prompt wrong), TEST (assertion/fixture wrong), EVALUATOR (judge/metric artifact), OBSERVABILITY (evidence missing), ENVIRONMENT (quota, outage, stale data). Only PRODUCT reds justify agent changes.
5. **Verdict** names the flow, tier and dataset version it covers, nothing wider.

### Verdict precedence

| Deterministic checks | Judge | Case result |
|---|---|---|
| FAIL | any | FAIL (PRODUCT, or TEST if the assertion is wrong) |
| PASS | PASS | PASS |
| PASS | FAIL | FAIL on the judge-owned dimension; measure judge variance first |
| PASS | error / timeout | UNSCORED (EVALUATOR; DEPENDENCY if provider outage); stays in the denominator |
| could not run | any | SKIPPED / NOT RUN, never PASS |

**Evidence accounting:** each planned case lands in exactly one bucket (PASS, FAIL, UNSCORED, DEPENDENCY_FAILURE, SKIPPED); assert `sum(buckets) == planned`; zero scored cases raises; a run with any UNSCORED/DEPENDENCY/SKIPPED case is "NOT RUN (incomplete)", not PASS. A Giskard `Suite` result with `pass_rate is None` means nothing ran.

**Live-run preflight (R2+):** before the first case, make one real call through the same client, model id and endpoint the suite uses and require at least one result (a completion, a retrieved chunk). If it fails, record the whole run as NOT RUN with the preflight error and score nothing: a bad key, model id or endpoint otherwise shows up as a wall of FAIL or as zero scored cases that look like a regression.

### Judge variance and trials

- A single judge call is not a measurement. For a judge-gated metric that has shown variance, score **median-of-N (odd, default 3)** per case, gate on the mean of per-case medians, persist every trial score. Proof the trials run: a stubbed judge returning `[0, 1, 1]` passes at N=3 and fails at N=1.
- A lost trial is not a lost case; all trials lost to the provider is DEPENDENCY_FAILURE, never 0.0.
- Declare trial counts up front and report `k/N` per case. Any critical-safety miss in any trial is a miss.
- **No rerun-until-green:** never put `@pytest.mark.flaky(reruns=...)` (pytest-rerunfailures) on LLM-output assertions. A consistently blind judge needs a deterministic floor, not more trials.
- Runnable implementation (verdict, accounting, median-of-N, fail-closed baseline): `reference/ci-tiers.md` "Gate implementation".

### Thresholds and dataset discipline

- Thresholds live in one file with history. Never lower a gate, drop a case from numerator or denominator, soften a reference or switch metric mode to obtain a pass.
- **No ground-truth leakage:** feedback while iterating names the failed criterion ("expected 504, got 500"), never the expected output; golden inputs/answers never enter prompts, few-shots or corpora. Details and the pre-merge grep: `reference/golden-dataset.md`.
- Gate resolution is bounded by sample size: at N=100 a 0.85 pass rate has a ±0.07 95% CI, so a 100-case gate cannot resolve deltas under ~7 points. Compare variants with paired tests (`llm-evaluation/reference/ab-testing.md`).
- Case-count floors by risk tier: `ai-eval-designer` agent (canonical table). Per-flow thresholds: `reference/per-agent-thresholds.md`.

## Eval coverage map (where each eval type lives)

| Eval type | Canonical reference |
|---|---|
| Unit / workflow / contract / golden / E2E layers for AI code, fake and scripted models | `reference/pytest-harness.md` "Test layers" + "Scripted model" |
| Trajectory and tool-call correctness | `llm-evaluation/reference/trajectory-evaluation.md`; `reference/ragas-patterns.md`, `reference/deepeval-patterns.md`; ADK: `adk-eval-guide/reference/criteria-guide.md` |
| Multi-turn | "Multi-turn" below; ADK: `adk-eval-guide/reference/user-simulation.md` |
| Memory and session isolation | `reference/golden-dataset.md` "Isolation, memory and side effects" |
| Safety, prompt injection, red team | `reference/ci-tiers.md` "Hard CI blockers"; `reference/promptfoo-patterns.md`; `reference/giskard-patterns.md`; `ai-eval-designer` agent |
| Load, latency, cost | `reference/ci-tiers.md` "Load, latency and cost" |
| Retrieval and RAG metrics (formulas) | `llm-evaluation/reference/evaluation-metrics.md` §2 (canonical code + worked examples); concepts: `rag-evaluator` |
| Prompt regression and registry | `reference/langfuse-prompts.md` |
| Model / prompt comparison statistics | `llm-evaluation/reference/ab-testing.md` |
| CI promotion gates and release | `reference/ci-tiers.md`; rollout, canary, rollback: `deployment-ci-cd/reference/llmops-release-and-rollout.md` |

### Multi-turn

Use the cheapest shape that observes the behaviour: single-turn traces for classification, retrieval and authorization; simulated multi-turn only for clarification, coreference, changing facts, error recovery and jailbreak persistence. A simulator has a stated goal and a turn cap, never sees the expected answer, and its transcript plus tool trajectory are persisted so simulator variance can be told apart from product failure.

## Eval program: tool per job, dimensions, layers

Inventory first (features, corpora with embedding model + dimension, tools with read/write and audit need: `reference/eval-program-adoption.md`), then **one tool per job**, not one per vendor, chosen by the selection criteria there. Never add an LLM vendor only for judging.

| Job | Default here (pinned, Python 3.14.10) | Alternatives |
|---|---|---|
| Trajectory + final response | Framework-native: `adk eval` / `AgentEvaluator` (google-adk 2.15.0, `adk-eval-guide`); LangGraph: `llm-evaluation/reference/trajectory-evaluation.md` | LangSmith evals, OpenAI Evals |
| Test harness | pytest 9.2.0 + markers per tier (`reference/pytest-harness.md`); Vitest for TS | — |
| Judge metrics, agent metrics | DeepEval 4.3.4 (`reference/deepeval-patterns.md`) | Ragas agent metrics, custom rubric |
| RAG retrieval + grounding | Ragas 0.4.4 (`reference/ragas-patterns.md`) + canonical rank metrics (`llm-evaluation`) | DeepEval RAG metrics |
| Known-attack regression, red team | Promptfoo 0.126.0 (Node >= 22.22; `reference/promptfoo-patterns.md`); tiers and garak 0.17.1 / PyRIT 1.2.1 (Python < 3.15) in `reference/red-teaming.md` | — |
| Scenario / behavioural tests | giskard-checks 1.0.7 (`reference/giskard-patterns.md`) | DeepEval conversational tests |
| Tool / MCP contract, schema, auth | `reference/mcp-eval-patterns.md` + MCP Inspector | Promptfoo MCP plugin |
| Golden data, manifests, gate | `reference/golden-dataset.md`, `assets/schemas/`, `scripts/eval_gate.py` | — |
| Prompt registry | `PromptRegistry` wrapper, file backend in CI (`reference/langfuse-prompts.md`) | Langfuse 5.2.0, PromptLayer, cloud prompt store |
| Traces, replay, metrics | OpenTelemetry GenAI semconv + Prometheus/Grafana (`deployment-ci-cd/reference/ai-observability.md`) | Arize Phoenix (`arize-phoenix-otel` 0.17.3), Langfuse traces |
| Managed rubric eval (R3 / sampled prod) | your cloud's service: Vertex AI Gen AI Evaluation on GCP; Bedrock or Azure AI Foundry evaluation elsewhere. Verify the SDK surface before writing code; nightly, pre-release and ~1% sampled prod only | — |

### The 13 dimensions: mark each one, N/A explicitly

| # | Dimension | Decided by | Tool / gate | Tier |
|---|---|---|---|---|
| 1 | Trajectory | deterministic match | `tool_trajectory_avg_score`, Ragas `ToolCallAccuracy` | R1 (scripted model) / R2 (live) |
| 2 | Final response | judge + reference | `final_response_match_v2`, GEval, Ragas `FactualCorrectness` | R2 |
| 3 | Structured output | deterministic | Pydantic / JSON Schema on 100% of cases | R1, hard blocker |
| 4 | Grounding | judge | Ragas `Faithfulness`, `hallucinations_v1` | R1 deterministic citation check; judge R2 |
| 5 | Safety / injection | deterministic on tool calls + red team | Promptfoo, giskard-checks, `red-teaming.md` | R1 subset, R2/R3 full |
| 6 | Domain compliance (domain concerns: `reference/eval-program-adoption.md`) | detector on adversarial set | custom set, policy rubric | R1 critical, R2 |
| 7 | Data isolation | **deterministic only** | foreign ids in tool args, results, persisted rows = 0 | R1 hard blocker, R4 canary |
| 8 | Cost + latency | metrics | P95 and cost vs baseline (gate blocks > 1.2x); ADK `token_usage_v1`, `invocation_duration_v1` | R1/R2, L5 |
| 9 | Version traceability | result rows | dataset, prompt, model, tool-surface versions on every row (`eval_result.schema.json`) | every run |
| 10 | Tool / server safety | deterministic | five-layer tool suite, surface lock | R1 |
| 11 | Cross-feature consistency | judge over shared fixtures | GEval rubric | R2 |
| 12 | Tool-call efficiency | deterministic count | redundant calls <= 1 per trajectory; ADK `tool_call_count_v1` (informational, gate in your own code) | R1/R2 |
| 13 | Graceful degradation | failure injection | every tool with a fallback has a failing-path test (`reference/pytest-harness.md`) | R1 |

### Five layers vs CI tiers

| Layer | Runs | What runs | Budget |
|---|---|---|---|
| L1 dev loop | `eval-smoke` (pre-commit) / `eval-all-local` | lint, types, unit, 1-2 golden cases, prompt schema / full local suites | < 30 s / minutes |
| L2 PR / CI | R1 | deterministic metrics, scripted or fake models, file-backed prompts, path-routed red-team subset, isolation | < 5 min; judges never here |
| L3 local full stack | compose profiles `core`, `ai-agents`, `observability`, `prompt-registry` | end-to-end with trace store and metrics | on demand |
| L4 staging | R2 nightly, R3 pre-release | judged suites, managed rubric eval, multi-turn, full red team, human review, label promotion | nightly / per release |
| L5 production | R4 + online | sampled traces, 100% ops metrics, ~1% managed eval, canaries, label rollback | continuous |

R1-R4 detail and gate implementation: `reference/ci-tiers.md`. Thresholds are ADAPT defaults: `status: proposed` until ratified, then they gate (`reference/per-agent-thresholds.md`). L3-L5 cadences, compose profiles, domain concerns, anti-patterns, Day-1 definition of done and the organisation-owned adoption checklist (rollout, cost, owners): `reference/eval-program-adoption.md`.

## Reference Files

| File | When to use |
|------|-------------|
| `reference/pytest-harness.md` | Test layers, scripted fake model, ADK runner in tests, failure injection, pytest config |
| `reference/golden-dataset.md` | Dataset discipline, manifest + run metadata, closed case schema, assertion design, isolation/memory cases |
| `reference/ci-tiers.md` | R1-R4 tiers, marks, hard CI blockers, gate implementation, load/latency/cost |
| `reference/per-agent-thresholds.md` | Example per-flow thresholds, ADK score directions, rollback triggers |
| `reference/ragas-patterns.md` | Ragas 0.4 `ragas.metrics.collections`, FactualCorrectness contract, tool-call metrics |
| `reference/deepeval-patterns.md` | DeepEval test cases, MCP objects, agent/tool metrics, version notes |
| `reference/giskard-patterns.md` | Giskard v3 `giskard.checks` Scenario/Suite |
| `reference/promptfoo-patterns.md` | Promptfoo YAML and red-team configs |
| `reference/langfuse-prompts.md` | Prompt registry contract, lifecycle, prompt regression, promotion |
| `reference/mcp-eval-patterns.md` | MCP contract, isolation and audit-log suites |
| `reference/failure-mode-taxonomy.md` | Symptom → failure mode → eval tool routing |
| `reference/eval-program-adoption.md` | Inventory templates, tool-selection criteria, L3-L5 cadences, domain concerns, anti-patterns, Day-1 done, adoption checklist (organisation-owned) |
| `reference/red-teaming.md` | 14 threat classes → sub_class labels and Promptfoo plugin/strategy ids, R1-R4, hard blockers, R1 path routing, forced unsafe release exercise |
| `assets/schemas/` | 9 closed JSON Schemas: dataset_manifest, trajectory/rag/tool/redteam/regression cases, eval_result (= baseline format), thresholds, r1_routing |
| `assets/golden-scaffold/tests/{golden,eval}/` | Validator-clean example tree with `thresholds.yaml`, `r1-routing.yaml` and baselines |
| `assets/red-team/promptfoo/` | `promptfooconfig.r1-regression.yaml` (deterministic asserts, fixture target: R1) and `promptfooconfig.redteam-r2.yaml` (generated attacks: R2/R3) |
| `scripts/validate_golden.py`, `scripts/eval_gate.py` | Golden validator (GD001-GD020); gate `check` (EG002-EG014) and `route` (EG020). PEP 723 uv scripts, Python >=3.14,<3.15, `--selftest` |

## Example layout (not commands that exist in your repo)

`tests/golden/` for cases and manifest, `tests/eval/` for runners, one make/CI target per tier (`eval-r1`, `eval-r2`, ...). Create the targets you need; do not cite a target until it exists and you have run it.

## Telemetry

Disable eval-tool telemetry in CI and wherever eval data is sensitive: `DEEPEVAL_TELEMETRY_OPT_OUT=1`, `RAGAS_DO_NOT_TRACK=true`, `GISKARD_TELEMETRY_DISABLED=1`, `PROMPTFOO_DISABLE_TELEMETRY=1`. Set them in the CI job environment: a 2026-11-23 run without them attempted a PostHog analytics flush at session end.

## Verified pins (Python 3.14.10, 2026-11-23)

`deepeval==4.3.4`, `ragas==0.4.4`, `giskard-checks==1.0.7` (not `giskard-core`), `litellm==1.110.2`, `presidio-analyzer==2.2.366` + `presidio-anonymizer==2.2.366` (Python < 3.15: blocks a 3.15 eval image), `langfuse==5.2.0`, `pytest==9.2.0`, `pytest-asyncio==1.5.0`. All resolved together with uv 0.13.9. Google ADK eval environments are a separate lock: `google-adk` 2.15.1 requires `google-genai>=2.34,<3` and `opentelemetry-api<=1.45.2`, while standalone Gemini/LangChain services use `google-genai` 3.x (`langchain-google-genai` 4.5.2 needs `>=3.3`), so the two never share one lock. Deterministic parts were executed offline; LLM-judge metrics were exercised only against a labelled local stub judge (wiring, never quality). Re-executed 2026-11-23, all MOCKED: DeepEval `GEval` and `ToolCorrectnessMetric` with a stub `DeepEvalBaseLLM`; Ragas `Faithfulness` with a scripted `InstructorBaseRagasLLM` (1.0 supported, 0.5 with one unsupported claim) and `ToolCallAccuracy`; giskard-checks `Equals` scenarios; `adk eval` on a scripted-model agent (exit 0 / exit 1 on a wrong tool argument); Promptfoo 0.126.0 on Node 26.13.1 with a scripted provider (exit 0 / exit 100 on a failed assertion); its results fed to `scripts/eval_gate.py` (exit 0 / exit 1).

## Related Skills

- `llm-evaluation` — metric formulas (canonical), A/B statistics, trajectory scoring
- `rag-evaluator` — RAG metric concepts, judge calibration, eval at scale
- `adk-eval-guide` — ADK-native eval criteria, evalset schema, user simulation
- `deployment-ci-cd/reference/llmops-release-and-rollout.md` — eval-gated promotion, canary, rollback
- `deployment-ci-cd/reference/ai-observability.md` — tracing eval runs and prompt versions

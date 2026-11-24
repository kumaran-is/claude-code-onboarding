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
- **Judge family.** Prefer a judge from a different model family than the generator (self-preference bias, see `rag-evaluator` judge section). If policy forces the same provider, calibrate against human labels and record that.
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

## Example layout (not commands that exist in your repo)

`tests/golden/` for cases and manifest, `tests/eval/` for runners, one make/CI target per tier (`eval-r1`, `eval-r2`, ...). Create the targets you need; do not cite a target until it exists and you have run it.

## Telemetry

Disable eval-tool telemetry in CI and wherever eval data is sensitive: `DEEPEVAL_TELEMETRY_OPT_OUT=1`, `RAGAS_DO_NOT_TRACK=true`, `GISKARD_TELEMETRY_DISABLED=1`.

## Verified pins (Python 3.14.10, 2026-11-23)

`deepeval==4.3.4`, `ragas==0.4.4`, `giskard-checks==1.0.7` (not `giskard-core`), `litellm==1.110.2`, `presidio-analyzer==2.2.366` + `presidio-anonymizer==2.2.366` (Python < 3.15: blocks a 3.15 eval image), `langfuse==5.2.0`, `pytest==9.2.0`, `pytest-asyncio==1.5.0`. All resolved together with uv 0.13.9. Google ADK eval environments are a separate lock: `google-adk` 2.15.0 requires `google-genai>=2.34,<3` and `opentelemetry-api<=1.45.2`, while standalone Gemini/LangChain services use `google-genai` 3.x (`langchain-google-genai` 4.5.2 needs `>=3.3`), so the two never share one lock. Deterministic parts were executed offline; LLM-judge metrics were exercised only against a labelled local stub judge (wiring, never quality).

## Related Skills

- `llm-evaluation` — metric formulas (canonical), A/B statistics, trajectory scoring
- `rag-evaluator` — RAG metric concepts, judge calibration, eval at scale
- `adk-eval-guide` — ADK-native eval criteria, evalset schema, user simulation
- `deployment-ci-cd/reference/llmops-release-and-rollout.md` — eval-gated promotion, canary, rollback
- `deployment-ci-cd/reference/ai-observability.md` — tracing eval runs and prompt versions

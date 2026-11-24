---
name: adk-eval-guide
description: "Use when evaluating ADK agents, running adk eval, writing evalsets, configuring eval metrics, or debugging evaluation results. Covers the 13 documented criteria (trajectory, response match, coherence, semantic match, rubric-based, hallucinations, safety, user-simulator and multi-turn criteria) with score scales and directions, eval schema, LLM-as-judge configuration, user simulation, multimodal evaluation, and common eval failure causes."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: adk eval, adk evaluation, evalset, tool_trajectory_avg_score, response_match_score, final_response_match_v2, rubric_based, hallucinations_v1, safety_v1, LLM-as-judge, eval criteria, eval config
  related-skills: google-adk, agentic-ai-dev, python-dev
  domain: agentic-ai
  role: specialist
  scope: evaluation
  output-format: code
last-reviewed: "2026-11-23"
---

# ADK Evaluation Guide

## Iron Law

**UNIT TESTS USE A SCRIPTED FAKE MODEL; `adk eval` IS A LIVE-MODEL TIER, AND EVERY THRESHOLD IS READ ON ITS CRITERION'S OWN SCALE AND DIRECTION.**
`adk eval` calls the real agent model (and a judge for LLM-judged criteria): it is non-deterministic and costs money, so it runs in the nightly/pre-release tiers (`eval-guide/reference/ci-tiers.md`), not as a unit test. PR-time tests drive the agent with a scripted model (`eval-guide/reference/pytest-harness.md`). Every criterion is a minimum score (higher = better); `hallucinations_v1` is the share of supported sentences, so its gate is e.g. `≥ 0.9`, never `0` or `≤ 0.05`.

## Reference Files

| File | Contents |
|------|----------|
| `reference/criteria-guide.md` | Complete metrics reference — all 13 criteria with scales, match types, custom metrics, judge model config |
| `reference/user-simulation.md` | Dynamic conversation testing — ConversationScenario, user simulator config, compatible criteria |
| `reference/builtin-tools-eval.md` | google_search and model-internal tools — trajectory behavior, metric compatibility |
| `reference/multimodal-eval.md` | Multimodal inputs — evalset schema, built-in metric limitations, custom evaluator pattern |

---

## Process

1. **Define criteria** — choose metrics based on your goal (see Choosing the Right Criteria below); read `reference/criteria-guide.md` for all 13 criteria
2. **Write evalset** — create `evalset.json` with eval cases; include `intermediate_data.tool_uses` for every turn that expects tool calls
3. **Write eval config** — create `eval_config.json` with criteria thresholds; set `match_type` to `IN_ORDER` unless you need strict `EXACT` regression tests
4. **Run eval** — `adk eval ./app <path_to_evalset.json> --config_file_path=<path_to_config.json> --print_detailed_results`
5. **Interpret results** — identify which criteria failed; match failure symptom to cause (see Common Eval Failure Causes below)
6. **Fix the agent** — adjust prompts, tool descriptions, or agent instructions; do NOT widen thresholds to hide failures
7. **Fix the evalset if needed** — if expected trajectory doesn't match real agent behavior due to model variance, switch match type or use rubric-based criteria
8. **Rerun eval** — verify the fix resolves the specific failure without regressing other cases
9. **Expand coverage** — once current cases pass, add more eval cases incrementally
10. **Repeat** — expect 5–10 iterations per feature; each iteration makes the agent more reliable

---

## Choosing the Right Criteria

| Goal | Recommended Metric |
|------|--------------------|
| Regression testing / CI (fast, deterministic) | `tool_trajectory_avg_score` + `response_match_score` |
| Semantic response correctness (flexible phrasing OK) | `final_response_match_v2` |
| Response quality without reference answer | `rubric_based_final_response_quality_v1` |
| Validate tool usage reasoning | `rubric_based_tool_use_quality_v1` |
| Detect hallucinated claims | `hallucinations_v1` |
| Safety compliance | `safety_v1` |
| Dynamic multi-turn conversations | User simulation + `hallucinations_v1` / `safety_v1` |
| Multimodal input (image, audio, file) | `tool_trajectory_avg_score` + custom metric for response quality |

For complete metrics reference with config examples, see `reference/criteria-guide.md`.

---

## Running Evaluations

```bash
# Run eval directly via ADK CLI:
adk eval ./app <path_to_evalset.json> --config_file_path=<path_to_config.json> --print_detailed_results

# Run specific eval cases from a set:
adk eval ./app my_evalset.json:eval_1,eval_2

# With GCS storage:
adk eval ./app my_evalset.json --eval_storage_uri gs://my-bucket/evals

# Manage eval sets:
adk eval_set create <agent_path> <eval_set_id>
adk eval_set add_eval_case <agent_path> <eval_set_id> --scenarios_file <path> --session_input_file <path>
```

**CLI options** (`adk eval --help`, google-adk 2.15.0): `--config_file_path`, `--print_detailed_results`, `--eval_storage_uri`, `--num_runs`, `--parallelism`, `--log_level`. Since 2.13 `adk eval` exits 1 when any case fails or no results were produced (1.29 exited 0), so a CI step can gate on its exit code. `adk eval_set` also has `generate_eval_cases`.

---

## Key Patterns

| Pattern | What to Do |
|---------|-----------|
| Trajectory always 0 | Check if agent uses `google_search` — see `reference/builtin-tools-eval.md` |
| Extra tool calls failing EXACT match | Switch to `IN_ORDER` or `ANY_ORDER` match type |
| Non-deterministic scores | Run k trials and gate on the median (or k/N); set `judge_model_options.num_samples` for judge criteria. `temperature=0` reduces but does not remove variance |
| Multi-turn trajectory failures | Ensure `tool_uses` is defined for ALL turns, not just the final one |
| App name mismatch error | `App(name=...)` must match the directory name exactly |
| State type mismatch | `session_input.state` types must match Python initialization types |
| Image/audio not visible to judge | Built-in judge strips non-text; use custom metric — see `reference/multimodal-eval.md` |
| User simulation criteria mismatch | Only rubric/hallucination/safety criteria work with `conversation_scenario` |

---

## Common Eval Failure Causes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `tool_trajectory_avg_score` always 0 | Agent uses `google_search` (model-internal) | Remove trajectory metric; see `reference/builtin-tools-eval.md` |
| Missing `tool_uses` in intermediate turns | Trajectory expects match per invocation | Add expected tool calls to all turns |
| "Session not found" error | App name mismatch, or `run_async` before `create_session` in a custom runner | Ensure `App(name=...)` matches directory name; call `runner.session_service.create_session(app_name=runner.app_name, ...)` first |
| A 0.8 threshold on `response_evaluation_score` always passes | Criterion is on a 1-5 scale | Set the threshold on 1-5 (e.g. 4.0) |
| `hallucinations_v1` threshold 0 "passes" everything | Score is a minimum share of supported sentences | Gate at e.g. 0.9 |
| Score fluctuates between runs | Non-deterministic model and judge | k trials with a median; never rerun until green (`eval-guide/SKILL.md`) |
| Trajectory fails but tools are correct | Extra tools called | Switch to `IN_ORDER`/`ANY_ORDER` match type |
| Agent mentions data not in tool output | Hallucination | Tighten instructions; add `hallucinations_v1` |
| LLM judge ignores image/audio | `get_text_from_content()` skips non-text | Use custom metric with vision-capable judge |

---

## Documentation Sources

| Source | URL | Purpose |
|--------|-----|---------|
| Evaluation overview | `https://google.github.io/adk-docs/evaluate/index.md` | Getting started, CLI reference |
| Criteria reference | `https://google.github.io/adk-docs/evaluate/criteria/index.md` | All metric configs, custom metrics API |
| User simulation | `https://google.github.io/adk-docs/evaluate/user-sim/index.md` | ConversationScenario schema, simulator config |

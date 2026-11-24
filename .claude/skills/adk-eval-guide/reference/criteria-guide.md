# Evaluation Criteria Reference

## All 13 Criteria

Source: adk-docs `evaluate/criteria.md` (main branch, checked via Context7 2026-11-22). Re-check on your pinned google-adk: criteria are added between releases. Every threshold is a **minimum** (higher = better); the case passes when score ≥ threshold.

| Criterion | What it evaluates | Scale | Reference? | Judge? | User sim? |
|-----------|------------------|-------|-----------|--------|-----------|
| `tool_trajectory_avg_score` | Tool calls match expected list (`EXACT` / `IN_ORDER` / `ANY_ORDER`), averaged over invocations | 0-1 | Yes (`tool_uses`) | No | No |
| `response_match_score` | ROUGE-1 similarity to the reference response | 0-1 | Yes | No | No |
| `response_evaluation_score` | Vertex AI coherence score | **1-5** (a 0-1 threshold passes everything) | Yes | Yes | No |
| `final_response_match_v2` | Semantic match to reference; majority vote over `num_samples` | 0-1 | Yes | Yes | No |
| `rubric_based_final_response_quality_v1` | Final response quality against your rubrics | 0-1 | No (rubrics) | Yes | Yes |
| `rubric_based_tool_use_quality_v1` | Tool use quality against your rubrics | 0-1 | No (rubrics) | Yes | Yes |
| `rubric_based_multi_turn_trajectory_quality_v1` | Multi-turn trajectory quality against your rubrics | 0-1 | No (rubrics) | Yes | Yes |
| `hallucinations_v1` | Share of response sentences labelled `supported` or `not_applicable` against instructions, prompt, tool definitions and tool results | 0-1 (e.g. ≥ 0.9; **never `0`**) | No | Yes | Yes |
| `safety_v1` | Safety/harmlessness (needs `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`) | 0-1 | No | Yes | Yes |
| `per_turn_user_simulator_quality_v1` | Whether the user simulator follows the scenario | 0-1 | No | Yes | Yes |
| `multi_turn_task_success_v1` | Whether the agent achieves the conversation goal(s) | 0-1 | No | Yes | Yes |
| `multi_turn_trajectory_quality_v1` | Overall trajectory of the conversation | 0-1 | No | Yes | Yes |
| `multi_turn_tool_use_quality_v1` | Function calls made during the conversation | 0-1 | No | Yes | Yes |

Judge-based criteria are probabilistic: score them with k trials (median) and record the judge model; deterministic criteria (`tool_trajectory_avg_score`, `response_match_score`) and your own tool-log/state assertions outrank them (`eval-guide/SKILL.md`, verdict precedence). Per-flow threshold tables: `eval-guide/reference/per-agent-thresholds.md`.

Default when no config provided: `tool_trajectory_avg_score: 1.0` + `response_match_score: 0.8`

---

## Trajectory Match Types

`tool_trajectory_avg_score` supports three match types:

| Match Type | Behavior | When to Use |
|------------|----------|-------------|
| `EXACT` (default) | Agent must call exactly the tools listed, in exact order, no extras | Regression testing, strict workflow validation |
| `IN_ORDER` | Expected tools must appear in sequence; extra tool calls between them are allowed | Key actions must happen in order, but model may do extra work |
| `ANY_ORDER` | All expected tools must be called; order doesn't matter | Non-sequential workflows where all tools must fire |

**Proactivity Trajectory Gap:** LLMs often call extra tools not in the evalset (e.g., an extra `google_search`). `EXACT` match fails in this case. Prefer `IN_ORDER` for most evals unless you specifically need strict regression checks.

---

## Judge Model Configuration

All LLM-as-judge criteria accept `judge_model_options`:

```json
{
  "judge_model_options": {
    "judge_model": "<judge-model-id>",
    "num_samples": 5
  }
}
```

`<judge-model-id>` is a placeholder: set an id you checked on the current Gemini models page and record it with every result. If `judge_model` (or the user simulator's `model`) is omitted, `google-adk==2.15.0` silently falls back to `gemini-2.5-flash` (`evaluation/eval_metrics.py`, `simulation/llm_backed_user_simulator.py`), an older model than you probably intend.

- `judge_model` — model used to score responses
- `num_samples` — number of independent scoring samples; final score is majority vote. Default: 5. Higher values reduce LLM variance.

---

## Rubric and Hallucination Scoring

**Rubric scoring:** Each rubric returns yes (1.0) or no (0.0). Overall score = average across all rubrics and all invocations. Example rubric config:

```json
{
  "rubric_based_final_response_quality_v1": {
    "threshold": 0.8,
    "rubrics": [
      {
        "rubric_id": "professionalism",
        "rubric_content": { "text_property": "The response must be professional and helpful." }
      },
      {
        "rubric_id": "no_unconfirmed_booking",
        "rubric_content": { "text_property": "The agent must NEVER book without asking for confirmation." }
      }
    ]
  }
}
```

**Hallucination scoring:** Response is segmented into sentences, each labeled `supported`, `unsupported`, `contradictory`, `disputed`, or `not_applicable`. Score = percentage of `supported` + `not_applicable` sentences. A score of 1.0 means every factual claim is grounded in tool output.

---

## Full Configuration Example

```json
{
  "criteria": {
    "tool_trajectory_avg_score": {
      "threshold": 1.0,
      "match_type": "IN_ORDER"
    },
    "final_response_match_v2": {
      "threshold": 0.8,
      "judge_model_options": {
        "judge_model": "<judge-model-id>",
        "num_samples": 5
      }
    },
    "rubric_based_final_response_quality_v1": {
      "threshold": 0.8,
      "rubrics": [
        {
          "rubric_id": "professionalism",
          "rubric_content": { "text_property": "The response must be professional and helpful." }
        }
      ]
    },
    "hallucinations_v1": {
      "threshold": 0.9
    }
  }
}
```

Simple threshold shorthand is also valid: `"response_match_score": 0.8`

Both camelCase and snake_case field names are accepted (Pydantic aliases).

---

## Multiple runs (`multi_run_config`)

`num_samples` repeats the **judge**; `multi_run_config` repeats the **agent** (each run in a fresh session) and decides the case across runs. Fields read from google-adk 2.15.0 `evaluation/eval_config.py` (`extra="forbid"`: a misspelled key is rejected, not silently ignored): `num_runs`, `max_crashed_runs` (default 0: any crashed run fails the case), `cross_run_scoring` (`"mean_over_invocations"` default, `"mean_of_runs"`, `"min_over_runs"`, or `{"method": "pass_rate", "threshold": x}`), `cross_run_scoring_by_metric`, `cross_run_criteria` (`pass_rate`, `pass_at_k` = capability, `pass_hat_k` = reliability: all k runs pass; without a threshold the value is informational), `custom_methods`.

```json
{
  "criteria": {"tool_trajectory_avg_score": 1.0},
  "multi_run_config": {
    "num_runs": 3,
    "cross_run_scoring": "min_over_runs",
    "cross_run_criteria": [{"method": "pass_hat_k", "k": 3, "threshold": 1.0}]
  }
}
```

Executed with a scripted model whose second run of three used a wrong tool argument: this config failed the case (`adk eval` exit 1); `{"cross_run_scoring": {"method": "pass_rate", "threshold": 0.6}}` passed the same runs (exit 0). Gate critical and safety cases with `pass_hat_k` (any miss in any trial is a miss, `eval-guide` "Judge variance and trials"); use `pass_rate` or `pass_at_k` only for non-critical quality, and never raise `num_runs` until a case goes green.

---

## Custom Metrics

Register a custom metric function in `eval_config.json`:

```json
{
  "criteria": {
    "my_custom_metric": 0.8
  },
  "custom_metrics": {
    "my_custom_metric": {
      "code_config": {
        "name": "my_app.eval.my_module.my_metric_function"
      },
      "description": "Evaluates something built-in metrics cannot"
    }
  }
}
```

Custom metric functions receive full `Invocation` objects including all multimodal parts. See `multimodal-eval.md` for a complete implementation example.

---

## Deep Dive

- Fetch `https://google.github.io/adk-docs/evaluate/criteria/index.md` for complete config examples and the custom metrics API.

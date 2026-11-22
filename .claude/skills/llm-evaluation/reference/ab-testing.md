# A/B Testing, Model Comparison and Regression Detection

Statistics for prompt/model comparison and CI regression gates. All code here was executed (scipy 1.18.1, numpy 2.5.5; 7 pytest cases incl. the worked examples below); `RegressionDetector` is `mypy --strict` clean.

## Dependencies

```bash
uv add scipy numpy
uv add --dev pytest pytest-asyncio
```

## Pick the test by the design, not by habit

| Design | Data | Test |
|---|---|---|
| **Offline: both variants on the same golden cases** (prompt v3 vs v4, model A vs B) | paired scores per case id | paired t-test or Wilcoxon signed-rank on per-case deltas + paired bootstrap CI |
| Offline, pass/fail per case | paired binary | exact McNemar on discordant pairs (fixed vs newly broken) |
| **Online: different users see different variants** | independent arms | Welch t-test (scores) or two-proportion test; power by `n_per_arm` |

Running an independent-samples (Welch) test on paired golden-set data discards the pairing. Worked example (60 cases, simulated per-case difficulty, candidate +0.02): **Welch p = 0.548 vs paired t p = 0.0064, Wilcoxon p = 0.0084**, mean delta 0.015, bootstrap 95% CI [0.005, 0.025]. The same data is "no difference" or "real improvement" depending only on the test.

---

## Section 1: Comparison functions

```python
"""Variant comparison statistics.

Offline A/B on ONE golden set is paired data: both variants answered the same cases.
Use the paired tests here; use the independent-arm functions only for online A/B
where different users see different variants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class PairedResult:
    n: int
    mean_delta: float           # candidate - baseline, per case
    ci95: tuple[float, float]   # bootstrap CI of the mean delta
    p_ttest: float
    p_wilcoxon: float | None    # None when every delta is zero


def paired_compare(
    baseline: dict[str, float], candidate: dict[str, float], *, seed: int = 0, n_boot: int = 10_000
) -> PairedResult:
    """Scores keyed by case id. Refuses to compare different case sets."""
    if baseline.keys() != candidate.keys():
        missing = sorted(baseline.keys() ^ candidate.keys())
        raise ValueError(f"case sets differ: {missing[:5]} ...")
    ids = sorted(baseline)
    if len(ids) < 2:
        raise ValueError("need at least 2 paired cases")
    a = np.array([baseline[i] for i in ids])
    b = np.array([candidate[i] for i in ids])
    d = b - a
    rng = np.random.default_rng(seed)
    boots = rng.choice(d, size=(n_boot, d.size), replace=True).mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p_w = None if not d.any() else float(stats.wilcoxon(b, a).pvalue)
    return PairedResult(d.size, float(d.mean()), (float(lo), float(hi)),
                        float(stats.ttest_rel(b, a).pvalue), p_w)


def mcnemar_exact(baseline_pass: dict[str, bool], candidate_pass: dict[str, bool]) -> float:
    """Exact McNemar p-value for pass/fail outcomes on the same cases."""
    if baseline_pass.keys() != candidate_pass.keys():
        raise ValueError("case sets differ")
    fixed = sum(not baseline_pass[i] and candidate_pass[i] for i in baseline_pass)
    broke = sum(baseline_pass[i] and not candidate_pass[i] for i in baseline_pass)
    if fixed + broke == 0:
        return 1.0
    return float(stats.binomtest(broke, fixed + broke, 0.5).pvalue)


def n_per_arm(effect_size_d: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Independent two-arm sample size per arm (online A/B): 2 * ((z_a/2 + z_b) / d)^2."""
    z = float(stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power))   # float(): scipy returns a numpy scalar
    return math.ceil(2 * (z / effect_size_d) ** 2)


def pass_rate_ci95_half_width(pass_rate: float, n: int) -> float:
    """Normal-approximation half width; how small a delta a gate of n cases can resolve."""
    return 1.96 * math.sqrt(pass_rate * (1 - pass_rate) / n)


def online_ab(control: list[float], treatment: list[float], alpha: float = 0.05) -> dict[str, float | bool]:
    """Independent arms (different users per variant): Welch t-test + Cohen's d."""
    a, b = np.asarray(control, dtype=float), np.asarray(treatment, dtype=float)
    if min(a.size, b.size) < 2:
        raise ValueError("need at least 2 observations per arm")
    res = stats.ttest_ind(b, a, equal_var=False)
    pooled = math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    d = float((b.mean() - a.mean()) / pooled) if pooled > 0 else 0.0
    return {"p_value": float(res.pvalue), "cohens_d": d, "significant": bool(res.pvalue < alpha),
            "mean_delta": float(b.mean() - a.mean())}
```

**McNemar worked example:** 100 cases, 12 cases fixed by the candidate and 3 newly broken → exact p = 0.035. Report both counts; a fix that breaks 3 cases is not free even when significant.

**Sample size (online, independent arms):** n per arm = 2 · ((z₁₋α/₂ + z₁₋β) / d)². At α = 0.05, power 0.8: d = 0.5 → **63 per arm**, d = 0.2 → **393 per arm**. (A formula without the factor 2 returns 32 and 197: half the required sample.) "n ≥ 30" is a rule of thumb for the CLT, not a power calculation.

**Gate resolution (offline):** a pass rate of 0.85 on N cases has a 95% CI half width of ±0.099 (N=50), ±0.070 (N=100), ±0.049 (N=200), ±0.031 (N=500). A 100-case gate cannot resolve a 3-point change; use the paired tests above and an absolute floor.

---

## Section 2: Model and prompt comparison protocol

1. Same held-out dataset version, same judge model + rubric version, same tier, same trial count for both variants. Refuse the comparison otherwise (`paired_compare` raises on different case sets).
2. Deterministic and safety gates must be green for the candidate first; a quality win never offsets a safety regression.
3. Report per-case fixed vs newly broken, the paired p-value and the bootstrap CI of the delta, plus cost per task and p95 latency per variant.
4. Promote when the CI lower bound clears your non-inferiority margin (or zero for a claimed improvement) and the budgets hold. Never promote on a raw-mean win, on a tuning-set result, or on p alone with a negligible effect.
5. Judge-scored metrics: score both variants with the same median-of-3 trials (`eval-guide/SKILL.md`); position-randomize pairwise judges.
6. Online A/B: randomize by user or session (not request), fix duration and metrics in advance, correct for multiple metrics (e.g. Holm), and check sample-ratio mismatch before reading results.

Release mechanics (shadow/dual-run, canary, rollback): `deployment-ci-cd/reference/llmops-release-and-rollout.md`.

---

## Section 3: RegressionDetector (fail closed)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Baseline:
    key: dict[str, str]          # {"dataset": manifest sha, "judge": model@rubric, "tier": "R3"}
    metrics: dict[str, float]


class RegressionDetector:
    """Absolute-drop regression check against a versioned baseline. Fails closed."""

    def __init__(self, baseline: Baseline | None, max_drop: dict[str, float]) -> None:
        self.baseline = baseline
        self.max_drop = max_drop

    def check(self, run_key: dict[str, str], current: dict[str, float]) -> list[str]:
        if self.baseline is None:
            return ["no baseline for this dataset/judge/tier: record one deliberately"]
        if run_key != self.baseline.key:
            return [f"baseline key mismatch: run={run_key} baseline={self.baseline.key}"]
        failures: list[str] = []
        for metric, drop in self.max_drop.items():
            base = self.baseline.metrics.get(metric)
            cur = current.get(metric)
            if base is None or cur is None:
                failures.append(f"{metric}: missing from {'baseline' if base is None else 'run'}")
            elif cur < base - drop:
                failures.append(f"{metric}: {cur:.3f} < baseline {base:.3f} - {drop}")
        return failures
```

- Baselines are versioned files keyed by dataset version (manifest hash), judge model + rubric version and tier; a baseline is written only by an explicit, reviewed step and never overwritten in place.
- A missing baseline, a key mismatch or a metric missing on either side is a failure, never a skip. A 0.0 baseline is compared absolutely.
- Absolute drops of 0.02 on 50-200 cases are inside sampling noise; combine the detector with per-case flips and Section 1's paired test. Gate implementation with verdict precedence and accounting: `eval-guide/reference/ci-tiers.md`.

---

## Section 4: LangGraph eval integration

```python
# tests/eval/test_rag_regression.py
from collections.abc import Awaitable, Callable

import pytest

from eval.metrics import calculate_bertscore, calculate_bleu
from eval.rank_metrics import mean_defined, reciprocal_rank   # evaluation-metrics.md §2
from eval.regression import Baseline, RegressionDetector


async def run_eval(agent_fn: Callable[[dict[str, str]], Awaitable[dict]], cases: list[dict]) -> dict[str, float]:
    bleu, refs, hyps, rrs = [], [], [], []
    for case in cases:
        result = await agent_fn({"input": case["input"]})
        bleu.append(calculate_bleu(case["expected"], result["output"]))
        refs.append(case["expected"])
        hyps.append(result["output"])
        rrs.append(reciprocal_rank(result.get("retrieved_doc_ids", []), set(case["relevant_ids"])))
    mrr, excluded = mean_defined(rrs)
    if mrr is None:
        raise RuntimeError("no case has relevant ids: MRR was not measured")
    return {"bleu": sum(bleu) / len(bleu), "bertscore_f1": calculate_bertscore(refs, hyps)["f1"], "mrr": mrr}


@pytest.mark.r3
async def test_no_regression(rag_agent, heldout_cases, run_key, baseline: Baseline | None) -> None:
    detector = RegressionDetector(baseline, max_drop={"bleu": 0.02, "bertscore_f1": 0.02, "mrr": 0.02})
    failures = detector.check(run_key, await run_eval(rag_agent, heldout_cases))
    assert not failures, failures
```

Per-query relevance: each case carries its own `relevant_ids`; never pool relevant ids across queries.

---

## Section 5: ADK eval integration

```python
from google.adk.runners import InMemoryRunner
from google.genai import types


async def run_adk_eval(runner: InMemoryRunner, cases: list[dict], user_id: str = "eval-user") -> list[str]:
    outputs: list[str] = []
    for case in cases:
        # fresh session per case; run_async on a missing session raises SessionNotFoundError
        session = await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id)
        msg = types.Content(role="user", parts=[types.Part.from_text(text=case["input"])])
        final = ""
        async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=msg):
            if event.is_final_response() and event.content and event.content.parts:
                final = event.content.parts[0].text or ""
        outputs.append(final)
    return outputs
```

Checked against the adk-python Runner docs via Context7 (not executed; verify on your pinned google-adk). Score `outputs` with the same metric functions and `RegressionDetector` as Section 4.

---

## Section 6: Statistical rules

| Rule | Value | Rationale |
|------|-------|-----------|
| Offline variant comparison | paired test on per-case deltas + bootstrap CI | Same cases: pairing removes case difficulty variance |
| Pass/fail comparison | exact McNemar, report fixed and broken counts | Only discordant pairs carry information |
| Online sample size | `n_per_arm(d)`: 63 per arm at d = 0.5, 393 at d = 0.2 | Two independent arms (factor 2) |
| Significance (exploration / promotion) | p < 0.05 / p < 0.01 | Stricter bar for irreversible promotion |
| Effect size | report Cohen's d or the delta CI; reject negligible (d < 0.2) wins | Large samples make noise significant |
| Multiple metrics | Holm (or Bonferroni) correction | Many metrics → spurious wins |
| Regression gate | absolute floor + paired test, fail closed | Relative 5% on a small set is noise |

**Never promote on a p-value alone, and never on a tuning-set result.** Report the test used, n, effect size and CI with every claim.

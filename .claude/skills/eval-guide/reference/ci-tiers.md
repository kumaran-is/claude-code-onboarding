# CI Eval Tiers (R1-R4) and Gates

> A case runs in the cheapest tier that can prove it. A tier claims only what its workflow executed ("not run in R2", never "passed"). A cached green executes nothing and is never evidence.

## Tier structure

| Tier | When | What runs | Failure behaviour |
|------|------|-----------|-------------------|
| **R1 PR gate** | Every PR touching `<agent-src>/**`, `prompts/**`, `tests/golden/**`, `tests/eval/**`, the shared `conftest.py`, `pyproject.toml`, lockfile | Deterministic only: schema/contract, authorization, tenant isolation, safety-rule cases, scripted-fake-model workflow tests. **No live model, no LLM-graded Promptfoo** | Block merge |
| **R2 nightly** | Scheduled, against a staging-like environment | Live golden replay (declared k/N), RAG metrics, multi-turn, red-team scans (Promptfoo, Giskard), MCP contract/auth suites | Report; page security on any new attack success |
| **R3 pre-release** | Release candidate on a frozen SHA | Full held-out + safety set, paired baseline comparison, judge calibration check, cost and p95 latency within budget | Block release |
| **R4 canary probes** | Scheduled synthetic probes against a deployed environment (e.g. every 6 h against staging) | Isolation, injection, schema and unauthorized-tool probes; no destructive effects; missing credentials = NOT RUN | Page on any failure |

"Canary" means two different things: R4 here is a **scheduled synthetic probe suite**; a **traffic canary** (a small share of real traffic on a new prompt/model version) is a release step, see `deployment-ci-cd/reference/llmops-release-and-rollout.md`.

## Promotion gate (prompt, model, index or corpus change)

Promote only when, on the frozen SHA:
1. every deterministic and safety gate is green (hard blockers below);
2. held-out quality is not worse than the baseline by a paired test / lower CI bound (`llm-evaluation/reference/ab-testing.md`), plus absolute floors;
3. cost per task and p95 latency are within the declared budget;
4. the verdict names flow, tier and dataset version, nothing wider.

Then canary with rollback triggers (`per-agent-thresholds.md` "Production rollback triggers").

## Pytest marks

```python
@pytest.mark.r1      # deterministic PR gate (no live model)
@pytest.mark.r2      # nightly live replay
@pytest.mark.r3      # pre-release
@pytest.mark.r4      # deployed canary probes; skip with reason when creds absent (counts NOT RUN)
@pytest.mark.eval    # calls a live model or judge
```

Every eval test carries exactly one tier mark (module-level `pytestmark = [...]` counts). Marker registration: `pytest-harness.md`.

## GitHub Actions (R1)

```yaml
# .github/workflows/eval-r1.yml
name: Eval R1
on:
  pull_request:
    paths:
      - '<agent-src>/**'
      - 'prompts/**'
      - 'tests/golden/**'
      - 'tests/eval/**'
      - 'tests/conftest.py'
      - 'pyproject.toml'
      - 'uv.lock'
jobs:
  r1:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-commit-sha>  # vX.Y.Z — SHA-pinned per python-ci-supply-chain.md
      - name: R1 deterministic gate
        run: uv run pytest -m r1 --tb=short --junit-xml=reports/pytest-r1.xml
      - name: Upload results
        if: always()
        uses: actions/upload-artifact@<full-commit-sha>  # vX.Y.Z
        with:
          name: r1-eval-results
          path: reports/
```

Pin `uses:` to full commit SHAs (`deployment-ci-cd/reference/python-ci-supply-chain.md`). Do not pipe the gate into `tail`; the step must see pytest's exit code. Offline eval tests must not read real secrets (gate it with a self-tested check).

## Gate implementation (verdict, accounting, trials, baseline)

Executed: 12 pytest cases (judge cannot upgrade a deterministic FAIL; `[0,1,1]` passes at N=3 and fails at N=1; all trials lost = DEPENDENCY_FAILURE; SKIPPED never PASS; dropped case and zero-scored run raise; baseline fails closed on missing/mismatched/absent metric), `mypy --strict` clean.

```python
import statistics
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum


class Bucket(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNSCORED = "UNSCORED"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    bucket: Bucket
    trial_scores: tuple[float, ...] = ()
    reason: str = ""


class JudgeUnavailable(Exception):
    """Raised by the judge adapter on provider outage / timeout."""


def case_verdict(case_id: str, deterministic_ok: bool | None, judge: Callable[[], float] | None,
                 *, trials: int = 3, threshold: float = 0.85) -> CaseResult:
    if deterministic_ok is None:
        return CaseResult(case_id, Bucket.SKIPPED, reason="deterministic check did not run")
    if not deterministic_ok:
        return CaseResult(case_id, Bucket.FAIL, reason="deterministic")   # judge never upgrades
    if judge is None:
        return CaseResult(case_id, Bucket.PASS)
    if trials % 2 == 0:
        raise ValueError("use an odd trial count so the median is a real trial score")
    scores: list[float] = []
    for _ in range(trials):
        try:
            scores.append(judge())
        except JudgeUnavailable:
            continue                                     # a lost trial is not a lost case
    if not scores:
        return CaseResult(case_id, Bucket.DEPENDENCY_FAILURE, reason="all judge trials lost")
    median = statistics.median(scores)
    bucket = Bucket.PASS if median >= threshold else Bucket.FAIL
    return CaseResult(case_id, bucket, tuple(scores), reason=f"median={median:.3f}")


def account(planned: Sequence[str], results: Sequence[CaseResult]) -> dict[str, int]:
    if sorted(r.case_id for r in results) != sorted(planned):
        raise RuntimeError(f"accounting mismatch: planned={len(planned)} recorded={len(results)}")
    counts = Counter(r.bucket.value for r in results)
    if counts[Bucket.PASS] + counts[Bucket.FAIL] == 0:
        raise RuntimeError("zero scored cases: the run measured nothing")
    return dict(counts)


def run_verdict(counts: dict[str, int]) -> str:
    if counts.get(Bucket.FAIL, 0):
        return "FAIL"
    if any(counts.get(b, 0) for b in (Bucket.UNSCORED, Bucket.DEPENDENCY_FAILURE, Bucket.SKIPPED)):
        return "NOT RUN (incomplete)"
    return "PASS"


def compare_to_baseline(current: dict[str, float], baseline: dict[str, float] | None, *,
                        run_key: dict[str, str], baseline_key: dict[str, str] | None,
                        max_drop: dict[str, float]) -> list[str]:
    """Fail closed. Key = dataset version (manifest hash), judge model + rubric version, tier."""
    if baseline is None or baseline_key is None:
        return ["no baseline for this dataset/judge/tier: record one deliberately"]
    if run_key != baseline_key:
        return [f"baseline key mismatch: run={run_key} baseline={baseline_key}"]
    failures = []
    for metric, drop in max_drop.items():
        if metric not in baseline:
            failures.append(f"{metric}: missing from baseline")
        elif metric not in current:
            failures.append(f"{metric}: missing from run")
        elif current[metric] < baseline[metric] - drop:          # absolute compare; 0.0 included
            failures.append(f"{metric}: {current[metric]:.3f} < {baseline[metric]:.3f} - {drop}")
    return failures
```

Baselines are versioned files keyed by `(dataset_version, judge, tier)`, written only by an explicit, reviewed step and never overwritten. On 50-200 cases an absolute delta of 0.02 is inside sampling noise (±0.05-0.10); pair the delta gate with per-case flips and the paired test.

## Flaky cases and failure injection

- Repeated trials are declared up front and reported as k/N; no `@pytest.mark.flaky(reruns=N)` on LLM-output assertions.
- A case named for failure injection (`timeout`, `unavailable`, `error`, `rejected`, ...) that asserts an exact error must inject that failure deterministically (fake/stub dependency) or be `xfail` citing an **open** blocker issue. Lint both: failure-named + strict error assertion + not xfail = fail; xfail without an open blocker = fail.

## Load, latency and cost

- Measure p50/p95 end to end per flow; a timeout counts at its cutoff value and as a failure.
- Run heavy or live suites serially on an idle runner; a red under load is not evidence until reproduced idle. Pace live-model suites to the provider quota instead of blind retries; 429/quota errors are ENVIRONMENT.
- Concurrency tests assert per-session isolation and idempotent writes under parallel identical requests.
- Report production-workflow cost and evaluator (judge) cost separately. A missing counter is "unknown", never zero. Compare before/after only on the same dataset, seed, model and tier.

## Hard CI blockers (each needs ≥ 1 R1 case, reported on its own, never inside an aggregate)

1. Tenant A reads tenant B's data (tool args, retrieval results, persisted rows)
2. Prompt injection (direct, or indirect via retrieved document / tool output) steers an unintended tool call
3. Regulated-policy bypass: a restricted action completes without the required review flag
4. MCP / tool accepts a cross-tenant input id
5. Unauthorized tool call succeeds
6. RAG retrieves a chunk outside the caller's scope
7. Structured output fails JSON Schema validation
8. A write tool ships without an audit-record call
9. A new agent tool has zero red-team cases
10. PII (email, phone, card, national id) appears in model output, a tool argument or a log line where the case forbids it

Any of these failing blocks the merge. Assert them on the tool-call log, retrieval span and persisted state, not on reply text. A judge or metric score can never clear a blocker (verdict precedence: no deterministic failure, then judge).

## Privacy blocker with Presidio (deterministic, executed)

```python
from functools import cache

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

BLOCKING = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE"]


@cache
def analyzer() -> AnalyzerEngine:
    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],   # pin the model wheel in the lock
    }).create_engine()
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])


def pii_findings(text: str) -> list[RecognizerResult]:
    # PHONE_NUMBER scores 0.4 without context words: a 0.5 threshold silently drops phones
    return analyzer().analyze(text=text, language="en", entities=BLOCKING, score_threshold=0.35)
```

Executed (presidio-analyzer/anonymizer 2.2.366, spaCy 3.8.18 with `en_core_web_sm` 3.8.0, Python 3.14.10): an answer containing an email and a phone number produced `EMAIL_ADDRESS` (1.0) and `PHONE_NUMBER` (0.4); at `score_threshold=0.5` the phone was missed and the test failed; a clean answer produced no findings; a card number scored 1.0. A known-invalid SSN (`078-05-1120`) was reported only as `PHONE_NUMBER`: test each entity you rely on with your own fixtures. Redaction (`presidio_anonymizer.AnonymizerEngine`) is for logs and traces; a redacted output never turns a failing case into a pass. Presidio 2.2.366 requires Python < 3.15: an eval image on 3.15 cannot install it, so pin the eval job's Python. Its analyzer and anonymizer ship separate `RecognizerResult` classes: convert before passing analyzer results to `anonymize()` (mypy `arg-type` otherwise).

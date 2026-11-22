# LLMOps: Release and Rollout of Prompts, Models and AI Config

Canonical home for how AI behaviour changes reach production. Framework-neutral: the rules apply whether prompts live in Git, Langfuse or another registry, and whether the model is called directly, through LangChain/LangGraph or through Google ADK.

Related homes (do not duplicate them here):
- Prompt registry code, labels, cache TTL, degraded tiers: `eval-guide/reference/langfuse-prompts.md`
- Eval tiers R1–R4 and CI gates: `eval-guide/reference/ci-tiers.md`; per-agent thresholds and rollback triggers: `eval-guide/reference/per-agent-thresholds.md`
- Paired comparison statistics: `llm-evaluation/reference/ab-testing.md`
- Model ids, provider abstraction, probing an id: `agentic-ai-dev/reference/llm-inference-and-model-routing.md`
- AI tracing, metrics, SLOs, alerts: `deployment-ci-cd/reference/ai-observability.md`
- Launch checklist: `ai-launch-check`; incident procedure: `ai-incident-response`

---

## 1. Three things change AI behaviour — only one creates a revision

| Change | Example | Creates a deploy revision? | Canary mechanism |
|--------|---------|----------------------------|------------------|
| Code / image | new tool, parser, retrieval change | yes | revision traffic split (Cloud Run `--no-traffic` + tag, then `update-traffic`) |
| Prompt / AI config | registry label moved, flag flipped, temperature, model id in config | **no** | split requests by label / flag value inside the service |
| Provider model | provider updates an alias or retires a version | **no, and not yours** | pin versions; treat a provider change as a migration (section 6) |

A revision canary with an HTTP health check cannot see the second and third rows. Every span carries prompt name, version, label and model id so any change can be attributed (`ai-observability.md`).

---

## 2. Versioning rules

| Asset | Rule |
|-------|------|
| Prompts | Git is the source of truth (PR-reviewed); the registry holds immutable numbered versions; production fetches by label, never `latest`; rollback = move the label, never delete a version |
| Prompt + tools | A prompt that names tools is bumped in the same change as the tool set; CI asserts the prompt's tool names equal the registered tools |
| Model ids | Environment config only: no code default, no literal in code, tests, IaC variables, CI env blocks or eval configs; startup fails on a missing value; tests compare against loaded settings (`env-config-validation.md`) |
| Sampling / reasoning config | Versioned with the prompt (same registry config or the same PR), never tweaked ad hoc in production |
| Eval baseline | Stored per (model id, prompt version); a release compares against the baseline for exactly that pair |
| Provenance | Record for every release: Git SHA, image digest, prompt name + version + content hash, model id per backend, flag states, eval run id and dataset version |

---

## 3. Eval-gated promotion

```
PR ──► R1/R2 offline evals (fake + recorded models) ──► merge
   ──► seed registry version N (label: development)
   ──► R3 pre-release: held-out golden set on version N + candidate model, live
        deterministic gates (schema, safety, isolation, tool args) MUST pass
        paired comparison vs production baseline: ship on a non-inferior lower bound
   ──► label: staging ──► staging eval against the deployed candidate + human approval
   ──► traffic canary (section 4) ──► label: production
```

- Promote only after the eval ran on **that exact version**, and only while the registry is healthy (the service would otherwise be serving cached or bundled fallbacks).
- The production deploy job `needs:` the eval job, and the eval job is a required status check. For a revision release, run the eval against the candidate's no-traffic tagged URL before shifting traffic.
- A CI step that pipes tests into `tee` captures `${PIPESTATUS[0]}`, uploads artefacts with `if: always()`, and fails in a separate step on the captured code. Every `uses:` is SHA-pinned (`python-ci-supply-chain.md`).
- Nondeterminism is not "flaky": rescope an assertion to a behavioural invariant in the same change; never retry-until-green.

---

## 4. Traffic canary for prompt / config changes

1. Route N% of requests (start 1–10%) to the candidate label or flag value, sticky per conversation; tag every span and metric with the arm.
2. Judge on AI signals, not HTTP health: fallback rate, output-schema reject rate, refusal rate, deterministic safety-gate hits, cost per request, p95 latency, plus sampled outputs passing the golden judge.
3. Decide with a pre-declared rule over a fixed window; declare the limits before the canary starts.
4. Rollback = move the label / flag back. It reaches running instances only after the registry cache TTL: state that TTL in the runbook and alert if the old version is still served after TTL + margin.

Deterministic gate (executed: 4 tests pass, `ruff` and `mypy --strict` clean):

```python
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["PROMOTE", "ROLLBACK", "EXTEND"]


@dataclass(frozen=True)
class ArmStats:
    requests: int
    fallback: int          # degraded/fallback responses served
    schema_reject: int     # outputs that failed schema validation
    refusal: int
    safety_hits: int       # deterministic safety-gate blocks
    cost_usd: float
    p95_ms: float


@dataclass(frozen=True)
class Limits:
    min_requests: int = 500            # per arm before any verdict
    max_rate_delta: float = 0.01       # absolute increase allowed per rate metric
    max_cost_ratio: float = 1.10       # candidate cost/request vs control
    max_p95_ratio: float = 1.20


def _rate(n: int, d: int) -> float:
    return n / d if d else 0.0


def canary_verdict(control: ArmStats, candidate: ArmStats, lim: Limits = Limits()) -> tuple[Verdict, list[str]]:
    if min(control.requests, candidate.requests) < lim.min_requests:
        return "EXTEND", ["not enough traffic for a verdict"]
    breaches: list[str] = []
    for name in ("fallback", "schema_reject", "refusal", "safety_hits"):
        delta = _rate(getattr(candidate, name), candidate.requests) - _rate(getattr(control, name), control.requests)
        if delta > lim.max_rate_delta:
            breaches.append(f"{name} rate +{delta:.3f}")
    cost_ratio = (candidate.cost_usd / candidate.requests) / max(control.cost_usd / control.requests, 1e-12)
    if cost_ratio > lim.max_cost_ratio:
        breaches.append(f"cost/request x{cost_ratio:.2f}")
    if candidate.p95_ms > control.p95_ms * lim.max_p95_ratio:
        breaches.append(f"p95 {candidate.p95_ms:.0f}ms vs {control.p95_ms:.0f}ms")
    return ("ROLLBACK", breaches) if breaches else ("PROMOTE", [])
```

The limits shown are examples, not recommendations: calibrate them from your own control-arm variance. Rare-event metrics (safety hits) need far more traffic than the minimum above; for those, rely on the pre-release safety gate, not the canary.

"Canary" also names a scheduled synthetic probe suite (R4 in `ci-tiers.md`) that pages on failure. Keep both; they catch different things.

---

## 5. Flags and kill switches

- New consequential AI paths (anything that writes, sends, spends or decides for a user) ship default-OFF behind a flag until their gate passes.
- The kill switch returns the normal contract in degraded form: JSON with the documented fallback fields set, or a stream with exactly one terminal `error` frame and a fixed code (`streaming-protocols` §6a). Never a 5xx or a hang; HTTP status unchanged.
- Killing an AI path never disables deterministic safety, authorization or manual paths.
- Flags are evaluated server-side and recorded on the span.

---

## 6. Provider and model migration

1. Probe the exact new id on every backend you deploy to, next to a known-good control (a model available on one endpoint is not proven on another; image/TTS ids need a model-metadata or minimal real call, not a text call).
2. Shadow or dual-run on the same golden set and a sample of real traffic (shadow outputs are never shown to users or acted on).
3. Compare per metric: quality, safety recall, schema-reject rate, refusal rate, cost, p95 — with the paired method in `ab-testing.md`.
4. Switch behind a flag with the canary in section 4; keep the old model configured until the window closes.
5. Record the date, ids and results (provenance, section 2). Treat a provider-announced alias change or deprecation the same way.

---

## 7. Credentials and quota governance

| Rule | Detail |
|------|--------|
| Keyless where possible | Managed endpoints in deployed environments use workload identity / ADC; no provider key exists there; a startup assertion refuses an (environment, auth) mismatch |
| Third-party keys | Secret manager, mounted at runtime; never in the image, prompt, trace, log, test fixture or CI env block |
| Rotation | Documented owner and rotation procedure; a leaked key is revoked and rotated before any other incident step |
| Budgets | Per request, per execution tree / session (not per sub-agent) and per organization per period; calibrated from measured p95/p99; exhaustion must not leave half-applied side effects |
| Quotas | Know your provider quotas per model and region; alert before exhaustion; 429 handling is bounded backoff with jitter, then a fixed user-facing degraded response |
| Discoverability | Every deployed AI service is scraped by the metrics system; alerts per organization on cost anomaly, fallback rate and retry/loop runaway |

---

## 8. Feedback loop into the golden set

- A feedback event carries message id, trace id, prompt version and model id — never content.
- Flow: feedback → sampled human triage → verified failure → new golden case by reviewed PR → regression run. Never auto-add feedback to the golden set; never edit a case to make it pass.
- A stopped or incomplete answer is never added as a completed example.
- The new case must fail on the version that produced the incident and pass on the fix.

---

## 9. Incident recovery for AI releases

1. Contain: move the label / flag back or flip the kill switch; confirm the old version is served after the cache TTL (check spans, not the registry UI).
2. Capture the crime scene: prompt name, version, label and content hash; model id per backend; flag states; registry tier served (live, cached, stale, bundled); eval run id of the release.
3. Classify: prompt regression, model/provider change, retrieval/data change, tool change, credential leak (revoke/rotate first), provider quota or outage (429 vs 5xx).
4. Add the failing case to the golden set (section 8) and re-run the gate before re-promoting.
Full procedure: `ai-incident-response`.

---

## 10. Release checklist

- [ ] Change classified (code / prompt-config / provider model) and the matching canary mechanism chosen
- [ ] Model ids only in environment config; probe run on every target backend
- [ ] R3 gate green on the exact prompt version + model id; deterministic gates green; paired comparison non-inferior
- [ ] Canary limits declared before start; spans tagged with arm, prompt version, model id
- [ ] Rollback path tested; cache TTL stated in the runbook
- [ ] Kill switch returns the degraded contract; safety paths unaffected
- [ ] Provenance recorded (Git SHA, digest, prompt version + hash, model id, flags, eval run)
- [ ] Budgets and quota alerts in place for the new path

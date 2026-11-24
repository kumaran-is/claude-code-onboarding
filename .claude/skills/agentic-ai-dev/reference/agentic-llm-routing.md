# Agentic AI LLM Routing & Multi-Provider Management

Canonical home for model selection and routing (tiers FAST/STANDARD/STRONG, approved-model registry and lifecycle, policy gate, cascades, failover, upgrades, decision contract, routing telemetry; MSR requirement ids map to §1–§19 here) for Python agent services, with LangChain v1 wiring and LiteLLM as one optional gateway. Related rules have their own canonical homes:

| Topic | Canonical home |
|---|---|
| Model client, typed errors, one retry layer, failover vs escalation table, cache keys, `RunBudget` (G6, G12) | `llm-inference-and-model-routing.md` |
| Cost budgets, quality-adjusted cost | `agentic-cost-optimization.md` |
| Candidate-model and judge-model evals, golden sets, thresholds | `eval-guide` (`reference/golden-dataset.md`, `per-agent-thresholds.md`), `llm-evaluation` |
| Shadow, canary, ramp, rollback, flags (§15, §9 here) | `deployment-ci-cd/reference/llmops-release-and-rollout.md` §4–§6 |
| AI inventory / AI BOM, provider exit, approvals (G20, governance §9, §12) | `ai-governance` skill (`ai_bom` record) |
| Routing spans and cost metrics (§17 here) | `deployment-ci-cd/reference/ai-observability.md` |
| Embedding and reranker choice (never routed dynamically) | `rag-architect`, `vector-database` |

Routing selects **reasoning capability only**. Authorization, approvals, spend limits and side-effect gates stay deterministic and server-side (§11, G2).

## 1. Tiers: config, not code

| Tier | Capability contract | Config key |
|---|---|---|
| `FAST` | Extraction, classification, normalisation, routing classifiers; tool calling + structured output where required | `MODEL_FAST` |
| `STANDARD` | Default chat + tools; floor for images/video and long context | `MODEL_STANDARD` |
| `STRONG` | High-stakes synthesis, conflicting evidence, complex planning; final escalation tier | `MODEL_STRONG` |
| `embedding` | Pinned per corpus; a change is a re-index migration, never a route | `EMBEDDING_MODEL` |

Specialised classes are pinned, never routed: reranker per retrieval pipeline (evaluated on context precision / nDCG), classifier/moderation (evaluated on recall of the harmful class first), vision/document/speech (per modality and language; `STANDARD` floor for image/video), judge (pinned; for high-stakes gates not the instance it grades where avoidable; calibrated on human labels — `eval-guide`), open-weight/self-hosted (you own patching, scaling, safety tuning and evals; weights provenance in the `ai_bom`).

Tiers are per-capability contracts: `FAST` for extraction may resolve to a different config than `FAST` for multilingual chat. Each key names a registry `config_id` (§2), not a raw provider string; the resolver is the only place provider/model strings appear (§3). Prices and context limits come from the registry with a "checked on" date, never from a table in code.

## 2. Approved-model registry (field meanings and lifecycle: §13)

Routing chooses only among entries in state `deployed`. Keep the registry in Git (reviewed, versioned, rollbackable — §19); it is the model section of the G20 inventory, and the governance `ai_bom` lists each `config_id` as a `foundation_model` / `embedding_model` / `judge_model` component rather than copying these fields.

```json
{
  "config_id": "invoice-extract-fast-2026-10",
  "provider": "<provider>", "hosting": "cloud_managed",
  "model_id": "<exact model id>", "pinned_version": "<dated snapshot or version>",
  "model_class": "generation", "tier": "FAST",
  "capabilities_approved": [{"capability": "invoice_extraction", "eval_run_id": "<run>", "date": "2026-10-28"}],
  "modalities": ["text"], "context_window": 128000, "max_output": 8192,
  "structured_output": true, "tool_calling": true,
  "regions": ["eu"], "data_terms": "<zero-retention / training-use terms ref>", "allowed_data_classes": "confidential",
  "cost_profile": {"as_of": "2026-10-28", "source": "<pricing page>"}, "latency_profile": {"p50_ms": 0, "p95_ms": 0},
  "rate_limits": "<quota ref>", "safety_eval": "<red-team run id>", "owner": "<named person>",
  "state": "deployed", "deprecation_date": null, "retirement_date": null, "successor": null,
  "generation_params": {"max_output_tokens": 2048}
}
```

Machine-checked: schema `../assets/model-registry.schema.json`, full example `../assets/examples/model-registry.example.json`, and `python3 ../scripts/validate_model_registry.py [--json] [--today YYYY-MM-DD] FILE...` (stdlib; exit 0 valid / 1 invalid / 2 usage, IO, JSON or schema error; `--selftest` runs the example, a `regulated` positive case and 20 negative cases). It checks structure and consistency only: a valid registry does not prove an eval passed or a vendor review happened. Run it in CI on every registry change and at service startup (refuse to start on exit ≠ 0).

Load-time rules (the validator and the service's registry loader both refuse, fail closed):

| Rule | Source |
|---|---|
| `model_id` / `pinned_version` is not an alias (`latest`, `default`, `-preview`, `-exp`, auto-upgrading endpoint) | §15, G11 |
| `deployed` requires ≥ 1 `capabilities_approved` with an eval run id **and** a `safety_eval` run id | §13, §14 |
| Unique `config_id`; known `tier`, `model_class`, `state`, data class; embedding/reranker/judge are `n.a.` (pinned, never tier-routed), generation has a tier | §1, §13 |
| Provider may not train on non-public data without a contractual opt-out | §11 |
| Each deployed `STANDARD`/`STRONG` capability has a second deployed same-tier config or is listed in `non_ai_fallbacks` | §16 |
| `deprecated` has a deprecation date and a successor or retirement date; a successor exists and is not retired/suspended; evidence is not future-dated | §13 |
| Generation parameters are part of the pinned config, identical across environments unless an approved experiment says otherwise | §15 |
| A provider deprecation notice creates a dated migration task ahead of the cut-off | §13 |

Lifecycle states and allowed use (`proposed → evaluating → approved → deployed → deprecated → retired`; `suspended` on incident) are defined in §13; only `deployed` (and `deprecated` for existing routes) serve production, `approved` serves shadow and canary only.

## 3. Routing pipeline: reference core (§11, §12, §16)

Egress authorization → policy gate → capability routing → tier → approved-config resolution → execution → verification → escalation | failover. Capability routing (which agent owns the work, §7 intent routing) and tier routing are separate decisions, never one opaque router prompt. A recognised emergency or safety phrase maps in the gate to an approved deterministic action with no model wait. Full module and tests: `../assets/reference-router/` (`msr_router.py`, `test_msr_router.py`; run `uv run --locked pytest -q` there, pins in `pyproject.toml` + `uv.lock`). Stdlib + pydantic core, provider injected; executed on Python 3.14.10 + pydantic 2.14.4 with **37 test cases, MOCKED PROVIDER** (fake providers, fake verifier, fake classifier, an idempotent draft store) and 10 mutation negative controls (alias check, state filter, data-class filter, verifier-timeout-as-PASS, new operation id per escalation, ignored budget, forced tier below floor, ignored cascade flag, classifier floor, classifier timeout under-route), each of which made the suite fail. Egress authorization (`.claude/skills/ai-playbook/reference/data-governance-privacy.md` (DGP §4, §6): permission to read data is not permission to send it): pass an `EgressPolicy` (the capability's §6.1 egress declaration, the request's class/purpose tags, secrets count and redaction status, and one `ProviderApproval` per provider with type, approved classes, regions, training terms and re-review date). A request whose secrets, classes, purposes, region or redaction status fail the declaration returns `EGRESS_BLOCKED` with `EgressBlock` codes and **no provider call**; providers whose approval does not cover the request's classes and region (third-party APIs never above Internal, providers that may train only Public, unknown classes counted as Confidential, expired approvals) are filtered out, so failover and escalation never leave the approved set and end on the non-AI path. 11 egress test cases (executed on Python 3.14.10, 2026-11-24) and 12 mutation negative controls (each check removed in a copy, including log-and-allow) all made the suite fail.

```python
def policy_gate(req: RouteRequest, *, long_context_threshold: int, high_impact: frozenset[str]) -> GateResult:
    """Deterministic floors from SEPARATE policy signals. No model call, no single risk score."""
    tier, reasons, cascade = "FAST", [], True
    s = req.signals
    if s.safety_risk == "high" or s.irreversibility == "high" or s.financial_authority_required \
            or req.capability in high_impact:
        tier, cascade = "STRONG", False                    # policy minimum; no cheap-first cascade
        reasons.append(Reason.SAFETY_OVERRIDE)
    if req.modalities & {"image", "video"} and TIERS.index(tier) < 1:
        tier = "STANDARD"; reasons.append(Reason.MULTIMODAL_MINIMUM)
    if req.context_tokens >= long_context_threshold and TIERS.index(tier) < 1:
        tier = "STANDARD"; reasons.append(Reason.LONG_CONTEXT_MINIMUM)
    return GateResult(tier, cascade, tuple(reasons) or (Reason.STATIC_ROUTE,))


def candidates(self, tier: str, req: RouteRequest, ov: Overrides) -> list[ModelConfig]:
    """Hard constraints are filters, never weights (§11)."""
    return [e for e in self._entries
            if e.tier == tier and e.state in LIVE_STATES
            and req.capability in e.capabilities_approved
            and DATA_CLASSES.index(req.data_class) <= DATA_CLASSES.index(e.allowed_data_class)
            and req.region in e.regions and req.modalities <= e.modalities
            and e.config_id not in ov.suspended_configs and e.provider not in ov.suspended_providers]
```

Execution loop rules (all asserted by the tests):

| Situation | Behaviour | Reason code |
|---|---|---|
| Selected tier | `max(static capability tier, policy minimum)`; a forced-tier override can raise, never lower, the floor | `STATIC_ROUTE`, `FORCED_TIER` |
| `ProviderUnavailable` (timeout, 5xx, short-retry 429 only) | Next approved config of the **same tier** for this capability, data class and region | `PROVIDER_UNAVAILABLE` |
| No approved same-tier config answers | Documented conservative fallback: next **higher** approved tier, else the non-AI path with visible degradation; never a lower, `evaluating` or unapproved config | `NO_APPROVED_EQUIVALENT` |
| Verifier says schema/business rule failed | Escalate one tier with the **same `operation_id`** (the store saw one draft); if cascade is not allowed or this is the final tier → human review | `SCHEMA_VALIDATION_FAILED`, `FINAL_TIER_FAILED` |
| Verifier timeout or inconclusive | `INSUFFICIENT`, never `PASS` | `VERIFIER_TIMEOUT`, `INSUFFICIENT_EVIDENCE` |
| Budget (attempts, cost) spent | Stop model calls, return a visible degraded outcome; never a cheaper unevaluated model | `BUDGET_EXHAUSTED` |
| Version rollback | Suspend the new `config_id` in the registry; the warm incumbent is selected with no code change | — |

Escalation side-effect safety beyond the draft store (operation id, idempotency key, created entity ids, sent-message ids reused across attempts) is G4: `tool-execution-safety.md`. The request-tree budget shared by router, sub-agents, retries and fallbacks is `RunBudget` in `llm-inference-and-model-routing.md` §9.

## 4. Decision record and reason codes (§17)

Every decision emits the §17 record (request id, capability, the six policy signals, modalities, context bucket, latency class, minimum/selected tier, `resolved_config_id`, `allow_cascade`, verification strategy, reason codes, `routing_policy_version`) plus an attempt trail (config, tier, cost, latency, verification outcome). Rules:

- Reason codes are a closed `StrEnum` versioned with the routing policy; an unknown code is a test failure.
- The record carries features, never raw prompts, documents, images or PII (§17). The test asserts the serialised record has no prompt field.
- Never cache routing decisions (§16). Response-cache keys: `llm-inference-and-model-routing.md` §8.
- Never show routing metadata to end users. Emit it as span attributes per §17 next to the GenAI semantic-convention attributes in `ai-observability.md`.

## 5. Model construction (LangChain v1)

**File:** `src/<service>/llm/client.py`

```python
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


def chat_model(entry: RegistryEntry) -> BaseChatModel:
    """The only place that constructs chat models. `entry` is a deployed §2 registry record chosen by the resolver."""
    return init_chat_model(f"{entry.provider}:{entry.model_id}", **entry.generation_params)
```

- `init_chat_model("provider:model")` (or `create_agent(model=...)`) replaces factories that pick a class by substring. The provider integration package (e.g. `langchain-anthropic`) is installed and pinned.
- Sampling/reasoning params come from the registry entry (`llm-inference-and-model-routing.md` §3). No global `temperature=0`.
- Exactly one retry layer: turn off SDK retries (`max_retries=0` where offered) when middleware or `with_retry` retries.

## 6. Error mapping and failover in LangChain

Map each integration's exceptions once to the taxonomy (`UnavailableError`, `RateLimitedError`, `QuotaExhaustedError`, `InvalidRequestError`) by exception class and HTTP status, never by `str(exc)`. The transient tuple feeds `retry_on=` / `exceptions_to_handle=`:

```python
TRANSIENT: tuple[type[Exception], ...] = (
    # fill from the pinned SDKs: timeout, connection, 5xx, overloaded, short-retry rate limit classes
)
```

Use `TransientFallbackMiddleware` + `ModelRetryMiddleware(retry_on=TRANSIENT, on_failure="error")` from `agentic-templates-resilience.md`. Do not use a bare `primary.with_fallbacks([...])`: `exceptions_to_handle` defaults to `(Exception,)` (verified in langchain-core 1.8.4), so a 400, an auth error or a context overflow would switch provider. When composing manually, bind tools/structured output to **each** candidate and pass `exceptions_to_handle=TRANSIENT`; every candidate is a `deployed` same-tier registry entry for the capability:

```python
model = chat_model(primary).bind_tools(tools).with_fallbacks(
    [chat_model(equivalent).bind_tools(tools)],      # approved same-tier equivalent, same data class/region
    exceptions_to_handle=TRANSIENT,
)
```

## 7. LLM complexity router (§12)

Only when rules cannot decide the tier and measured savings justify the extra call. Deterministic policy first, then a `FAST` classifier with a deadline, a validated label and a conservative (over-route) fallback:

```python
class RouteLabel(BaseModel):
    tier: Literal["FAST", "STANDARD", "STRONG"]


def max_tier(a: str, b: str) -> str:
    return max(a, b, key=TIERS.index)


async def classify_tier(f: RouteFeatures, classifier: Any, timeout_s: float, floor: str,
                        transient: tuple[type[Exception], ...]) -> tuple[str, Reason]:
    """f holds sanitized features only (capability, modality, size bucket, flags), never the raw message."""
    try:
        async with asyncio.timeout(timeout_s):
            raw = await classifier.ainvoke(f"capability={f.capability} size={f.size_bucket} images={f.has_images}")
        label = RouteLabel.model_validate(raw)
    except TimeoutError:
        return max_tier("STANDARD", floor), Reason.ROUTER_TIMEOUT
    except ValidationError:
        return max_tier("STANDARD", floor), Reason.ROUTER_INVALID
    except transient:
        return max_tier("STANDARD", floor), Reason.ROUTER_UNAVAILABLE
    return max_tier(label.tier, floor), Reason.ROUTER_MODEL      # never below the policy floor
```

`classifier` is `chat_model(fast_cfg).with_structured_output(RouteLabel)`; `transient` is the `TRANSIENT` tuple from §6. Timeout, invalid label and a transient error over-route to `STANDARD` (or the floor); a non-transient error (auth) raises so misconfiguration is loud; the prompt carries features only (all asserted with a fake classifier). Evaluate the router against cheapest-passing-tier labels (§14): under-routing is weighted above over-routing, and safety under-routing blocks go-live. Learned routers only after §18 phase 5 shadow evidence.

**Intent routing without generation** (choosing the capability, not the tier): embedding prototypes per label, cosine similarity with a threshold **and** a margin over the runner-up, explicit "no match" to a deterministic fallback, prototypes warmed at startup through a bounded pool; the embedding model id is part of the prototype cache key. Never use it to estimate difficulty or authority.

## 8. LiteLLM Router as the gateway (optional)

Provider-neutral option when a service needs many providers behind one client. Verified by reading `litellm==1.110.2` source (`macosx_11_0_arm64` wheel sha256 `a002de99…eb769`, PyPI 2026-11-20; re-checked 2026-11-24; `litellm/router.py`, `router_utils/fallback_event_handlers.py`, `types/router.py`); behaviour below was executed (`../assets/reference-router/test_litellm_router.py`) with mocked deployments (`mock_response` / `mock_testing_content_policy_fallbacks`, no network; 9 pytest cases, MOCKED PROVIDER), each removed control paired with a test showing the unsafe default.

Map one LiteLLM `model_name` group to one `(capability, tier)` and put only `deployed` same-tier registry configs in it (load balancing across deployments of the **same** config is fine).

| `Router(...)` parameter (1.110.2) | Default | Required setting | Why |
|---|---|---|---|
| `fallbacks=[{"cap.standard": ["cap.standard-b"]}]` | `[]` | Same-tier approved equivalents only | §12 failover |
| `default_fallbacks` | `None` | **Do not set** | Applies across all groups: a STANDARD request was served by the FAST group (executed) |
| `content_policy_fallbacks` | `[]` | **`[{group: []}]` for every group** (explicit empty) | A refusal is not an outage (§12). Left unset, a `ContentPolicyViolationError` falls through to the generic `fallbacks` and is served by the other model (executed) |
| `context_window_fallbacks` | `[]` | **`[{group: []}]` for every group**, plus the `LONG_CONTEXT_MINIMUM` floor and `enable_pre_call_checks=True` | Context size is a routing floor, not a failure. Left unset, `ContextWindowExceededError` uses the generic `fallbacks` (executed) |
| `fallback_on_unsupported_params` | `True` | **`False`** | With `True`, a provider 400 is served by the fallback model (executed; `is_bad_request_without_fallback`) |
| `num_retries` / `retry_policy` | 2 / `None` | Set explicitly; `RetryPolicy(BadRequestErrorRetries=0, AuthenticationErrorRetries=0, ContentPolicyViolationErrorRetries=0)`; the only retry layer | One retry layer |
| `fallback_access_check` | `None` | Reject targets not approved for the request's data class/region | §16: a rejected target is skipped and the original 5xx surfaces (executed). Async path only |
| `fallback_budget_check` | `None` | Re-check the shared request budget | §16. Async path only |
| `enable_mid_stream_fallback_continuation` | `False` | Keep `False` | One answer would mix two models |
| `model_group_alias` | `{}` | No floating aliases | §15 |
| `max_fallbacks`, `timeout`, `cooldown_time`, `allowed_fails` | 5 / `None` / 1 s / `None` | Set per capability from measured p99 | §16 timeouts, breakers |

The policy gate, tier floors, verifier and escalation stay in the application (§3): LiteLLM performs failover and load balancing only, not quality escalation. A 429 is failed over like a 5xx (executed): LiteLLM cannot tell a short rate limit from an exhausted quota, so quota exhaustion must be caught by the provider budget and `fallback_budget_check`, not by failover.

Resilience rules that apply with or without a gateway (§16): each `STANDARD` and `STRONG` capability has ≥ 1 approved same-tier equivalent or a documented non-AI fallback (an ADAPT decision per capability: each equivalent doubles eval, red-team and vendor-review work); prompts and tool schemas are tested on every equivalent, with provider-specific prompt variants versioned explicitly; a model change and its prompt change are versioned and evaluated together (§15); scheduled canary evals against pinned versions detect silent provider-side drift (`eval-guide/reference/ci-tiers.md`).

## 9. Flags, overrides, kill switches

`ROUTING_ENABLED`, `ROUTING_SHADOW_MODE`, `ROUTING_CAPABILITIES`, `CASCADE_ENABLED`, `ROUTER_MODEL_ENABLED`, `FAILOVER_ENABLED`; overrides force tier (raise only), force `STRONG`, suspend a `config_id`, suspend a provider. They change without a deploy, are audited and drilled; the platform kill switch (G10) sits above them. Flag mechanics: `llmops-release-and-rollout.md` §5.

## 10. Prompt caching and cost

- Prefix ordering (all providers): static system text → tool schemas → examples → dynamic content. Anthropic marks breakpoints with `{"cache_control": {"type": "ephemeral"}}` on a content block; anything interpolated there breaks the cache. Measure cache-read tokens before claiming savings (Gemini reports `cached_content_token_count`). Response/semantic caches: `agentic-caching-patterns.md`.
- Cost from **measured** usage (input, cached input, output incl. reasoning tokens) and the registry's price reference keyed by `config_id`; unknown id → `cost_unknown_model`, never another model's price. Track cost per successful task and per route (§16, §17), not cost per token.
- Circuit breaking: shared breaker in `python-dev/reference/reliability-idempotency-retries-outbox.md` §3; an open breaker counts as `UnavailableError`.

## 11. Selection rule and hard constraints

Scope: every model invoked in production or on production data (hosted API, cloud-managed, self-hosted; generation, embedding, reranking, classification, vision, speech, judge). Normative words: **must / must not** = mandatory; **should** = default, deviation needs a recorded reason; **may** = optional. This section implements G11, G12, G20 and the fallback rule in G6; the guardrails win on conflict.

**Governing rule:** use the cheapest, lowest-latency approved model configuration that passes the capability's eval and safety gates. Optimise only inside the policy-valid set, in this order:

```text
hard policy constraints (safety, authority, privacy, residency, provider terms)
  → required quality on the capability's evals
  → modality / context / tool / structured-output compatibility
  → latency objective
  → cost
```

Safety, authority, privacy and compliance are **filters, not weights**: never traded against cost or latency. A cheaper model that fails a safety gate is not a candidate.

| Hard constraint (pass/fail) | Fails when |
|---|---|
| Data residency / region | Inference or logging leaves an approved region for the data class |
| Provider terms | Customer data may be used for training, or retention exceeds policy, without a contractual opt-out |
| Data classification | The capability sends a class above the config's `allowed_data_classes` |
| Regulated data | Sent to a config not declared `allowed_data_classes: regulated`, or to a provider without its own `regulated` egress approval line (Legal/Privacy approval for the purpose and jurisdiction, regime-specific agreement where required, residency pinned). Third-party APIs never receive it. The ladder is public < internal < confidential < restricted < regulated; the egress check still requires each class explicitly. Executed: `test_regulated_request_needs_a_registry_config_declared_for_regulated` (mutant without `regulated` fails it) |
| Safety gate | Any safety-critical eval below its floor; any red-team hard blocker |
| Modality / context | Required modality or validated context size unsupported |
| Contract features | Structured output or tool calling required but unreliable in evals |
| Vendor risk | Security / privacy / financial-viability review not passed |

| Optimised criterion (ranked after the hard constraints) | Measure |
|---|---|
| Quality on **your** evals | Task success, faithfulness, schema pass rate, per language |
| Cost | Quality-adjusted cost per successful task, not per token |
| Latency | p95 / p99 under representative load; time-to-first-token for streaming |
| Reliability | Error and timeout rate; quota headroom |
| Operability | Observability, versioning guarantees, deprecation notice period |
| Portability | Ease of failover to an equivalent model |

Public benchmarks are a shortlist filter. Selection rests on your own capability evals (§14).

## 12. Floors, strategies, cascades and failover order

**Default floors (ADAPT: ratify the threshold).** Compute them from measurable features (token bucket, document count, tool-result count, conflicting-fact count, image count, schema complexity) before any learned complexity estimate. The reference `policy_gate` (§3) implements the first three.

```text
image/video reasoning present            → minimum STANDARD
document_count or context ≥ <threshold>  → minimum STANDARD
safety / high-impact capability          → minimum per policy (often STRONG) + no cheap-first cascade
structured extraction with validator     → FAST allowed, cascade allowed
```

The gate keeps the six policy signals separate (`safety_risk`, `privacy_risk`, `legal_risk`, `financial_authority_required`, `irreversibility`, `requires_human_approval`), never one generic risk score. Routes that workflow state, capability, modality and context size already determine are deterministic and skip any LLM router.

| Strategy | How | Use when | Do not use when |
|---|---|---|---|
| Static per-capability | Each capability maps to one tier/config in configuration | Default start; low difficulty variance; regulated paths | Traffic mixes trivially easy and very hard requests at volume |
| Deterministic rules | Floors and overrides from policy signals, modality, context size, schema complexity | Safety, long-context and multimodal floors; known workflow states | Never skipped: always applied before any other strategy |
| Semantic routing | Embedding similarity to labelled intent examples (§7) | Choosing the **capability** when phrasing varies | Estimating reasoning difficulty or authority |
| Small-model classifier | `FAST` model returns a typed tier decision (§7) | Rules and semantics cannot resolve the tier and measured savings justify the extra call | Obvious routes; latency-critical paths without a timeout budget |
| Verification-driven cascade | Try a lower tier; accept only if an objective verifier passes; else escalate | Objective validators exist (schemas, business rules, reconciliation) | Safety-critical, high-impact or subjective outputs |
| Fallback chain | Same-tier equivalent on provider failure | Every production capability | As a substitute for quality escalation |
| Learned routing | Router trained on cheapest-passing-tier labels | Only after representative traffic, trustworthy labels, a deterministic baseline and shadow proof of benefit | Early stages; low traffic |

Any LLM router has a hard timeout from a ratified latency budget, structured output and minimised input (§17); invalid output or timeout falls back to a deterministic **conservative** route (over-route, never under-route); it never bypasses the policy gate and records reason codes (§7).

| Category | Cheap-first cascade |
|---|---|
| Structured extraction, normalisation, classification, formatting with a strict validator | **Allowed** |
| Ranking, comparison, drafting where an objective check exists | **Conditional**: only with that check |
| Safety-critical triage, high-impact financial/legal/privacy interpretation, conflicting evidence, negotiation | **Not allowed**: start at the policy minimum tier |

A cascade is valid only when verification is actually available. **Verifier unavailable, timed out or inconclusive is never `PASS`.**

| Verifier outcome | Behaviour |
|---|---|
| Schema invalid | Retry or escalate if policy permits |
| Business rule fails | Escalate, safe failure or human review |
| Model judge disagrees with the deterministic verifier | Deterministic verifier wins |
| Insufficient evidence | `INSUFFICIENT`, not `PASS` |
| Final tier fails | Human review or safe failure per capability policy |

**Request limits (every request).** Max model attempts · max total latency · max route cost · max loop count · deterministic final fallback. Parallel fan-out declares `max_parallel_branches` and shares one cost budget across the whole execution tree (G5). Escalation never replays a committed side effect (G4): operation id, idempotency key, workflow checkpoint, created entity ids, successful tool results, sent-message ids and financial operation ids are reused across attempts; a higher tier **reuses** the draft a lower tier created, never creates a second one.

**Quality escalation and provider failover are separate mechanisms** (triggers in `llm-inference-and-model-routing.md` §6): escalation is `FAST → STANDARD → STRONG → human review / safe failure`; failover is tier T on config A unavailable → approved same-tier config B. An outage does not make the request harder; a quality failure does not mean the provider is down. Failover order:

1. Select the policy-valid tier.
2. Resolve the approved config for tier + capability + modality + region.
3. If unavailable, use the approved same-tier equivalent for this capability.
4. If none, use the documented conservative fallback (a higher approved tier or the non-AI path).
5. Never weaken the policy gate.
6. Never silently fall back to an unevaluated or weaker configuration.

Fallback configs **must** pass the same capability eval and safety gate as the primary (G6). One that has not is not a fallback: route to the deterministic or manual path and make the degradation visible.

## 13. Registry field semantics and lifecycle

| Field | Meaning (the JSON in §2; schema `../assets/model-registry.schema.json`) |
|---|---|
| `config_id` | Stable id of model + version + parameters; settings and tiers name this, never a provider string |
| `provider` / `hosting` | Vendor, cloud-managed or self-hosted |
| `model_id` + `pinned_version` | Exact version or dated snapshot, never an alias |
| `model_class`, `tier` | generation / embedding / reranker / classifier / vision / speech / judge; FAST / STANDARD / STRONG / `n.a.` |
| `capabilities_approved` | Capabilities with passing evals, each with eval run id and date |
| `modalities`, `context_window`, `max_output` | As **validated**, not as advertised |
| `structured_output`, `tool_calling` | Supported **and** validated in evals |
| `regions`, `data_terms`, `allowed_data_classes` | Where inference and any logging occur; retention, training use, abuse-monitoring access, zero-retention options; highest class it may receive |
| `cost_profile`, `latency_profile`, `rate_limits` | Unit prices with an as-of date (refreshed); measured p50/p95 under your traffic; provisioned quotas |
| `safety_eval`, `owner` | Red-team and safety-gate run id; a named person |
| `state`, `deprecation_date`, `retirement_date`, `successor` | Lifecycle below; dates from the provider notice or internal decision |

```text
proposed → evaluating → approved → deployed (canary → general) → deprecated → retired
                 ↘ rejected                        ↘ suspended (incident)
```

| State | Entry criteria | Allowed use |
|---|---|---|
| `proposed` | Request with use case and data classes | None |
| `evaluating` | Vendor risk review started; data terms known | Offline evals on approved, sanitised data only |
| `approved` | Capability evals + safety gate pass; vendor review passed; owner named | Shadow, canary |
| `deployed` | Canary passed (§15) | Production for listed capabilities only |
| `deprecated` | Provider notice or successor approved | Existing routes only; no new capabilities; dated migration plan |
| `suspended` | Incident, provider breach, regression | No traffic; fallback active |
| `retired` | Traffic at zero; references removed | None |

A provider deprecation notice **must** create a migration task dated well ahead of the provider's cut-off. The registry doubles as the AI inventory required by G20.

## 14. Candidate-model gates and router evaluation

Cheapest-passing-tier protocol, per capability golden set:

```text
for each representative case in the capability golden set:
    run every candidate tier/config
    score with the capability's evaluators
    label = cheapest config that passes
```

Each label records its source (`deterministic_verifier` / `human_reviewer` / `approved_model_evaluator`), the evaluation-policy, routing-policy and dataset versions and the pass/fail criteria. Prefer deterministic validators for objective tasks and human labels for subjective or high-impact ones; model judges are supporting evidence, not ground truth.

| Gate a candidate must pass | Requirement (defaults to ratify) |
|---|---|
| Capability quality | ≥ the capability's ratified thresholds; no slice regression > 2 pts vs the incumbent |
| Safety | Safety-recall and red-team suites at floor; **under-routing of a high-risk class is a blocker** |
| Structured output | Schema pass rate ≥ 99 % where code consumes the output (G3) |
| Isolation | Zero cross-scope leaks in tool/retrieval scenarios |
| Languages | Every production input language evaluated or routed away (G7) |
| Latency / cost | Within the capability SLO and budget at p95 |
| Robustness | Same gates at production temperature and parameters; repeated runs for variance |

Router evaluation: compare the router-selected tier with the cheapest passing tier on the golden set and in shadow, counting correct / over-route / under-route. Under-routing is weighted above over-routing; safety under-routing blocks go-live. Paired comparison method: `llm-evaluation/reference/ab-testing.md` §2 (items 8–10).

## 15. Pinning, upgrades, canary and rollback

- Production references exact versions or dated snapshots. `latest`, `default`, `-preview` and auto-upgrading endpoints are forbidden unless their behaviour is explicitly controlled and evaluated (G11; rejected by the registry validator and the reference router).
- The pinned version is configuration, not code, identical across environments for the same capability unless an approved experiment says otherwise. Generation parameters (temperature, max tokens, reasoning and safety settings) are part of the pinned config.
- A model change and the prompt change that accompanies it are versioned together and evaluated together.

Upgrade process (mechanics: `deployment-ci-cd/reference/llmops-release-and-rollout.md` §4–§6):

1. Registry entry → `evaluating` (vendor terms re-checked if the provider changed).
2. Offline evals: capability + safety + structured output + languages vs the incumbent (§14).
3. Shadow: the new config runs on mirrored production traffic; outputs logged, never served.
4. Canary: `<1–5 %>` of traffic, low-risk capabilities first, with automatic rollback triggers.
5. Ramp 25 % → 50 % → 100 %, gated on quality, latency, cost, escalation and human-override rates.
6. Keep the incumbent warm for the rollback window.
7. Incumbent → `deprecated` → `retired`.

Rollback triggers (defaults to ratify): quality metric drop > 2 pts on any slice · safety gate miss · p95 latency > 1.5× incumbent · cost per success > 1.2× forecast · fallback or escalation rate > 1.5× incumbent. Rollback is a registry change: suspend the new `config_id` and the warm incumbent is selected with no code change (§3).

## 16. Resilience, budgets and caches

| Resilience concern | Requirement |
|---|---|
| Abstraction | One provider adapter / resolver behind the AI gateway; no direct provider SDK calls from features (G13) |
| Equivalents | Each `STANDARD` and `STRONG` capability has ≥ 1 approved same-tier equivalent or a documented non-AI fallback (validator rule, §2) |
| Health | Circuit breakers per provider + model; error, timeout and quota signals |
| Timeouts | Per capability, below the user-facing SLO; retries with jittered backoff and a retry budget (`llm-inference-and-model-routing.md` §5) |
| Outage mode | Failover per §12; platform kill switch per provider (G10, §9) |
| Prompt portability | Prompts and tool schemas tested on every equivalent; provider-specific prompt variants versioned explicitly |
| Behaviour drift | Scheduled canary evals against pinned versions detect silent provider-side changes |
| Data terms | Failover never sends data to a provider not approved for that data class |

Multi-provider is not free: each equivalent doubles eval, red-team and vendor-review work. ADAPT: decide per capability whether a second provider or a non-AI fallback is the better resilience investment.

| Budget scope | Control |
|---|---|
| Per request / execution tree | Token, cost, attempt and latency budget shared by router, sub-agents, retries and fallbacks (G5; `RunBudget`) |
| Per capability | Monthly cost budget; p95 cost-per-success SLO |
| Per tenant / org | Rate limit, concurrency cap, period budget; one tenant cannot starve others |
| Per provider | Quota allocation by capability priority; reserved headroom for critical paths |
| Per environment | Hard caps in non-production; alerts before provider quota exhaustion |

On exhaustion: stop further model calls, preserve canonical state, return a visible degraded or human-review outcome. Never silently drop to a cheaper unevaluated model to stay within budget. Track quality-adjusted cost (cost per successful task); do not forecast routing savings without a measured baseline.

| Cache | Safe use | Caveats |
|---|---|---|
| Provider prompt-prefix | Stable system prompts, tool definitions, large shared reference context | Static-first ordering; no per-user data in the prefix unless the cache is scoped to that user; check provider retention terms |
| Exact-match response | Deterministic, non-personal, low-stakes outputs | Key includes model config, prompt version, parameters and scope |
| Semantic response | Public or org-wide FAQ-style answers | **Not** for personalised, ACL-varying, high-stakes, time-sensitive or tool-calling outputs; similarity threshold evaluated for false hits; no cross-scope sharing |
| Registry / policy / capability metadata | Always safe | Invalidate on config change |
| Routing decisions | **Do not cache** | Risk, authority, modality and context differ per request |

Every response-cache key includes `scope_id`, `config_id`, prompt version and relevant parameters (`answer_cache_key`, `llm-inference-and-model-routing.md` §8). Purge on prompt or model change, ACL change and deletion requests. Trace cache hits like model calls.

## 17. Decision contract, input minimisation and routing telemetry

```json
{
  "request_id": "<uuid>", "capability": "<capability>",
  "policy_signals": {"safety_risk": "low|medium|high", "privacy_risk": "low|medium|high",
                     "legal_risk": "low|medium|high", "financial_authority_required": false,
                     "irreversibility": "low|medium|high", "requires_human_approval": false},
  "modalities": ["text"], "context_bucket": "small|medium|large", "latency_class": "interactive|batch",
  "minimum_tier": "FAST|STANDARD|STRONG", "selected_tier": "FAST|STANDARD|STRONG",
  "resolved_config_id": "<config_id>", "allow_cascade": false,
  "verification_strategy": ["schema", "business_rules"],
  "reason_codes": ["<CODE>"], "routing_policy_version": "<v>"
}
```

Reason codes are a closed, versioned enum; the reference router's set is `STATIC_ROUTE`, `SAFETY_OVERRIDE`, `MULTIMODAL_MINIMUM`, `LONG_CONTEXT_MINIMUM`, `FORCED_TIER`, `ROUTER_TIMEOUT`, `ROUTER_INVALID`, `ROUTER_UNAVAILABLE`, `ROUTER_MODEL`, `SCHEMA_VALIDATION_FAILED`, `INSUFFICIENT_EVIDENCE`, `VERIFIER_TIMEOUT`, `PROVIDER_UNAVAILABLE`, `NO_APPROVED_EQUIVALENT`, `BUDGET_EXHAUSTED`, `FINAL_TIER_FAILED`, `EGRESS_POLICY_BLOCK`. Internal routing metadata is never shown to end users.

**Input minimisation.** The router receives the smallest sanitised feature set: capability, task type, modality, token/document counts, policy flags, tool requirement, schema strictness, latency class, verification availability, previous attempt state. By default it does **not** receive raw user messages, images, whole documents, payment data, full retrieval context, unnecessary PII or unrelated history; raw content only when routing genuinely needs it, policy permits it and the need is documented (G9 egress rules).

Span attributes per model call and per routing decision, next to the GenAI semantic-convention attributes (`deployment-ci-cd/reference/ai-observability.md`):

```text
capability, agent, workflow, trace_id, request_id, scope_id (hashed)
policy signals, minimum_tier, selected_tier, resolved_config_id, provider, pinned_version
routing_policy_version, reason_codes, router_used, router_latency_ms, router_fallback_used
attempt_number, escalation_reason, failover_from, verification_outcome
input_tokens, output_tokens, cached_tokens, model_latency_ms, ttft_ms
estimated_cost, cache_hit (layer), budget_remaining
human_review_outcome, final_task_outcome
```

| Metric group | Metrics |
|---|---|
| Cost | Per capability, tier, tenant and **route**; cost per successful task; cascade double-spend; evaluator and fan-out cost |
| Quality | Task success, schema pass, verification pass, human-override rate, grounding failures |
| Routing | Initial-tier acceptance, escalation rate, **under-route** and over-route rates, cheapest-passing-tier accuracy, deterministic-route share, router timeout rate |
| Resilience | Failover rate by provider, circuit-breaker opens, quota rejections |
| Latency | Router, model, verifier and end-to-end p50/p95/p99; cascade latency penalty |

Alerts: under-route on a safety slice (page) · failover or escalation rate > baseline × `<n>` · cost per route over budget · router timeout rate over threshold · a pinned version returning materially different canary scores. Keep metric labels bounded (tenant and route breakdowns from traces or billing exports).

## 18. Rollout plan and anti-patterns

| Phase | Milestone |
|---|---|
| 0 | Registry and tier definitions written; current models pinned; aliases removed |
| 1 | Instrument current state: capability, model, tokens, latency, cost, verification, final outcome |
| 2 | Logical tiers and capability contracts; resolver in the gateway; static per-capability mapping |
| 3 | Deterministic policy gate, floors and same-tier failover; fallback safety gate verified |
| 4 | Cascade pilot on one objectively verifiable, low-risk capability |
| 5 | Shadow dynamic routing compared against cheapest-passing-tier labels |
| 6 | Limited live routing for low-risk capabilities / cohorts |
| 7 | Broader routing after quality, safety and rollback gates pass |
| 8 | Learned routing, only with sufficient labelled evidence |

Anti-patterns (reviewer flags): choosing a model from a public leaderboard without evals on your tasks · strongest model everywhere "to be safe", or cheapest everywhere without safety gates · safety, privacy or authority traded as weights · one opaque router prompt picking both capability and model · an LLM router on routes rules already determine, or one with no timeout or fallback · raw user content, documents or PII sent to a router that needs metadata · cheap-first cascades on safety-critical or subjective outputs · an unavailable verifier treated as `PASS` · escalation retries that re-create records or re-send messages · provider failover conflated with quality escalation · fallback models that never passed the primary's safety gate · `latest` / `default` / auto-upgrading aliases in production · provider model strings hard-coded in features, prompts or tests · upgrades without shadow, canary or a warm rollback · cached routing decisions, semantic caches on personalised or ACL-varying answers, cache keys without scope · failover to a provider not approved for the data class · silent downgrade to stay under budget · routing-savings forecasts without a measured baseline · provider deprecation notices ignored until the cut-off.

## 19. Adoption checklist (organisation-owned)

These are decisions and records the organisation owns. The toolkit supplies aids (registry schema + validator, reference router, tests), but none of the approvals below is automated enforcement.

| Decision (ADAPT) | Proposer | Approvers (independent of the proposer for T2/T3) |
|---|---|---|
| New provider | Capability or platform team | AI platform owner · Security · Privacy/Legal (data terms) · Procurement (vendor risk) |
| New model from an approved provider | Capability team | AI platform owner · capability owner; + Security for T2/T3 |
| New capability → tier mapping | Capability team | AI platform owner |
| Version upgrade of a deployed model | AI platform | Capability owner sign-off on eval results |
| Routing-policy change (floors, cascade rules) | AI platform | Capability owner · Security for safety floors |
| Self-hosted open-weight model | Platform team | AI platform · Security (supply chain, weights provenance, licence) · Infra |
| Emergency suspension | Any on-call | Ratified afterwards via incident review |

Vendor risk review covers data retention and training use, sub-processors, regions, security certifications, incident-notification terms, deprecation-notice period, abuse-monitoring access to prompts, indemnity and exit plan. Routing-policy and registry changes are versioned in Git, reviewed, tested, observable and rollbackable.

- [ ] Logical tiers and per-capability contracts defined (§1); default floors ratified (§12)
- [ ] Registry exists with the §13 fields; every production model is in it in state `deployed`; `validate_model_registry.py` runs in CI and at startup
- [ ] All production references pinned to exact versions; no aliases; parameters part of the config (§15)
- [ ] Hard constraints (§11) checked for every config; vendor risk review on file per provider
- [ ] Cheapest-passing-tier labels and capability evals exist for every routed capability (§14)
- [ ] Routing strategy chosen per capability; deterministic rules run first; any LLM router has timeout + conservative fallback (§7, §12)
- [ ] Cascade only where an objective verifier exists; escalation idempotent (§12)
- [ ] Same-tier failover configured; every fallback passed the same eval and safety gate (§12)
- [ ] Upgrade runbook with shadow, canary, ramp and rollback triggers (§15)
- [ ] Provider adapter behind the gateway; circuit breakers and timeouts per provider (§16)
- [ ] Budgets per request tree, capability, tenant and provider enforced (§16)
- [ ] Cache keys include scope, config and prompt version; no routing-decision cache (§16)
- [ ] Decision contract typed and versioned; router inputs minimised (§17)
- [ ] §17 span attributes emitted; cost-per-route and under-route alerts live
- [ ] Approvers named as individuals; registry serves as the AI inventory (G20)
- [ ] Flags and overrides exist, are audited and drilled (§9)

## Key Rules

| Rule | Standard |
|------|----------|
| Model strings | Registry + resolver only; aliases rejected at load |
| Selection | Cheapest deployed config that passes the capability's eval and safety gates; hard constraints filter, never weigh |
| Policy gate | Deterministic, separate signals, before any model call; floors cannot be lowered by overrides |
| Failover | Same tier, availability errors only, approved for the data class and region; else higher tier or non-AI path |
| Escalation | Verifier-driven, same operation id, no cascade on safety/high-impact; unavailable verifier ≠ PASS |
| Budget | One budget per request tree; exhaustion degrades visibly, never downgrades |
| Router | LLM router only for ambiguous routes, with deadline, validated label, conservative fallback, minimised input |
| Audit | Typed decision record with closed reason codes and policy version on every request |

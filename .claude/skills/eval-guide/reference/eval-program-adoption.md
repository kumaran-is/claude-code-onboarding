# Eval Program: Inventory, Tool Selection, Layer Cadences, Domain Concerns, Adoption

> Program-level rules for instantiating an evaluation strategy in a product. Per-run discipline lives in `../SKILL.md`; tiers in `ci-tiers.md` and `red-teaming.md`; datasets in `golden-dataset.md`; thresholds in `per-agent-thresholds.md`; prompts in `langfuse-prompts.md` and `prompt-engineering-patterns/reference/promptops-lifecycle.md`; tools in `mcp-eval-patterns.md`; production alerts and SLOs in `deployment-ci-cd/reference/ai-observability.md` §9.1. **ADAPT** marks a product decision; every other value is a default you may adopt as-is. Bias: open source first, your cloud's managed services second, a paid SaaS only where it is clearly worth it.

## Five rules that hold whatever tools you pick

| Rule | Where it is enforced |
|---|---|
| 1. Evaluate **trajectories** (which tools, in what order, with what inputs), not only final answers | `trajectory_case.schema.json` `required_tool_sequence` / `forbidden_tools`; dimension 1 in `../SKILL.md` |
| 2. Golden datasets live in **Git**, not only in a SaaS UI | `golden-dataset.md` rule 1 (GD001) |
| 3. Security and authorization **never** depend on prompts: they live in code with deterministic tests | `ci-tiers.md` "Hard CI blockers"; `langfuse-prompts.md` "What goes in code vs the registry" |
| 4. The PR gate is **fast** (< 5 min); full suites run nightly and pre-release | `ci-tiers.md` R1; never-on-PR suites rejected by `eval_gate.py route` (EG020) |
| 5. Every confirmed production failure becomes a **permanent regression case** | `golden-dataset.md` "Data flywheel" (GD017) |

## Inventory your eval targets (ADAPT: fill all three before choosing thresholds)

You cannot evaluate what you have not listed. `ai-eval-designer` writes these rows into the feature's eval README; a missing row is a gap, never a guess.

| Feature / agent | Type (single-call / RAG / agent / multi-agent) | Tools it calls | Primary eval concerns | Risk level (critical / high / medium / low) |
|---|---|---|---|---|

| Corpus | Store | Used by | Metrics that matter (recall@k, faithfulness, citation correctness) | Isolation boundary (tenant / org / user) | Embedding model + dimension |
|---|---|---|---|---|---|

An embedding model or dimension change invalidates every retrieval baseline for that corpus (re-baseline through the reviewed step in `golden-dataset.md`).

| Tool | Read / write | Side effect (none / financial / communication / data) | Who may call it | Audit required (write: **yes**; read: recommended) |
|---|---|---|---|---|

## Tool selection: one tool per job

Pick **one** option per job (`../SKILL.md` "Job" table). Never add an LLM vendor only for judging. Selection criteria, in order:

1. **Fits your stack:** native to your agent framework and language; no banned dependency pulled in by your own imports (transitive deps: `../SKILL.md` Iron Law).
2. **Runs locally and in CI** without a SaaS account.
3. **Judge model is configurable** to the provider you already use.
4. **Emits machine-readable results** (JUnit XML / JSON) so CI can gate on it (`eval_result.schema.json`).
5. **Licence and cost** acceptable at your scale.

| Category | Look for | Watch out for |
|---|---|---|
| Framework-native eval | trajectory + final-response scoring from golden files | thin metric set: supplement with a judge library |
| Judge-metric library | agent metrics (task completion, step efficiency), multi-turn metrics, custom rubrics | metric names change between versions: verify against current docs (`deepeval-patterns.md`) |
| RAG eval | faithfulness, context precision/recall, factual correctness, tool-call accuracy | test-set generators that pull in frameworks you do not use (`ragas-patterns.md`) |
| Red-team runner | declarative config, plugin library (injection, BOLA/BFLA, PII, RAG poisoning, excessive agency), multi-turn jailbreak strategies, fail-on-error | running the full corpus on every PR (`red-teaming.md` "Never on every PR") |
| Scenario framework | structured scenarios, groundedness / toxicity / conformity checks, user simulation | API breaks across major versions (`giskard-patterns.md`) |
| Prompt registry | immutable versions, labels, protected production label, SDK fetch + compile, cache | heavy self-host footprint (several containers): consider managed for staging/prod |
| Trace store | OTel-native ingestion, span replay, dataset export, experiments | licence terms for self-host |
| Managed eval | adaptive rubrics for quality, hallucination, tool use, safety | per-eval cost: nightly, pre-release and sampled prod only |

## Layer cadences (L3-L5)

L1/L2 budgets and the layer → tier map: `../SKILL.md` "Five layers"; L2 stage gates and the hard merge blockers: `ci-tiers.md`. Never block pre-commit on the full suite.

**L3 local full stack.** A container stack shaped like staging, split by compose profiles so engineers start only what they need:

| Profile | Contents | Use |
|---|---|---|
| `core` | metrics + dashboards | everyone |
| `ai-agents` | trace store | engineers on AI features |
| `observability` | core + ai-agents + logs | full observability |
| `prompt-registry` | registry and its dependencies | engineers editing prompts |

Cap memory on heavy stores (for example ClickHouse) so they do not starve primary databases. Route by environment: `OTEL_EXPORTER_OTLP_ENDPOINT`; `PROMPT_LABEL` (`development` → `staging` → `production`); fail-closed prompts (`PROMPT_ALLOW_DEGRADED=false`, the inverse of a `PROMPT_FAIL_CLOSED=true` flag) in staging and production, relaxed locally. Every environment file carries the same eval/observability keys.

**L4 staging (pre-production).**

| Activity | Cadence |
|---|---|
| Trace + metrics ingestion, cost per request | always-on |
| Prompt registry, label `staging` | always-on |
| Managed rubric eval on the full golden set | nightly (R2) |
| Multi-turn flows against deployed agents | nightly |
| Full red-team + scenario scans | nightly / weekly |
| Trace replay + experiments vs the release golden set | on demand / per release |
| Human review queue for failed traces | on demand |
| Pre-release sign-off → move the `production` label | per release (R3) |

**L5 production (online).**

| Activity | Cadence |
|---|---|
| Trace ingestion | always-on, sampled (e.g. 10% at high volume) |
| Ops metrics | always-on, 100% |
| Per-request cost + quality flags from a post-model callback / middleware | every request |
| Deep managed eval on sampled traffic | continuous, ~1% sample |
| `prompt_name`, `prompt_version`, `prompt_label`, `model_name` on spans (`app.prompt.*`, `gen_ai.request.model`) | every request |
| Isolation canary / injection + unauthorized-tool canary / compliance canary | hourly / hourly / daily (R4, `ci-tiers.md`) |
| Prompt rollback | on demand: **label move, no deploy** |

**Never write canonical data on model output alone.** Every mutating action passes through a typed service layer with its own validation (schema, authorization, business rules); eval catches drift, the service layer prevents catastrophe. Test it: for every write path, a case feeds a schema-valid but rule-violating model value (wrong scope, forbidden transition, out-of-range amount) and asserts the service layer rejects it and nothing is persisted (`mcp-eval-patterns.md` L2/L3 negatives; assert on persisted state, not reply text).

## Domain-specific concerns (ADAPT)

Generic metrics miss load-bearing product rules. For each concern that applies write **what is tested, golden-set size, threshold, owner** (the `ai-eval-designer` README "Domain concerns" table); compliance sets default to 25 cases Day 1, 100+ pre-launch (`golden-dataset.md`).

| Concern | Applies when | Typical threshold |
|---|---|---|
| Regulated-criteria compliance (fair housing, fair lending, EEO, healthcare, age) | AI influences eligibility, pricing, ranking or access | detector fires on 100% of the adversarial set |
| Multi-tenant / multi-user isolation | shared infrastructure | 0 leaks, enforced in code |
| Jurisdictional variance | advice or actions depend on location | 0 jurisdiction-incorrect mandatory actions; hedging is acceptable |
| Adverse-action / explainability duties | AI contributes to a denial | 0 missing notice flags |
| Marketplace gaming | participants can game scores | synthetic bad actor flagged within `<N>` interactions |
| Safety-critical classification | a miss causes harm | 100% critical-case sub-threshold |
| Cost-privacy / role visibility | different roles see different data | 0 forbidden fields rendered |

## Anti-patterns → review finding

| Anti-pattern | Caught by |
|---|---|
| Final answers only, no trajectory checks | `eval-reviewer` row 18 (dimension coverage) |
| Isolation or authorization in prompts or tool descriptions | `eval-reviewer` row 18; `ci-tiers.md` blockers asserted on tool calls and state |
| Golden data only in a SaaS UI | GD001 |
| Full red-team corpus or paid judges on every PR | EG020; `ci-tiers.md` R1 "no live model" |
| Re-baselining until a failing threshold passes | `eval-reviewer` row 20; EG012 anchor drift |
| `latest` prompts in production; registry-UI edits without Git | `langfuse-prompts.md` drift check; `prompt_drift.py` |
| Hardcoded prompt fallbacks hiding registry outages | `langfuse-prompts.md` outage policy (missing prompt raises) |
| Free-form `data: any` tool inputs; admin or destructive tools exposed to the model | `mcp-eval-patterns.md` L2 schema negatives |
| Write tools without audit logs | blocker 8 (`ci-tiers.md`) |
| Unsanitized production traces committed | GD013 + signed sanitization checklist |
| Incident closed without a regression case that failed before the fix | GD017; `pre_fix_ref` / `post_fix_ref` |
| Tool failures swallowed instead of testing the fallback path | dimension 13; `pytest-harness.md` "Failure injection" |

## Day-1 definition of done

"Day 1" means every mandatory eval and observability tool is installed, wired, runnable locally and has at least one meaningful smoke test for the product, not full coverage. A gate you have not run is NOT RUN, never PASS.

| # | Gate | Pass means | Toolkit proof |
|---|---|---|---|
| 1 | Observability stack boots locally | trace store, metrics, dashboards healthy | compose profiles above; healthchecks green |
| 2 | Prompts seeded | ≥ 1 prompt per implemented AI feature, label `development` | `langfuse-prompts.md` hash-based seed |
| 3 | Framework-native eval passes | all existing golden sets pass current thresholds | `adk eval` / `AgentEvaluator` (`adk-eval-guide`) or the LangGraph trajectory harness |
| 4 | Judge-metric suite runs | ≥ 2-3 metric cases per implemented feature pass | DeepEval / Ragas with an explicit judge |
| 5 | RAG metrics produce numbers | faithfulness + context precision score ≥ 1 RAG flow | `ragas-patterns.md`; `/rag-eval-init` |
| 6 | Red-team suite runs | completes; zero new attack successes vs baseline | `red-teaming.md`, `promptfoo-patterns.md` |
| 7 | Tool/MCP suite passes | contract + schema + auth + security for every implemented tool | `mcp-eval-patterns.md` |
| 8 | One trace visible | a local AI call appears in the trace UI | `ai-observability.md` §8 |
| 9 | One service scraped | metrics endpoint visible in the metrics store | `ai-observability.md` §4, §9.1 |
| 10 | One dashboard renders | against live metrics | `ai-observability.md` §9.1 |

Hard gates before the strategy counts as shipped: tenant/user isolation enforced **in code** at every tool and data boundary; the same eval/observability keys in every environment file; every threshold ratified (no TBD in a merge gate, `per-agent-thresholds.md`); owners are **named individuals**; Day-1 dataset minimums met (`golden-dataset.md`, GD018); the R1 gate exists with path routing and the hard-blocker list (`red-teaming.md`).

## Adoption checklist (organisation-owned)

These are product and organisation decisions. The toolkit supplies templates, validators and gates; it does not enforce ownership, cadences or budgets.

**Rollout (12 weeks, default order).** Week 0: inventory, expand golden sets to Day-1 minimums, add the judge library, create `prompts/` with the naming convention, build the `PromptRegistry` wrapper. Weeks 1-2: local observability profiles, fix isolation gaps **in code**, pin image versions, prompt/model span attributes. Weeks 3-4: critical-case sets, tool contract suites, manifests, sanitizer. Weeks 5-6: registry for dev/staging, seeding, prompt → trace correlation. Weeks 7-8: judge and RAG metrics in CI. Weeks 9-10: R1 path-routed gate, R2 nightly, R3 sign-off process. Weeks 11-12: multi-turn simulation, managed eval in staging, canaries, paging, rehearsed rollback runbook, calibrated thresholds. Post-launch: weekly red-team sweeps, nightly scans, ~1% sampled production eval, hourly/daily canaries, quarterly threshold and prompt-drift review.

**Cost.** Pre-launch ~$0 (OSS, local stack); launch: low hundreds of $/month (managed tracing/monitoring, ~1% managed eval, small hosted trace store and registry). Levers: lower the production eval sample (1% → 0.5%); drop a separate trace store if the cloud trace UI suffices; managed registry in staging/prod, self-host only for dev/CI; revisit self-host vs managed at high event volume. Estimate managed-eval cost in a staging load test; never commit a fixed figure up front.

**Ownership (named people, not roles; unowned suites decay).**

| Surface | Owner |
|---|---|
| Golden datasets + thresholds | AI quality owner |
| Framework eval per feature | feature owner |
| RAG eval | RAG owner |
| Red team + canaries + compliance sets | security engineer |
| Tool server suites + audit log | backend owner |
| Prompt registry + promotion | AI platform owner |
| Traces, metrics, dashboards, paging | platform owner |
| Domain-compliance cases | product + legal (review), AI team (execution) |

**Checklist.**

- [ ] Inventory filled: features, corpora (embedding model + dimension), tools (read/write, audit), risk levels
- [ ] One tool chosen per job; no extra LLM vendor added only for judging
- [ ] Thresholds written and ratified, including critical sub-thresholds at 100%
- [ ] `tests/golden/` layout + manifests; Day-1 minimums met; `validate_golden.py` green
- [ ] Every eval result records dataset / prompt / model / tool-surface versions
- [ ] `eval-smoke` (< 30 s) and `eval-all-local` targets exist and were run
- [ ] R1 < 5 min, path-routed, hard blockers enforced; R2 nightly, R3 pre-release sign-off, R4 canaries scheduled
- [ ] Prompts in Git, served via `PromptRegistry`, label-promoted, rollback rehearsed, drift check blocks release
- [ ] Every tool covers the five layers; surface hash locked; write tools audited
- [ ] Spans carry prompt + model attributes; dashboards and alerts (`ai-observability.md` §9.1) live
- [ ] Isolation enforced in code and tested deterministically; the violation metric pages at > 0
- [ ] Data flywheel and PII sanitization written into the incident process
- [ ] Owners named

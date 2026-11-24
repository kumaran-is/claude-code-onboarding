# PromptOps Lifecycle: Git → Registry → Runtime

> Referenced by `prompt-engineering-patterns` SKILL.md. This file is the canonical home of the PromptOps requirements (lifecycle, change → evals, security suite, drift, attribution, multilingual, portability, runtime wrapper, ownership, anti-patterns, adoption). `PRM §n` labels are stable requirement IDs; section 13 maps every one to its home in this skill. Executable runtime (fetch by label, model binding, safe rendering, last-known-good, emergency pack, eval-gated promotion and rollback): `../assets/prompts-scaffold/promptops/prompt_registry.py` (section 11). Langfuse-specific usage: `eval-guide/reference/langfuse-prompts.md`. Release mechanics (canary, flags, provider migration): `deployment-ci-cd/reference/llmops-release-and-rollout.md`. Values marked ADAPT are defaults for you to set, not mandates.

## 1. Lifecycle and labels (PRM §9)

```text
prompts/<domain>/<feature>/<task>.<type>.yaml   Git: authoring + review (source of truth)
   ↓ sync job: push only on content change, record content_hash + synced_at   (section 2)
Registry: immutable versions + movable labels   development → staging → production
   ↓ registry.get(name) with the label from PROMPT_LABEL config; never "latest"
Application → span: prompt_name, prompt_version, prompt_label, prompt_content_hash, model_*   (section 5)
```

| Label | Who moves it | Gate |
|---|---|---|
| `development` | Sync job from any branch | `validate_prompts.py` exit 0 |
| `staging` | Sync job from main | Local + CI evals for the change class pass (section 3) |
| `production` | Release owner / AI platform owner only | Staging evals pass + human approval (+ independent sign-off for T2/T3) + `prompt_drift.py --mode prerelease` exit 0 |

- Promotion **moves a label onto an existing immutable version**, so the version that was evaluated is the version that serves. There is no "production copy".
- No `latest`, `default` or auto-upgrading label in staging or production (G11). Langfuse reserves and manages `latest` itself (5.2.0 source); it is never a deployment label.
- **Rollback = move `production` back to the previous version**: no deploy, no code change. Rehearse it before a prompt's first production promotion. Rollback reaches running instances within the wrapper's cache TTL.
- New T2/T3 prompts ship behind a feature flag defaulting OFF; shadow-evaluate against the incumbent before switching (G7).
- Editing in the registry UI without a Git change is prohibited in staging and production. Drift detection (section 5) catches it.
- **Promotion freeze:** no label moves while any instance reports the degraded or emergency tier.

| Environment | Backend | Label | Missing prompt |
|---|---|---|---|
| Unit tests / CI | `file` (Git checkout) | n/a | Error |
| Local dev | `file` or registry | `development` | Error |
| Staging, production | registry | `staging` / `production` | Fail closed (`PROMPT_FAIL_CLOSED=true`) |

**Registry choice (ADAPT):** any registry that provides immutable versions, movable labels, a protected `production` label, SDK fetch by label, an audit log of label moves, a metadata field for `content_hash`, and export. Langfuse is one option (`eval-guide/reference/langfuse-prompts.md`). No paid product is required.

**Retirement (§9.4):** remove all callers → remove labels → set `deprecated: {date, replaced_by}` on the card → delete the file after the retention window (ADAPT). Registry versions stay retrievable for audit. `validate_prompts.py classify` reports a removed card as `PC_PROMPT_REMOVED` (REVIEW).

## 2. Sync job and label moves (Langfuse 5.2.0 example)

Executed against a fake client shaped like the 5.2.0 API (4 unit tests + 2 remove-the-guard controls, MOCKED PROVIDER) and end to end with `prompt_drift.py` (in sync → exit 0; registry-side edit → exit 1). Method signatures were read from the installed package source; no Langfuse server was run.

```python
import datetime as dt
import logging

from langfuse import Langfuse
from langfuse.api import NotFoundError

logger = logging.getLogger("prompt_sync")


def sync_card(lf: Langfuse, card: dict, content_hash: str) -> int | None:
    """New immutable version only when content changed; it starts at `development` only."""
    try:
        current = lf.get_prompt(card["name"], label="development", cache_ttl_seconds=0)
        if (current.config or {}).get("content_hash") == content_hash:
            return None                                                   # unchanged: push nothing
    except NotFoundError:
        logger.info("prompt_first_sync", extra={"prompt": card["name"]})  # any other error propagates
    config = {k: v for k, v in card.items() if k != "template"}
    config |= {"content_hash": content_hash, "synced_at": dt.datetime.now(dt.UTC).isoformat()}
    created = lf.create_prompt(name=card["name"], prompt=card["template"], type="text", labels=["development"],
                               config=config, commit_message=card["changelog"][-1]["change"])
    logger.info("prompt_synced", extra={"prompt": card["name"], "version": created.version})
    return created.version


def move_label(lf: Langfuse, name: str, version: int, label: str, *, registry_healthy: bool) -> None:
    """Promotion and rollback are label moves onto an existing version; frozen while degraded."""
    if label in ("latest", ""):
        raise ValueError("'latest' is managed by the registry and is never a deployment label")
    if not registry_healthy:
        raise RuntimeError("promotion freeze: registry not healthy")
    lf.update_prompt(name=name, version=version, new_labels=[label])  # labels are unique across versions
    logger.info("prompt_label_moved", extra={"prompt": name, "version": version, "label": label})
```

`content_hash` comes from `validate_prompts.py hash <card>`. It covers template, model binding, output schema, variables, tools, examples and languages, so a model change is a new version (§13). The 5.2.0 `Prompt` object has no creation timestamp, so the sync job stores `synced_at` in `config`. The snapshot for drift detection is built from `lf.api.prompts.list(name=...)` (version numbers) and `lf.api.prompts.get(name, version=n)` (labels, `config.content_hash`, `config.synced_at`), dropping the `latest` label.

## 3. Prompt change → required evals (PRM §15)

`validate_prompts.py classify --base-root base/prompts prompts --json changes.json` classifies each card diff deterministically and lists the evals. Keyword-based classes (`safety_wording`, `rag_citation`) can over-select, which is the safe direction. A reviewer can add classes but never remove them.

| Class (`classify`) | Trigger | Minimum evals |
|---|---|---|
| `metadata_only` | owner, description, changelog | none |
| `formatting` | whitespace or case only | prompt file validation + smoke golden cases |
| `wording` | task or constraint text, variables | full golden set for the feature + critical sub-thresholds |
| `output_schema` | `output_schema` ref | above + schema conformance 100% + all consumers' contract tests |
| `few_shot_examples` | `examples` | full golden set + bias/fairness checks where applicable (G19) |
| `safety_wording` | changed lines mention escalate / refuse / safety / harm / legal / medical / fraud | above + safety-recall set at 100% critical sub-threshold + red-team subset |
| `rag_citation` | changed lines mention citations, sources, retrieval, `<context` | above + faithfulness, context precision, citation correctness |
| `tools` | `tools` list, or a tool name in changed lines | above + trajectory eval + tool-surface hash update + tool red-team (eval strategy §10) |
| `model_change` | provider, model, version or params | **full** golden set + safety + red-team + latency and cost comparison; fallback binding re-evaluated |
| `new_language` | language added | full golden set + safety recall in that language |
| `new_prompt` | card not in base | everything above that applies + baseline before first promotion |

Gates: compare against the baseline rather than pass/fail alone (no regression on any critical, safety, isolation or compliance case; aggregate within tolerance, eval strategy §7.7). Evals run on a pinned dataset version and record prompt, model and dataset versions. Judge prompts are themselves prompt cards (type `judge`). A failing version is never promoted "temporarily". Execution, path routing and thresholds: `eval-guide` (`reference/ci-tiers.md`, `reference/red-teaming.md`). A behaviour change without a new changelog version is a BLOCK (`PC_CHANGELOG_NOT_BUMPED`).

## 4. Prompt security suite (PRM §16)

Every T1+ user-facing or tool-using prompt has these cases, path-routed into its PR gate. The success of any hard-blocker case blocks merge, and every confirmed production injection becomes a permanent regression case (eval strategy §7.9). Red-team tiers and tooling: `eval-guide/reference/red-teaming.md`. Attack-class catalogue: `security-reviewer/reference/ai-threat-model-attack-classes.md`. `test_ac*` names are in `security-reviewer/assets/ai-attack-class-fixture/test_attack_classes.py`; `test_runtime_*` in `../assets/prompts-scaffold/promptops/test_prompt_registry.py`. Schema-breaking, encoded/obfuscated, multi-turn and per-language cases have no deterministic test here: they are model-behaviour evals (`eval-guide/reference/red-teaming.md`).

| Case | Expected outcome | Deterministic layer that also covers it (executed test) |
|---|---|---|
| Direct injection ("ignore previous instructions…") | not followed, no tool call | code-side tool authorization (G2); `test_ac01_direct_injection_cannot_reach_write_tool`; stays inside its slot: `test_runtime_instruction_override_stays_inside_slot` |
| Indirect injection in a retrieved document | no behaviour change, no tool call, cited as data | delimiting + quarantined summarisation; `test_ac02_retrieved_instruction_never_triggers_tool` |
| Indirect injection in tool / sub-agent output | no behaviour change | tool output schema-filtered by code; `test_ac03_stored_payload_is_quarantined_at_read_time` |
| Delimiter breakout (closing tags in content) | escaped, structure intact | `test_runtime_delimiter_breakout_escaped`, `test_runtime_untrusted_slot_outside_delimiter_refused` |
| System-prompt extraction | refused; nothing confidential leaks | nothing secret in prompts (`PC_SECRET`); `test_ac06_prompt_contains_no_secrets`, `test_ac06_canary_in_output_is_blocked` |
| Role / authority claims ("I am an admin") | no privilege change | code-side authz; `test_ac04_authority_rederived_each_turn_not_from_history` |
| Cross-scope data request | refused; code returns no other-scope data | tenant/ACL filter before retrieval (G9); `test_ac07_cross_scope_id_rejected_and_no_violation` |
| Schema-breaking request ("answer in free text") | output still schema-valid | structured output + validation (G3) |
| Unsafe action request | `ESCALATE` / `REFUSED`, no action | approval gate in code; `test_ac05_jailbroken_model_cannot_force_forbidden_transition` |
| Encoded / obfuscated payloads (base64, homoglyphs) | no behaviour change | input classifiers where the tier requires |
| Multi-turn escalation | constraints hold on later turns | per-thread history, bounded window |
| Over-length / token flooding | truncated or rejected per budget | `test_runtime_over_length_rejected_or_truncated`, `test_runtime_input_budget_enforced`; `test_ac12_input_cap` |
| Secret in a variable (fixture) | render fails before the model call | `test_runtime_secret_interpolation_fails`, `test_runtime_secret_exfiltration_via_variable_refused` |
| Each supported language variant of the above | same outcomes | per-language eval sets (section 6) |

## 5. Drift detection and attribution (PRM §17–§18)

```bash
S=.claude/skills/prompt-engineering-patterns/scripts
uv run --script $S/prompt_drift.py --prompts-root prompts --registry snapshot.json --mode prerelease     # release gate
uv run --script $S/prompt_drift.py --prompts-root prompts --registry snapshot.json --traces spans.jsonl \
  --mode scheduled --max-behind-days 7 --json drift.json                                                  # nightly/daily
```

| Standard check | Cadence (§17) | Rule | Severity |
|---|---|---|---|
| Git hash ≠ staging-labelled version about to be promoted | pre-release | `DRIFT_STAGING_MISMATCH` | BLOCK |
| Registry content edited without a matching Git change | nightly staging, daily production | `DRIFT_REGISTRY_EDIT` (hash not current, not in `changelog[].content_hash`) | REVIEW → alert owner |
| `production` older than Git main for > `<n>` days (ADAPT, default 7) | weekly | `DRIFT_PRODUCTION_BEHIND` / `DRIFT_AGE_UNKNOWN` | REVIEW |
| Traces show a version at no label | continuous (sampled spans) | `DRIFT_TRACE_UNLABELED` | REVIEW |
| Git prompt never synced / registry-only prompt | every run | `DRIFT_NOT_SYNCED` / `DRIFT_REGISTRY_ORPHAN` | REVIEW |

Behavioural drift (same prompt, changing outcomes) is not a hash problem. It is detected by sampled production evaluation and the triple baseline (eval strategy §5.5, §7.8) and handled as an AI incident (`ai-incident-response`).

**Attribution (§18), on every model call:** `prompt_name`, `prompt_version`, `prompt_label`, `prompt_content_hash`, `model_provider`, `model_name`, `model_version`, generation params, `output_schema_version`, `validation_result`, `retry_count`, `input_tokens`, `output_tokens`, `cached_tokens`, `cost`, `latency`, `language`, `fallback_mode` (`normal | degraded | emergency`). Attribute names and the OTel GenAI mapping: `deployment-ci-cd/reference/ai-observability.md`. Store rendered prompt text only where the trace-store privacy rules allow (G8). Dashboards show the live version per environment with per-version quality, cost and latency.

## 6. Multilingual prompts and model portability (PRM §12–§13)

| Decision | Default (ADAPT) |
|---|---|
| Instruction language | One pivot language + an explicit output-language rule in `[CONSTRAINTS]` |
| Per-language prompt | Only when evals show the pivot approach fails for that language; same name, language recorded in a `{task}_<lang>` task segment or version metadata (pick one and enforce it) |
| Language detection | In code, before the call; never decided by the model |
| Unsupported language | Routed in code to a supported flow, a human or a form; never answered unevaluated |
| Safety, legal, emergency text | Pre-approved translated templates, not model translation |

Every language a prompt can receive is listed in `languages` and covered by its eval sets. Safety and escalation recall is measured **per language**. Glossaries for regulated terms are governed content and are injected, not paraphrased by the model.

Portability: the evaluated unit is *(prompt version, model version)*. A model, version or parameter change re-runs the full set (`model_change`). Fallback models have their own evaluated binding. Each pinned model's end-of-support date lives in the AI inventory (G20), with re-evaluation due `<n weeks>` before it. Routing chooses only among approved bindings (`agentic-ai-dev/reference/agentic-llm-routing.md`). Provider-specific features belong in the adapter, not the prompt text.

## 7. Ownership (PRM §20, ADAPT: name people, not roles)

| Surface | Owner | Where recorded |
|---|---|---|
| Each prompt | Feature owner + backup | `owner`, `backup_owner` on the card (`PC_PLACEHOLDER` until named) |
| `prompts/` conventions, CI validation, the wrapper, emergency pack | AI platform owner | CODEOWNERS for `prompts/**` and the wrapper module |
| `production` label moves | Release owner per product | registry permission on the protected label |
| Judge / rubric prompts | AI quality owner | owner of `*.judge` cards |
| Prompt security suites | Security engineer | red-team dataset manifest owner |
| Safety and legal-adjacent wording | Product + Legal / Compliance (review) | PR approval on `safety_wording` changes |
| Localized prompts and glossaries | Localization owner + feature owner | card owner + glossary file owner |

The toolkit can template and check these records. Appointing the people, and protecting the label in the registry, is an organisational step the toolkit cannot do.

## 8. Anti-patterns (PRM §21) and how they are caught

| Anti-pattern | Caught by |
|---|---|
| Editing in the registry UI without a Git change | `DRIFT_REGISTRY_EDIT`, `DRIFT_REGISTRY_ORPHAN` |
| Fetching `latest` in staging/production | `check-ai-assets.py` `PROMPT_LABEL_LATEST` (BLOCK); card schema rejects alias model versions |
| Hardcoded fallback prompt strings hiding outages | Wrapper raises; emergency pack only (`langfuse-prompts.md`); review |
| Authorization, isolation, limits or compliance only in prompt wording | Review (§19); `ai-security-reviewer` |
| Untrusted content concatenated into the system section | `PC_UNTRUSTED_UNDELIMITED`, `PC_UNTRUSTED_OUTSIDE_CONTEXT` |
| Regex-parsing free text to drive actions | Review; structured output (`system-prompts.md`) |
| Hand-copied prompt schema | `PC_EXAMPLE_SCHEMA` against the exported code-side schema; review |
| Few-shot examples from real customer conversations | `PC_EXAMPLE_PII`, `PC_EXAMPLE_PROVENANCE` |
| Prompt examples reused as eval cases | `PC_EXAMPLE_EVAL_OVERLAP` |
| Model swap "because the prompt didn't change" | `classify` → `model_change` (full set) |
| One mega-prompt doing several jobs | Review ("one prompt, one task") |
| Secrets, access codes or full records interpolated | `PC_SECRET`; renderer secret scan; `max_chars` |
| Model choosing the language of safety-critical messages | Review; code-side detection (section 6) |
| Patch-on-patch growth | `PC_BUDGET_STATIC` |
| Promoting a failing prompt "temporarily" | Promotion gates (section 1); `/ship` AI release gate |
| No owner, no eval set, no changelog | Card schema (`owner`, `eval_sets`, `changelog` required) |

## 9. Adoption checklist (PRM §22) with toolkit support

| Item | Toolkit support |
|---|---|
| `prompts/` + naming + allowed domains published | `assets/prompts-scaffold/prompts/` (`domains.yaml`), `PC_PATH`, `PC_DOMAIN` |
| Card format chosen; CI validates required fields | `assets/schemas/prompt_card.schema.json`, `validate_prompts.py` |
| Inline prompts moved into `prompts/` | `check-ai-assets.py` `PROMPT_REFERENCE_UNRESOLVED`; finding inline strings is review work |
| One registry; labels configured; `production` protected | Section 1 (registry permission is org setup) |
| Wrapper with `file` + registry backends, caching, attribution | `promptops/prompt_registry.py` (section 11; RUNTIME tests); Langfuse usage: `eval-guide/reference/langfuse-prompts.md` |
| Emergency pack from labelled versions; fail closed in staging/prod | `build_emergency_pack` + SHA-256 check at use; typed `PromptUnavailableError` (section 11) |
| Rendering: declared typed variables, escaping, secret scan, PII minimisation | `render_template` in `promptops/prompt_registry.py` (secret patterns imported from `validate_prompts.py`); `prompt-templates.md` §2 |
| Output schemas single-sourced; validation on every response | `system-prompts.md`; `PC_EXAMPLE_SCHEMA` on exported schemas |
| Few-shot governance | `few-shot-learning.md` §Governance |
| Prompt vs code division reviewed | `system-prompts.md` pitfalls; §19 checklist |
| Languages declared and evaluated; unsupported-language routing in code | Section 6; `languages` required on the card |
| Model pinned; model change → full re-eval | Card schema; `classify` → `model_change` |
| Token and cost budgets | `token_budget`, `PC_BUDGET_*` |
| §15 matrix in the PR gate via path routing | `classify` + `eval-guide` routing |
| §16 suite for every T1+ prompt | Section 4 + `eval-guide/reference/red-teaming.md` |
| Drift detection at §17 cadences | `prompt_drift.py` (schedule it in your CI) |
| §18 attributes on every call; live-version dashboard | Section 5; `ai-observability.md` |
| §19 checklist in the PR template for `prompts/**` | `prompt-optimization.md` §Review Checklist |
| Rollback by label move rehearsed | `rollback()` picks the previous approved version (section 11); rehearsal itself is organisation-owned (section 12) |
| §20 owners named | Card `owner`/`backup_owner`; section 7 |

## 10. Command map (no dedicated prompt commands)

| PromptOps task | Use |
|---|---|
| Create a prompt | Copy `assets/prompts-scaffold/prompts/` (and `promptops/` for the runtime) into the project; fill the card; `validate_prompts.py`. New agent projects: `/scaffold-agentic-ai`, `/scaffold-google-adk` |
| Serve and render a prompt in code | `PromptRuntime(registry, label=PROMPT_LABEL).render(name, variables, model=..., language=...)` from `promptops/prompt_registry.py`; put `span_attributes()` on the model-call span |
| Review a prompt PR | `/review-code` (routes `prompts/**` to `eval-reviewer`, runs `check-ai-assets.py`) + the §19 checklist + `ai-security-reviewer` for T1+ |
| Regression for a change | `validate_prompts.py classify` → the listed sets via `eval-guide` / `llm-evaluation`; `/verify` runs the deterministic AI checks |
| Promote | `promote()` (refuses without a passing eval for that exact (version, model), production without approval, or while degraded) + `/ship` AI release gate (R3 report names `prompt_version`) + `prompt_drift.py --mode prerelease`; `ai-launch-check` for first launch |
| Detect drift | `prompt_drift.py --mode scheduled` in a scheduled CI job |
| Roll back | `rollback()` (most recent previously approved version, never the current or an unapproved one); incident handling: `ai-incident-response`, `llmops-release-and-rollout.md` §9 |
| Test the runtime | `uv run --script assets/prompts-scaffold/promptops/test_prompt_registry.py` (CI); `python3.14` runs the stdlib subset |

## 11. Runtime wrapper: `PromptRegistry` (PRM §10)

Application code never calls a registry SDK directly. Reference implementation (stdlib only, copy it): `../assets/prompts-scaffold/promptops/prompt_registry.py`; tests: `test_prompt_registry.py` beside it (RUNTIME tests execute the module; STATIC VALIDATION tests run `validate_prompts.py` / `prompt_drift.py`; each listed control fails on a mutated copy).

| Responsibility (PRM §10.2) | Requirement | In the module |
|---|---|---|
| Backends | `file` (CI, offline, tests) and `registry` (staging, production), chosen by configuration | `FileRegistry`, `LangfuseRegistry` (lazy optional import; not run against a live server) behind the `PromptRegistry` protocol |
| Label pinning | Label from `PROMPT_LABEL`; code cannot request `latest` | `check_label`: only `development`, `staging`, `production` |
| Immutable versions | Re-publishing a name+version with other content is refused | `FileRegistry.publish` → `PromptIntegrityError` |
| Caching | TTL cache keyed by (name, label) (ADAPT, e.g. 60 s–5 min; the TTL is the rollback latency) plus last-known-good per prompt | `PromptRuntime(ttl_seconds=..., allow_degraded=...)`: TTL cache (default 0 = fetch every call) and last-known-good; strict mode raises on outage. One cache only (the Langfuse adapter disables the SDK cache). Tested: `test_runtime_ttl_bounds_rollback_latency`, `test_runtime_strict_mode_raises_instead_of_degrading` |
| Rendering | PRM §11 safety: declared typed variables, escaping, length limits, secret guard | `render_template`; secret patterns and `content_hash` come from `validate_prompts.py` (one definition) |
| Model binding | Pinned model from the card; a caller's resolved model that differs is refused, never silently overridden | `ModelBindingError`; placeholder bindings refused |
| Language and budget | Undeclared language refused (routing is code's job); rendered input over `token_budget.input_max` refused | `PromptRenderError` |
| Attribution | `prompt_name`, `prompt_version`, `prompt_label`, `content_hash`, model, tier for the span; no prompt text | `RenderedPrompt.span_attributes()` |
| Missing prompt | **Raises**; never a hardcoded fallback string | `PromptNotFoundError` / `PromptUnavailableError` |
| Metrics | Cache hit rate, fetch latency, degraded/emergency counters | `on_degraded(name, tier)` hook; emit the rest from your adapter |

Outage policy (PRM §10.3):

| Mode | Trigger | Behaviour | Alert |
|---|---|---|---|
| Normal | Registry healthy | Fetch by label; refresh cache | none |
| Degraded | Registry unreachable, last-known-good present | Serve it (`tier=last_known_good`); emit metric | Low severity |
| Emergency | Registry unreachable, no last-known-good (cold start) | Serve the pre-approved emergency pack entry after its SHA-256 check (`tier=emergency`) | Higher severity |
| Fail closed | Prompt absent from registry, cache **and** pack, or the pack fails its check | Raise a typed error; the capability takes its G6 degradation path | High severity |
| Promotion freeze | Any non-normal mode | `promote(..., registry_healthy=False)` refuses every label move | none |

The emergency pack is built at build time by `build_emergency_pack(registry, label, names)` from the versions at the target environment's label (never branch content) and is checksum-verified at use (corruption check, not a signature: sign the pack or ship it in the signed build artifact); a misfiled entry or a pack built for another label is refused. `PROMPT_FAIL_CLOSED=true` in staging and production. A registry that is healthy but has no version at the label fails closed (it does not serve last-known-good).

Promotion and rollback (PRM §9.2, §13, §15): `promote()` moves a label onto an existing version only when the latest eval record for that exact (prompt version, model binding) passed; `production` also needs a recorded human approval. `rollback()` moves the label to the most recent version previously promoted to that label with a passing eval for the model, skipping the current version and any version already rolled back from; with no such version it raises instead of guessing. The eval ledger is in memory in the reference: persist it (eval result rows, registry audit log).

**Where the deterministic checks sit.** Prompt wording is never the authorization control. Enforcement points: the renderer and runtime above (before the model call), structured-output validation and code-side tool authorization (after it, `system-prompts.md`, `agentic-ai-dev/reference/tool-execution-safety.md`), and the CI gates (`validate_prompts.py`, `classify`, `prompt_drift.py`).

## 12. Adoption checklist (organisation-owned)

The toolkit templates and checks these records; people must do the following. None is automated enforcement.

- [ ] Name owners per PRM §20 (section 7), people not roles; add CODEOWNERS for `prompts/**` and the wrapper module.
- [ ] Choose one registry (section 1); configure `development` / `staging` / `production`; protect `production` with access control and keep the label-move audit log.
- [ ] Publish the allowed `domain` list (`domains.yaml`) and the ADAPT values: cache TTL, input/static/output budgets, cost per call p95, prompt-size growth threshold, `<n>` days behind, retention window, end-of-support re-eval lead time.
- [ ] Move existing inline prompts into `prompts/` and remove them from application code.
- [ ] Add the §19 checklist (`prompt-optimization.md` §Prompt Review Checklist) to the PR template for `prompts/**`; require owner (or backup) approval and an independent reviewer for T2/T3 safety-relevant changes.
- [ ] Wire `classify` into path-routed PR evals; schedule `prompt_drift.py` (nightly staging, daily production, weekly behind-check) with alerts.
- [ ] Rehearse rollback by label move for every production prompt before its first production promotion.
- [ ] Record each pinned model's end-of-support date in the AI inventory (G20) and plan re-evaluation before it.
- [ ] Product + Legal / Compliance review of safety- and legal-adjacent wording; pre-approved translated templates for safety, legal and emergency messages.
- [ ] Build a live-version dashboard per environment with per-version quality, cost and latency.

## 13. Requirement map (PRM §1–§22)

| PRM | Requirement | Home in this skill |
|---|---|---|
| §1 | Principles P1–P10 | `SKILL.md` §PromptOps in One Screen |
| §2, §2.1, §2.2 | Six-part anatomy, template, writing rules, uncertainty contract | `system-prompts.md` §six-part anatomy; template: `assets/prompts-scaffold/prompts/support/triage/classification.system.yaml`; `PC_ANATOMY_*`, `PC_UNCERTAINTY_CONTRACT` |
| §3, §3.1–§3.3 | Trust levels, delimiting, injection-resistant patterns | `system-prompts.md` §Trust levels; `prompt-templates.md` §2–§4; `PC_UNTRUSTED_*` |
| §4 | Structured output | `system-prompts.md` §Output format; `prompt-library-structured-output.md` |
| §5 | Few-shot governance | `few-shot-learning.md` §Governance; `PC_EXAMPLE_*` |
| §6 | Prompts vs code | `system-prompts.md` §Prompts vs code |
| §7 | Naming `{domain}.{feature}.{task}.{type}` | `prompt-templates.md` §1; `PC_PATH`, `PC_DOMAIN`, card schema |
| §8 | Prompt file and card | `assets/schemas/prompt_card.schema.json`; `prompt-templates.md` §1 |
| §9, §9.1–§9.4 | Lifecycle, registry choice, labels, environments, retirement | sections 1–2 |
| §10, §10.1–§10.3 | Wrapper interface, responsibilities, outage policy | section 11; `promptops/prompt_registry.py` |
| §11 | Templating and variable safety | `prompt-templates.md` §2; `render_template` |
| §12 | Multilingual | section 6; card `languages`; `PC_EXAMPLE_LANGUAGES`; runtime language check |
| §13 | Model portability | section 6; `classify` → `model_change`; runtime model binding |
| §14 | Length and cost budgets | `prompt-optimization.md` §Length and Cost Budgets; `PC_BUDGET_*`; runtime `input_max` check |
| §15 | Change → required evals | section 3; `validate_prompts.py classify` |
| §16 | Prompt security suite | section 4; `test_prompt_registry.py` (`RuntimeAdversarial`) |
| §17 | Drift detection | section 5; `prompt_drift.py` |
| §18 | Observability and attribution | section 5; `span_attributes()` |
| §19 | PR review checklist | `prompt-optimization.md` §Prompt Review Checklist |
| §20 | Ownership | section 7 |
| §21 | Anti-patterns | section 8 |
| §22 | Adoption checklist | sections 9 (toolkit support) and 12 (organisation-owned) |

Validator and drift messages cite these numbers as "(section n)".

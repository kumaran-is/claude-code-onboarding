# Prompt Registry, Lifecycle and Prompt Regression

> Provider-neutral contract first; Langfuse is one optional backend. Langfuse SDK calls were checked against the installed langfuse 5.2.0 (Python 3.14.10) with no Langfuse server: `get_prompt(name, label=, fallback=, max_retries=, fetch_timeout_seconds=, cache_ttl_seconds=)` signature introspected; executed, the fallback path returned a `TextPromptClient` with `is_fallback=True`, `version=0`, `labels=['production']`; without `fallback=` an unreachable server raised `httpx.ConnectError` (the adapter below must let it propagate to the registry). Server-side label moves and prompt linking were not exercised. The registry runtime (one implementation, below) runs in this repo with 35 tests and per-control negative controls; its Langfuse adapter is tested with a fake client only. Also read in the 5.2.0 source: `create_prompt(*, name, prompt, labels=[], tags=None, type='text'|'chat', config=None, commit_message=None)`; `update_prompt(*, name, version: int, new_labels=[])` moves labels and invalidates the SDK cache for that name, and the `latest` label is reserved and managed by Langfuse; prompt clients expose `.version` and `.config`.
> Release mechanics (eval-gated promotion, canary, rollback, provider migration): `deployment-ci-cd/reference/llmops-release-and-rollout.md`. Trace attributes: `deployment-ci-cd/reference/ai-observability.md`.

## Install (Langfuse backend, optional)

```toml
# pyproject.toml
langfuse = "==5.2.0"   # Python >=3.11; v2-era `langfuse.decorators` / `.trace()` APIs no longer exist (ai-observability.md section 7)
```

## Naming

`{domain}.{feature}.{task}.{type}` (prompt-engineering standard §7): four lowercase snake_case segments, type ∈ `system|user|tool|judge|examples|correction`, for example `support.triage.classification.system`, `hr.policy_qa.rag_answer.system`. The path mirrors the name: `prompts/<domain>/<feature>/<task>.<type>.yaml`. Validator: `prompt-engineering-patterns/scripts/validate_prompts.py` (it owns the prompt-card schema and the `prompt_drift.py` release gate). The file backend below rejects any other name at load, so CI fails on a misnamed prompt.

## Registry contract (required pattern)

Agent code never calls the backend SDK directly. The registry returns a **versioned prompt object** (name, label, version, content hash, tier), never a bare string, so every model-call span and eval row can name the exact version. "Fail closed" means **raise**; degraded tiers are explicit, logged and alerted.

The one implementation is `prompt-engineering-patterns/assets/prompts-scaffold/promptops/prompt_registry.py` (stdlib; copy it next to your `prompts/` tree): `PromptRuntime` (label from configuration, TTL cache, last-known-good and hash-verified emergency tiers, `allow_degraded=False` strict mode, model binding, safe rendering, input budget), `FileRegistry` (Git prompt tree for CI and local dev), `LangfuseRegistry` (optional), `build_emergency_pack`, and eval-gated `promote` / `rollback`. Tests: `test_prompt_registry.py` next to it (`uv run --script`, CI job `promptops_runtime`). Normative rules: `prompt-engineering-patterns/reference/promptops-lifecycle.md`.

Rules:
- **TTL is the rollback latency.** `PromptRuntime(ttl_seconds=...)`: a label move reaches running instances within the TTL (default 0, fetch on every call). State the TTL in the runbook; a cache without TTL means a rollback never applies until restart.
- **One cache.** The Langfuse adapter disables the SDK cache (`cache_ttl_seconds=0`) because the runtime owns caching; if you rely on the SDK cache instead (default TTL 60 s, background refetch), keep `ttl_seconds=0`. Never stack two.
- **The label comes from configuration** (`PROMPT_LABEL`), never from the call site; anything but `development`, `staging` or `production` (including `latest` and empty) is refused before any fetch.
- **The card travels with the text.** The prompt card is stored as the Langfuse version `config`, with `content_hash` written by the sync job, defined by `validate_prompts.content_hash(card)` (sha256 over template, model, output_schema, variables, tools, examples, languages), so a model change also changes the hash. A version without `content_hash`, or whose served text no longer matches it (a registry-UI edit that kept the old config), is refused (`PromptIntegrityError`). Drift detection compares this hash.
- **Fail mode.** Last-known-good (Degraded) and the emergency pack (Emergency) are served on outage; a prompt absent from registry, cache and pack raises. `allow_degraded=False` is deliberately **stricter**: once the TTL has expired a failed fetch raises (use `ttl_seconds=0` for prompts that must never be served past a rollback) and the caller turns `PromptUnavailableError` into the structured fallback / safe state. Use it for consequential prompts in production; `on_degraded` increments a metric per tier and alerts.
- **Seed only on change.** The sync job publishes a new registry version only when the card's `content_hash` differs from the latest one (Langfuse numbers versions server-side; `FileRegistry.publish` is idempotent on equal content and refuses a reused version number with other content).
- Log `error_type`, never `str(exc)` (request-derived content can leak); see `deployment-ci-cd/reference/python-observability.md` §2.
- **Emergency pack:** built from the versions at the target label (never branch content), each entry carries a SHA-256 checksum and its own prompt name; a corrupted or edited entry, a misfiled entry or a pack built for another label is refused at use. The checksum is not a signature: anyone who can rewrite the pack can recompute it, so sign the pack or ship it inside the signed build artifact.
- Record the prompt name, label, version, content hash and tier on the span of every model call (`RenderedPrompt.span_attributes()`: `app.prompt.name`, `app.prompt.label`, `app.prompt.version`, `app.prompt.sha256`, `app.prompt.tier`; the model as `gen_ai.request.model` / `gen_ai.response.model`, `deployment-ci-cd/reference/ai-observability.md` §2 and §6) and on every eval row (`prompt_name`, `prompt_version`, `model_name` in `../assets/schemas/eval_result.schema.json`). These are the PromptOps correlation fields `prompt_name`, `prompt_version`, `prompt_label`, `model_name` under OTel naming rules (custom attributes in your own namespace).

### Langfuse adapter

`LangfuseRegistry` in the runtime calls `get_prompt(name, label=label, cache_ttl_seconds=0, fetch_timeout_seconds=5)` with no SDK `fallback=` (the runtime decides the tier): `NotFoundError` fails closed as `PromptNotFoundError`, any other error (an unreachable server raised `httpx.ConnectError`, executed) becomes `RegistryUnavailableError`. `publish` calls `create_prompt(name=, prompt=, type="text", labels=[], config=card, commit_message=)` and `move_label` calls `update_prompt(name=, version=, new_labels=[label])` after the label check. Not executed against a live Langfuse server.

If Langfuse is also your tracer, you may link the SDK prompt object to the generation (`start_as_current_observation(as_type="generation", prompt=prompt)`); keep the span attributes above either way. `prompt.compile()` substitutes `{{var}}` slots, leaves unknown slots in place and escapes nothing, so it is not a safe renderer: use `PromptRuntime.render` (rules: `prompt-engineering-patterns/reference/prompt-templates.md` §2). To list versions and labels: `api.prompts.list(name=, label=, tag=, page=, limit=, from_updated_at=, to_updated_at=)` (returns `versions`, `labels`, `last_config`). With `cache_ttl_seconds=0` there is no SDK-level stale tier (the SDK otherwise returns an expired cached prompt when a refetch fails). The SDK's own `fallback=` / `is_fallback` is an alternative to the emergency tier; if used, `is_fallback=True` must emit the same degraded metric.

## Lifecycle and promotion

```
prompts/<domain>/<feature>/<task>.<type>.yaml   Git: source of truth, PR-reviewed
        ↓ seed job (writes content hash into registry metadata)
Registry version N                    label: development
        ↓ eval on version N passes (held-out set, deterministic gates)
label: staging → staging eval + human approval → label: production
```

- Promote a label only after the eval ran on **that exact version** and only while the registry is healthy. Fetch by label, never `latest` in production. `production` additionally needs a recorded human approval.
- **Rollback = move the label to N-1**, no deploy. Never delete versions. Rehearse it before launch.
- **Prompt + tools move together:** a prompt that names tools is bumped in the same change as the tool set, and a CI check asserts the tool names in the prompt equal the registered tools.
- **Drift check:** Git hash vs registry `content_hash` metadata vs what the production label serves. Any mismatch **blocks the release**; run it nightly in staging and weekly in production with an alert. For prompt cards the CLI gate is `prompt-engineering-patterns` `prompt_drift.py --mode prerelease`; the runtime test `test_static_drift_detected_against_runtime_hash` proves the runtime hash is the one it compares.
- **CI never needs a registry container:** R1 runs on the file backend (`PROMPT_BACKEND=file`); `registry` is for dev-with-registry, staging and production.

### File backend, drift check, promotion guard

CI uses `FileRegistry` (no registry container): a misnamed or schema-invalid card is caught by `validate_prompts.py`, a missing prompt raises `PromptNotFoundError`, and a reused version number with other content raises `PromptIntegrityError`. Drift is the `prompt_drift.py --mode prerelease` gate over the same content hash. `promote()` refuses a label move while the registry is unhealthy or any instance serves a degraded tier, without a passing eval for that exact (version, model), and for `production` without a recorded approval; `rollback()` moves the label to the most recent previously approved version. Adapt the in-memory `EvalLedger` to your eval-result store and the registry audit log.

### Outage policy

| Mode | Trigger | Behaviour | Alert |
|---|---|---|---|
| Normal | registry healthy | fetch by `production` label; cache last-known-good (TTL) | none |
| Degraded | registry down, cache hit | serve the cached version (`tier=last_known_good`); emit the degraded metric | low severity |
| Emergency | registry down, cache miss | serve the hash-verified emergency pack built from the target label (`tier=emergency`); consequential prompts with `allow_degraded=False` raise instead (stricter than the outage tiers) | higher severity |
| Promotion freeze | any of the above, or any instance reporting degraded / emergency | `promote()` refuses every label move until the registry is healthy and no instance reports a degraded tier | with the mode's alert |

A missing prompt raises in every mode: never fall back to a hardcoded string in application code.
- **Provenance:** frameworks append schema and context to the system prompt, so hash equality with the rendered prompt never holds. Prove provenance by containment of the stored prompt text in the rendered system prompt plus a stable recorded delta.

## Prompt regression test

1. Run the **held-out** golden set (never the tuning set) for the current production version and the candidate, same model, judge, dataset version and tier.
2. Deterministic gates (schema, safety, isolation, tool-call args) must be green for the candidate.
3. Compare per case with a paired test (`llm-evaluation/reference/ab-testing.md`): fixed vs newly broken cases, McNemar for pass/fail, paired bootstrap CI for scores. Ship on a non-inferior lower bound, never on a raw-mean win or a tuning-set improvement.
4. Report fixed and newly broken cases in both directions; re-run happy paths after a negative-case fix.

## What goes in code vs the registry

| In code (deterministic, security) | In the registry (language behaviour, tunable) |
|----------------------------------|------------------------------------------|
| Tenant isolation, authorization | System and task prompts |
| Policy detectors, business rules | Tone and notification prompts |
| Tool schemas (Pydantic), allowlists | Rubric / judge prompts (versioned like code) |
| Retry / fallback logic, SQL filters | RAG answer instructions, prompt experiments |

## Environment (Langfuse)

```
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=http://localhost:3000   # LANGFUSE_HOST is the deprecated alias
PROMPT_LABEL=production                   # per environment: development | staging | production; never latest
PROMPT_ALLOW_DEGRADED=false               # per prompt class; false for consequential prompts in prod
PROMPT_CACHE_TTL_SECONDS=60
```

Local stack: run the self-hosted compose file from the Langfuse docs (web, worker, Postgres, ClickHouse, Redis, object storage); wait for all containers healthy before seeding.

## Known Gotchas

| Gotcha | Fix |
|--------|-----|
| Registry returns `str` | Return the versioned object; tracing and evals need version + hash |
| Dict cache without TTL | Rollback never applies; TTL cache, one cache only |
| "Fail closed" that falls back | Fail closed = raise; fallback is an explicit, alerted tier |
| `except Exception: ...` without logging | Every except logs event + `error_type`, then raises or returns an explicit tier |
| `label="latest"` in production | Fetch by deployment label |
| Missing `flush()` in short-lived eval scripts | Flush/shutdown the tracing client before exit or events are lost |
| `fallback=` and a registry bundled tier both active | Pick one; an SDK fallback has `version=0`, so record `is_fallback` as the degraded tier |

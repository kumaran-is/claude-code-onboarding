# Prompt Registry, Lifecycle and Prompt Regression

> Provider-neutral contract first; Langfuse is one optional backend. Langfuse SDK calls (`get_prompt(name, label=, cache_ttl_seconds=, fallback=)`, `is_fallback`, prompt-to-generation linking, `LANGFUSE_BASE_URL`) were checked against the Langfuse docs via Context7 on 2026-11-22, not executed. The registry class below was executed with a fake client (4 tests: TTL rollback, fail-closed raise, degraded tiers, placeholder refusal) and passes `mypy --strict`.
> Release mechanics (eval-gated promotion, canary, rollback, provider migration): `deployment-ci-cd/reference/llmops-release-and-rollout.md`. Trace attributes: `deployment-ci-cd/reference/ai-observability.md`.

## Install (Langfuse backend, optional)

```toml
# pyproject.toml
langfuse = "==<pinned v3+ release>"   # verify via Context7; v2 examples (Langfuse(), LANGFUSE_HOST) are outdated
```

## Naming

`<audience>.<domain>.<task>.<prompt_type>`, for example `user.onboarding.profile_collection.system`, `support.answer.system`, `support.classify.system`, `search.ranking.system`, `notification.user.status_update.system`.

## Registry contract (required pattern)

Agent code never calls the backend SDK directly. The registry returns a **versioned prompt object** (name, label, version, content hash, tier), never a bare string, so every model-call span and eval row can name the exact version. "Fail closed" means **raise**; degraded tiers are explicit, logged and alerted.

```python
# <package>/prompts/registry.py
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("prompts")


@dataclass(frozen=True)
class ResolvedPrompt:
    name: str
    label: str
    version: str           # registry version, or "bundled:<sha12>" for the emergency pack
    text: str
    content_sha256: str
    tier: str              # "live" | "last_known_good" | "bundled"


class PromptUnavailableError(RuntimeError):
    pass


class RegistryClient(Protocol):
    def fetch(self, name: str, label: str) -> tuple[str, str]:  # (version, text)
        ...


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class PromptRegistry:
    def __init__(self, client: RegistryClient, bundled: dict[str, str], *, ttl_seconds: float = 60.0,
                 allow_degraded: bool, on_degraded: Callable[[str, str], None] = lambda name, tier: None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        for name, text in bundled.items():
            if not text.strip() or "TODO" in text or "PLACEHOLDER" in text.upper():
                raise ValueError(f"bundled prompt {name!r} is a placeholder; ship a reviewed prompt")
        self._client, self._bundled, self._ttl = client, bundled, ttl_seconds
        self._allow_degraded, self._on_degraded, self._clock = allow_degraded, on_degraded, clock
        self._cache: dict[tuple[str, str], tuple[float, ResolvedPrompt]] = {}

    def get(self, name: str, label: str = "production") -> ResolvedPrompt:
        key = (name, label)
        cached = self._cache.get(key)
        if cached and self._clock() - cached[0] < self._ttl:
            return cached[1]                                   # TTL bounds rollback propagation
        try:
            version, text = self._client.fetch(name, label)
        except Exception as exc:
            logger.warning("prompt_fetch_failed", extra={"prompt": name, "label": label,
                                                          "error_type": type(exc).__name__})
            return self._degraded(name, label, cached[1] if cached else None, exc)
        prompt = ResolvedPrompt(name, label, version, text, _sha(text), "live")
        self._cache[key] = (self._clock(), prompt)
        return prompt

    def _degraded(self, name: str, label: str, stale: ResolvedPrompt | None,
                  exc: Exception) -> ResolvedPrompt:
        if not self._allow_degraded:
            raise PromptUnavailableError(name) from exc
        if stale is not None:
            self._on_degraded(name, "last_known_good")
            return ResolvedPrompt(stale.name, label, stale.version, stale.text,
                                  stale.content_sha256, "last_known_good")
        if name in self._bundled:
            text = self._bundled[name]
            self._on_degraded(name, "bundled")
            return ResolvedPrompt(name, label, f"bundled:{_sha(text)[:12]}", text, _sha(text), "bundled")
        raise PromptUnavailableError(name) from exc
```

Rules:
- **TTL is the rollback latency.** Moving a label back reaches running instances within `ttl_seconds`; a cache without TTL means a rollback never applies until restart. State the TTL in the runbook.
- **One cache.** With the Langfuse adapter below, disable the SDK cache (`cache_ttl_seconds=0`) because the registry owns caching; or drop the registry cache and rely on the SDK's (default TTL 60 s, background refetch). Never stack two.
- `allow_degraded=False` for consequential prompts in production: the caller turns `PromptUnavailableError` into the structured fallback / safe state. `on_degraded` increments a metric per tier and alerts.
- Log `error_type`, never `str(exc)` (request-derived content can leak); see `deployment-ci-cd/reference/python-observability.md` §2.
- The bundled pack is the reviewed prompt set frozen at build time; placeholder text is refused at load.
- Record `prompt.name`, `prompt.label`, `prompt.version`, `prompt.content_sha256`, `prompt.tier` on the span of every model call and on every eval row.

### Langfuse adapter

```python
from langfuse import get_client

class LangfuseRegistryClient:
    def __init__(self) -> None:
        self._lf = get_client()                     # reads LANGFUSE_PUBLIC_KEY / _SECRET_KEY / _BASE_URL

    def fetch(self, name: str, label: str) -> tuple[str, str]:
        p = self._lf.get_prompt(name, label=label, cache_ttl_seconds=0)   # registry owns the cache
        return str(p.version), p.prompt              # template text; render with your own variables
```

If Langfuse is also your tracer, you may link the SDK prompt object to the generation (`start_as_current_observation(as_type="generation", prompt=prompt)`); keep the span attributes above either way. The SDK's own `fallback=` / `is_fallback` is an alternative to the bundled tier; if used, `is_fallback=True` must emit the same degraded metric.

## Lifecycle and promotion

```
prompts/<domain>/<task>.system.yaml   Git: source of truth, PR-reviewed
        ↓ seed job (writes content hash into registry metadata)
Registry version N                    label: development
        ↓ eval on version N passes (held-out set, deterministic gates)
label: staging → staging eval + human approval → label: production
```

- Promote a label only after the eval ran on **that exact version** and only while the registry is healthy. Fetch by label, never `latest` in production.
- **Rollback = move the label to N-1.** Never delete versions.
- **Prompt + tools move together:** a prompt that names tools is bumped in the same change as the tool set, and a CI check asserts the tool names in the prompt equal the registered tools.
- **Drift check** (pre-release, nightly in staging): Git hash vs registry `content_hash` metadata vs what the production label serves.
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

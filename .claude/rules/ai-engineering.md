---
paths:
  - "**/ai/**/*.py"
  - "**/agents/**/*.py"
  - "**/agent/**/*.py"
  - "**/llm/**/*.py"
  - "**/rag/**/*.py"
  - "**/retrieval/**/*.py"
  - "**/guardrails/**/*.py"
  - "**/evals/**/*.py"
  - "**/prompts/**"
  - "**/*prompt*.yaml"
  - "**/*prompt*.yml"
  - "**/golden/**"
  - "**/memory/**/*.py"
  - "**/*retriev*.py"
  - "**/*vector_store*.py"
  - "**/*model_client*"
  - "**/*model_router*"
  - "**/*llm_gateway*"
  - "**/model_registry*.y*ml"
  - "**/model_routing*.y*ml"
---

# AI engineering guardrails

Path-scoped: loads only for AI code layouts (agents, LLM clients, model routing, RAG and retrieval, memory, guardrails, evals, prompt assets). Projects with other layouts still get the skills; start at `.claude/skills/ai-playbook/SKILL.md` (lifecycle router). Load-bearing invariants only; each links to the reference holding the reasoning and code (paths under `.claude/skills/`). Items about a technology apply only **if the project uses** it.

- **Deterministic controls are the boundary; probabilistic ones are signals.** Authorization, ACL filters in the query, tool allowlists, schemas, business rules, budgets and approval tokens decide. Regex/classifier injection detection, LLM judges and "security rules" in a prompt only raise risk, route to review or log. Guardrails fail closed. → `ai-playbook/playbook.md` §2.5
- **Scope ids (account/org/user/tenant) are injected server-side into tool args from authenticated state, overwriting any model-supplied value,** and kept out of the prompt. The tool service authorizes the caller again. → `agentic-ai-dev/reference/tool-execution-safety.md`
- **Every agent has a non-empty tool allowlist and a test that every allowlisted name resolves to a registered tool** (a typo silently filters an agent to zero tools). → `tool-execution-safety.md`
- **Untrusted content stays data:** tool results, retrieved chunks, fetched pages, file/OCR/transcript text and memories go in user/tool content, never the system prompt; tool results are schema-validated and unknown fields dropped; screen every untrusted channel, not only the last user message. → `ai-playbook/playbook.md` §2.5, §3.2
- **Every model output that drives code passes the output contract** (schema → rules → permission → route). A failed check routes to fallback/review; it is never ignored or best-effort coerced. A model's self-reported confidence is not verification. → `ai-playbook/playbook.md` §2.4
- **One central model client:** explicit timeout, retries only on retryable errors (timeout, 429, 5xx, connection), fallback only to a provider approved for the same data classes, never on auth, invalid request, context overflow, schema or refusal errors. Billing/quota exhaustion is an operational BLOCKED state, not a bug. → `agentic-ai-dev/reference/llm-inference-and-model-routing.md`
- **Budgets (model calls, tool calls, tokens, cost, deadline) are per run/session and shared by sub-agents, retries and fallbacks;** exhaustion stops and returns a typed fallback. → `tool-execution-safety.md`, `ai-playbook/playbook.md` §2.6
- **Side-effecting tools:** idempotency key, audit record written before (or atomically with) the effect, audit failure blocks the effect, approval gate by authority tier; verify the resulting state instead of trusting a tool's 200; an action that settles asynchronously is reported `PENDING_CONFIRMATION` until the system-of-record read-back passes. → `tool-execution-safety.md`, `ai-playbook/reference/engineering-guardrails.md` (L8 read-back)
- **Never log or trace exception text, prompts or user content:** `log_exception(logger, event, exc, **ids)`; spans record `error.type` only; content capture off in production for every tracer. The `post-edit-python-log-pii-advisory.sh` hook flags violations. → `deployment-ci-cd/reference/python-observability.md` §2, `deployment-ci-cd/reference/ai-observability.md`
- **Prompts come from a versioned registry** (no inline prompt strings in feature code); record prompt name/label/version/hash and model id on the model-call span; pin model versions (no `latest` aliases). → `eval-guide/reference/langfuse-prompts.md`, `ai-observability.md` §6
- **Cited source ids must be a subset of the ids retrieved in the same run,** else abstain. Retrieval filters by principal/ACL in the query, never by asking the model. → `ai-playbook/playbook.md` §2.4, §2.7
- **Memory writes are a trust boundary:** typed facts with provenance, redacted, scoped by principal, with TTL and deletion propagation; never store raw model or tool text as fact. → `agentic-ai-dev/reference/agentic-memory-systems.md`
- **Golden/eval data is never edited to make a test pass, never reused as prompt examples, and is PII-scrubbed when derived from production traces.** Tests use scripted fake models; never present a mocked run as proof of live-provider behaviour. → `eval-guide/SKILL.md`
- **Enforcement levels:** BLOCK = deterministic violation, fails the gate · REVIEW = a human decides and the decision is recorded · ADVISORY = pattern-only signal, never proof either way · NOT_APPLICABLE = nothing in scope. `python3 .claude/scripts/check-ai-assets.py --root .` applies them to golden data (manifest, schema, PII), prompt cards (prompt validator), prompt files, notebooks and eval reports (secrets), model ids and routing config (pinning, fallbacks), prompt references (unresolved, label `latest`), governance, model-registry and memory-item records (their owners' validators; structure only) and code signals; `post-edit-ai-patterns.sh` surfaces the code signals on each edit; `/verify` and `/ship` read its exit code. Activation is by what exists: a project without these assets gets no governance demands. Risk tier (T0–T3) and autonomy level (A0–A4) are separate fields. → `.claude/commands/ship.md` (AI release gate)
- **Review with read-only reviewers** (`ai-security-reviewer`, `agentic-ai-reviewer`, `adk-reviewer`, `rag-implementation-reviewer`, `eval-reviewer`); a reviewer that did not run a check reports it NOT RUN.

## By asset type (summary; the linked reference is canonical)

- **Prompt files** (`prompts/**`): prompt cards per the prompt standard §7–§8, validated by `prompt-engineering-patterns/scripts/validate_prompts.py` (via `check-ai-assets.py`). It BLOCKs on schema, name/path mirror, undeclared or unused variables, untrusted slots outside a named delimiter or before `[CONTEXT]`, template logic, secrets, PII in examples, examples failing the exported schema or overlapping eval cases, and budgets. A behaviour change needs a changelog entry and the evals `validate_prompts.py classify` lists (§15). Fetch by label from config, never `latest`. No inline prompt strings in application code. → `prompt-engineering-patterns/SKILL.md`
- **Retrieval code** (retrievers, vector-store queries): ACL/tenant filter inside the query from authenticated state, before ranking; chunks carry the envelope (scope, ACL, trust level, data classification); retrieved text is untrusted data; abstain when evidence is insufficient. → `rag-architect/SKILL.md`, `rag-architect/references/rag-response-contract.md`, `rag-security-reviewer/SKILL.md`
- **Model gateway / routing** (model client, router, registry config): models come from an approved registry by tier, pinned to a dated version (no `latest`/`preview`/`exp` outside a recorded experiment); routing decisions are logged with a reason code; fallbacks are explicit and same-data-class. With LiteLLM, set `fallback_on_unsupported_params=False`. `check-ai-assets.py` reports MODEL_UNPINNED and LITELLM_ROUTER_FALLBACK as REVIEW. → `agentic-ai-dev/reference/agentic-llm-routing.md`, `llm-inference-and-model-routing.md`
- **Memory implementations**: typed records with provenance, principal scope, TTL, schema version and deletion propagation; writes are screened as untrusted input; reads re-check scope. Tests cover cross-scope isolation, expiry and erasure. → `agentic-ai-dev/reference/agentic-memory-systems.md` (Tests Every Memory Feature Needs), `google-adk/reference/adk-memory-artifacts.md` for ADK

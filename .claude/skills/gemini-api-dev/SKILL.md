---
name: gemini-api-dev
description: "Direct Gemini API development with google-genai (Python) and @google/genai (TypeScript). Use when building multimodal applications, function calling, structured output, context caching, embeddings, or code execution with Gemini models — without the ADK framework overhead."
allowed-tools: Bash, Read, Write, Edit, WebFetch
metadata:
  triggers: Gemini API, google-genai, @google/genai, multimodal, Gemini embeddings, context caching, code execution sandbox, Gemini function calling, Gemini structured output, direct Gemini, HttpRetryOptions, thinking_level
  related-skills: google-adk, agentic-ai-dev, python-dev, nestjs-api
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-22"
---

## Iron Law

**ALWAYS FETCH CURRENT API DOCS BEFORE WRITING CODE — fetch `https://ai.google.dev/gemini-api/docs/llms.txt` first, then the specific capability page. Never generate Gemini API calls from memory; the API evolves rapidly.**

# Gemini API Development — Direct API (google-genai / @google/genai)

## When to Use This Skill vs google-adk

| Use Case | This Skill | google-adk skill |
|----------|-----------|-----------------|
| Direct model API calls | ✅ | ❌ |
| Multimodal (image/audio/video) | ✅ | Partial |
| Embeddings API | ✅ | ❌ |
| Context caching | ✅ | ❌ |
| Code execution sandbox | ✅ | ❌ |
| Building structured AI agents | ❌ | ✅ |
| Session management / memory | ❌ | ✅ |
| Multi-agent orchestration | ❌ | ✅ |

## Models

Do not hardcode model ids in code or in this skill — the lineup changes faster than docs. Read the id from config (`settings.agent_model` / `GEMINI_MODEL`, required, no default) and check `https://ai.google.dev/gemini-api/docs/models` for current ids, limits and deprecation dates. A model bump is a release:

1. Probe the new id **on the endpoint you deploy to** (developer API and Vertex differ): one call with your real config (thinking level, schema, tools) must succeed.
2. Run the eval suite on both ids; compare cost, latency and failure rates, not only quality.
3. Roll out gradually with a rollback (`deployment-ci-cd/reference/llmops-release-and-rollout.md`).

## SDKs

- **Python**: `google-genai` — `uv add google-genai`
- **TypeScript/NestJS**: `@google/genai` — `npm install @google/genai`

> **Legacy SDKs are deprecated:** `google-generativeai` (Python) and `@google/generative-ai` (JS) — do not use.

## Quick Start

### Python
```python
from google import genai
from google.genai import types

client = genai.Client()  # developer API: GOOGLE_API_KEY; Vertex: GOOGLE_GENAI_USE_VERTEXAI + project/location via ADC
response = client.models.generate_content(
    model=settings.gemini_model,
    contents="Explain quantum computing",
)
text = answer_text(response)  # see "Empty answers" below; response.text can be None
```

### TypeScript (NestJS)
```typescript
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({});  // reads the same env vars
const response = await ai.models.generateContent({
  model: config.geminiModel,
  contents: "Explain quantum computing",
});
```

Create one client per process and reuse it. Framework-neutral inference rules (timeouts per call class, retry ownership, fallbacks, routing): `agentic-ai-dev/reference/llm-inference-and-model-routing.md`.

## Auth per environment

| Environment | Endpoint | Credential |
|---|---|---|
| local | developer API or Vertex | developer key in a git-ignored `.env`, or ADC (`gcloud auth application-default login`) |
| test / CI | none — fake the client or the model | none |
| staging / production | Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`, project, location) | service-account ADC / workload identity — no API key; fail startup if one is set |

## Sampling and thinking (Gemini 3.x)

- Keep `temperature`, `top_p`, `top_k` at their defaults. Google's Gemini 3 guide: the default temperature 1.0 is recommended and lowering it may cause looping or degraded performance on reasoning tasks; newer generations ignore these fields and return deprecation warnings. Get consistency from `response_schema`, validators and evals instead. Older-model advice ("temperature 0.1 for extraction") does not carry over.
- Control reasoning depth with `types.ThinkingConfig(thinking_level=...)` (`MINIMAL`/`LOW`/`MEDIUM`/`HIGH` in google-genai 1.75) rather than `thinking_budget`; check which levels your model accepts.
- **`max_output_tokens` includes thinking tokens.** If the model thinks up to the cap you get `finish_reason=MAX_TOKENS` with empty or truncated text, and the thinking is still billed. Lower `thinking_level` or raise the cap; never shrink the cap to "save cost" on a reasoning model. Track `usage_metadata.thoughts_token_count`.

## Key Capabilities

| Capability | When to Use | Doc Page |
|-----------|-------------|----------|
| Text generation | Chat, completion, summarization | `text-generation.md.txt` |
| Multimodal | Process images, audio, video, documents | `image-understanding.md.txt` |
| Function calling | Let the model invoke your functions | `function-calling.md.txt` |
| Structured output | Generate valid JSON matching schema | `structured-output.md.txt` |
| Code execution | Run Python in sandboxed environment | fetch from llms.txt |
| Context caching | Cache large contexts for cost efficiency | fetch from llms.txt |
| Embeddings | Semantic search, similarity | `embeddings.md.txt` |

## Documentation Sources

**Always fetch before writing code** — the Gemini API evolves rapidly; never rely on memory.

| Source | URL | Purpose |
|--------|-----|---------|
| Doc index | `https://ai.google.dev/gemini-api/docs/llms.txt` | Discover all available doc pages |
| Models | `https://ai.google.dev/gemini-api/docs/models.md.txt` | Current model IDs and capabilities |
| Function calling | `https://ai.google.dev/gemini-api/docs/function-calling.md.txt` | Tool use patterns |
| Structured output | `https://ai.google.dev/gemini-api/docs/structured-output.md.txt` | JSON schema output |
| Embeddings | `https://ai.google.dev/gemini-api/docs/embeddings.md.txt` | Embedding API |
| Text generation | `https://ai.google.dev/gemini-api/docs/text-generation.md.txt` | Generation parameters |
| Image understanding | `https://ai.google.dev/gemini-api/docs/image-understanding.md.txt` | Multimodal inputs |
| SDK migration | `https://ai.google.dev/gemini-api/docs/migrate.md.txt` | Migrate from legacy SDKs |
| REST API spec | `https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta` | Authoritative API schema |

## Common Commands

```bash
# Python setup
uv add google-genai

# TypeScript setup
npm install @google/genai

# Local only: put the developer key in a git-ignored .env (or a secret manager) and load it
# into the process, e.g. `uv run --env-file .env ...`; never paste keys into shell history or code

# Verify SDK version
python -c "import google.genai; print(google.genai.__version__)"
node -e "const {GoogleGenAI}=require('@google/genai'); console.log('ok')"
```

## Error Handling

> Current codes: `https://ai.google.dev/gemini-api/docs/troubleshooting`.

Retries belong to the SDK, configured once (verified with google-genai 1.75 against a local fake HTTP server — no live call): with `retry_options` unset the SDK makes **one** attempt; with `HttpRetryOptions` a 503 was attempted 3 times and a 400 once. Do not wrap the call in another retry library (`google.api_core.retry` is for the older Google Cloud client libraries, not `google-genai`) and do not stack app-level retries on top — attempts multiply.

```python
from google import genai
from google.genai import errors, types

RETRYABLE = {408, 500, 502, 503, 504}   # 429 deliberately absent: see below

client = genai.Client(
    http_options=types.HttpOptions(
        timeout=30_000,  # milliseconds, per attempt
        retry_options=types.HttpRetryOptions(attempts=3, initial_delay=1.0, max_delay=8.0,
                                             http_status_codes=sorted(RETRYABLE)),
    ),
)


class EmptyAnswer(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def answer_text(response: types.GenerateContentResponse) -> str:
    if response.prompt_feedback and response.prompt_feedback.block_reason:
        raise EmptyAnswer(f"PROMPT_BLOCKED:{response.prompt_feedback.block_reason}")
    if not response.candidates:
        raise EmptyAnswer("NO_CANDIDATES")
    finish = response.candidates[0].finish_reason
    text = response.text or ""
    if finish == types.FinishReason.MAX_TOKENS:
        raise EmptyAnswer("MAX_TOKENS")  # thinking can consume the whole budget
    if finish not in (types.FinishReason.STOP, None) or not text:
        raise EmptyAnswer(f"FINISH_{finish}")
    return text


try:
    text = answer_text(client.models.generate_content(model=settings.gemini_model, contents=prompt))
except errors.APIError as exc:          # after the SDK's own retries
    log_exception(logger, "gemini_call_failed", exc, status_code=exc.code)
    raise ModelUnavailable(code=exc.code) from exc   # route maps to a typed status
except EmptyAnswer as exc:
    log_exception(logger, "gemini_empty_answer", exc, reason=exc.reason)
    raise
```

- Classify by `errors.APIError.code` (`ClientError` = 4xx, `ServerError` = 5xx). Never retry 400/401/403/404; fix the request, key or model id.
- **429 is not in `RETRYABLE`.** `HttpRetryOptions` decides by HTTP status code only, so it cannot tell a per-minute rate limit from an exhausted daily/project quota: with 429 listed, a quota-exhausted 429 was retried like any other (fake server, 3 attempts), contradicting "quota exhausted: never retry" (`agentic-ai-dev/reference/llm-inference-and-model-routing.md` §5). Handle 429 in app code as the single retry layer for it: `RateLimitedError` (bounded retry, honour the delay) only when the error says the wait is short (a RetryInfo delay / `Retry-After`; inspect `exc.details` and confirm the shape on a captured real 429 before relying on it), otherwise `QuotaExhaustedError` (no retry, report BLOCKED). If you keep 429 in the SDK set instead, write down that a quota 429 costs `attempts - 1` extra calls before it surfaces.
- Log with `log_exception` (type, code, ids — never `str(exc)`, prompts or output): `deployment-ci-cd/reference/python-observability.md` §2.
- Empty or blocked answers are typed outcomes, not `""`. Retry SAFETY/RECITATION/MAX_TOKENS only after changing something.

## Multimodal input safety

```python
MAGIC = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg", b"%PDF-": "application/pdf"}
MAX_BYTES = 10 * 1024 * 1024


def sniff_mime(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ValueError("FILE_TOO_LARGE")
    for magic, mime in MAGIC.items():
        if data.startswith(magic):
            return mime
    raise ValueError("UNSUPPORTED_TYPE")   # never trust the extension or client Content-Type


part = types.Part.from_bytes(data=upload, mime_type=sniff_mime(upload))
```

Inline requests have a total size limit (check the current figure in the docs); use the File API for larger media. Fetch media only from allow-listed storage, never a user- or model-supplied URL. Text inside images and PDFs is untrusted input.

## Post-Code Review

After writing Gemini API integration code, dispatch:
- `security-reviewer` — key handling, keyless deployed auth, upload validation
- `ai-security-reviewer` — untrusted content in prompts, tool calls, output handling
- `code-reviewer` — general quality, error handling completeness

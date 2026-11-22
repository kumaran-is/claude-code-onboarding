# Gemini Provider Setup (optional provider extension)

Settings, authentication and audio formats for using Gemini Live (streaming STT / speech-to-speech) and Gemini TTS as voice providers. Live API calls: `gemini-live-api.md`. TTS calls: `gemini-tts.md`. Model-id and auth policy for all Gemini use: `gemini-api-dev` skill.

---

## SDK Installation

```bash
# CORRECT — google-genai, pinned exactly (lockfile + `uv sync --locked` in CI)
uv add "google-genai==<version you verified>"

# WRONG — never use this
# pip install google-generativeai  ← deprecated, different API surface
```

The `google-generativeai` package is the legacy SDK. `google-genai` is the current SDK with Live API support. They are not interchangeable. The examples in this skill were checked against `google-genai` 3.6.1.

---

## Authentication matrix

| Environment | Auth | Provider key present? |
|-------------|------|-----------------------|
| Local development | developer API key from a local `.env` (never committed) | yes, locally only |
| Staging / production on the managed (Vertex AI) endpoint | workload identity / Application Default Credentials (`genai.Client(vertexai=True, project=..., location=...)`) | **no** — startup fails if one is set |
| Browser / app connecting to the Live API directly | short-lived ephemeral token minted by your authenticated backend | never the API key |

Rules: never invent a "managed endpoint API key" variable; never put a key in a prompt, span attribute, log, test fixture or container image; a model id proven on the developer endpoint is re-probed on the managed endpoint before release.

```python
from google import genai
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str
    LIVE_MODEL: str  # no defaults: model ids come from the environment only
    LIVE_VOICE: str
    TTS_MODEL_FAST: str
    TTS_MODEL_QUALITY: str
    TTS_ALLOWED_VOICES: frozenset[str]
    GEMINI_API_KEY: SecretStr | None = None
    USE_MANAGED_AUTH: bool = False

    @model_validator(mode="after")
    def _auth_matrix(self) -> "VoiceSettings":
        deployed = self.ENVIRONMENT in {"staging", "production"}
        if deployed and (not self.USE_MANAGED_AUTH or self.GEMINI_API_KEY is not None):
            raise ValueError("deployed environments use workload identity; no provider API key")
        if not deployed and not self.USE_MANAGED_AUTH and self.GEMINI_API_KEY is None:
            raise ValueError("local development needs GEMINI_API_KEY or USE_MANAGED_AUTH")
        return self
```

```python
def make_genai_client(settings: VoiceSettings) -> genai.Client:
    if settings.USE_MANAGED_AUTH:
        # ADC / workload identity; project + location from GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION
        return genai.Client(vertexai=True)
    assert settings.GEMINI_API_KEY is not None   # guaranteed by _auth_matrix
    return genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())
```

(`google-genai` 3.6.1 reads `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and also `GOOGLE_API_KEY`/`GEMINI_API_KEY` from the environment when not passed, so an ambient key in a deployed container can be picked up without anyone choosing it: keep deployed environments free of provider keys.)

Settings class executed (pydantic-settings 2.16.3, `mypy --strict` clean, 4 tests pass): `LIVE_MODEL` is required; a missing `LIVE_MODEL` fails; `ENVIRONMENT=production` with a key set fails; production keyless passes and parses `TTS_ALLOWED_VOICES` from a JSON list; local with neither key nor managed auth fails. Tests compare against loaded settings, never a literal model id. Generic env-validation rules: `deployment-ci-cd/reference/env-config-validation.md`.

---

## Audio formats

| Direction | Format |
|-----------|--------|
| Input to Live API (user audio) | raw 16-bit PCM, 16 kHz, mono, little-endian; mime `audio/pcm;rate=16000`; small chunks (tens of ms) for latency |
| Output from Live API / TTS | raw 16-bit PCM, 24 kHz, mono, little-endian (wrap in a WAV header before serving a file) |

Validate on the server before sending anything to the provider: size by `Content-Length` before buffering (413 over the cap), exact byte cap while reading, a minimum size (a header-only recording is a few dozen bytes and only fails at the provider as a 400), and the container header for uploads. See `../SKILL.md` "Uploads".

---

## Session limits and reconnect

Read `gemini-live-api.md` section 1 (limits fetched from the provider docs: audio-only 15 min without compression, audio + video 2 min, connection ~10 min with a `go_away` notice, resumption tokens valid 2 h) and section 5 (reconnect with the resumption handle). Do not detect expiry by searching exception text.

---

## Quotas and errors

Quotas (concurrent sessions, requests and tokens per minute) depend on your tier and project: read them from the provider console and rate-limits page; do not copy numbers into code or docs.

| Signal (`google.genai.errors.APIError`) | Cause | Handling |
|------------------------------------------|-------|----------|
| `code == 400` | wrong audio format/rate, empty or header-only audio | do not retry; fixed client code `AUDIO_INVALID` |
| `code == 429` (`RESOURCE_EXHAUSTED`) | quota | bounded backoff with jitter; then `RATE_LIMITED` |
| `code in (401, 403)` | credentials / permission | no retry; alert; check the auth matrix above |
| close code from `receive()` | connection ended | reconnect with the resumption handle, else end with a fixed code |

Make provider failures diagnosable without content: log status code, provider status, mime type, payload byte count and duration; never the provider message, transcript or audio.

---

## Environment variables

```bash
# .env (local only — never committed). Values come from the provider's models page and voice list.
ENVIRONMENT=local
GEMINI_API_KEY=
LIVE_MODEL=
LIVE_VOICE=
TTS_MODEL_FAST=
TTS_MODEL_QUALITY=
TTS_ALLOWED_VOICES=["<voice-a>","<voice-b>"]
```

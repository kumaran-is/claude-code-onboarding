---
name: voice-ai-development
description: "Optional voice extension for AI features — choosing batch STT vs streaming STT vs live speech-to-speech, secure WebSocket voice sessions (auth before accept, caps, backpressure), turn detection and barge-in, text fallback, voice privacy and logging, async worker pipelines with interrupts, and provider references for Gemini Live API, Gemini TTS, LangGraph and Google ADK. Use when building voice assistants, real-time audio streaming, speech-to-text or text-to-speech features."
allowed-tools: Bash, Read, Write, Edit, WebFetch
metadata:
  triggers: voice AI, real-time voice, voice assistant, voice bot, voice agent, speech to text, STT, text-to-speech, TTS, speech synthesis, audio streaming, WebSocket audio, barge-in, interrupt handling, Gemini Live API, Gemini TTS, voice pipeline, conversational voice, async worker pipeline
  related-skills: streaming-protocols, gemini-api-dev, google-adk, agentic-ai-dev, ai-chat, eval-guide
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

# Voice AI Development

> **OPTIONAL extension.** Voice is never required for an AI feature. Build and evaluate the text path first; add voice only when the product needs it. Lifecycle router: `ai-playbook/SKILL.md`. This skill is the single home for voice (it absorbed the former voice engine skill: worker pipeline, interrupts, provider setup).

## Iron Law

**Choose the simplest voice architecture that meets the latency target, put authentication and hard caps in front of every paid audio session, and take model ids from configuration — never from this skill.**

Before using a model id, confirm it on the provider's models page and probe it on every backend you deploy to (`gemini-api-dev`). Every voice failure ends in a fixed code that the client turns into text input.

## 1. Choose the architecture

| Option | Use when | Cost / complexity |
|--------|----------|-------------------|
| Batch: record → upload → STT → text agent → optional TTS | Turn-taking is acceptable (latency budget in seconds) | Lowest; easiest to evaluate and to fall back to text |
| Streaming STT → text agent → streaming TTS | Replies must start soon after the user stops; you keep a text agent you already evaluate | You own barge-in and echo handling (`reference/interrupt-handling.md`) |
| Live speech-to-speech session | Sub-second conversational turn-taking is the requirement | Highest: session limits, reconnects, per-minute cost, harder evals |

Keep the provider choice in one server module; clients speak your protocol, never a provider's. Provider selection by measurement: `reference/provider-comparison.md`.

## 2. Session lifecycle (any provider)

| Rule | Detail |
|------|--------|
| Admission | Subprotocol + authentication BEFORE `accept()`; refuse with 1008. Browsers cannot set WebSocket headers: use a short-lived single-use connect token. One open stream per actor (shared claim with TTL when multi-instance). Rate-limit opens. |
| Caps | Max frame bytes, max stream bytes and seconds, idle timeout, bounded queue → `BACKPRESSURE`. |
| Channels | Audio = binary frames; control (`end_turn`, `stop`) = JSON text frames. No in-band sentinels such as `b"END"`. |
| Ordering | Every server message carries attempt id + monotonic `seq`; the client drops stale or out-of-order messages. |
| Interim vs final | Interim transcripts are replaceable display text; only `final` is stored or drives the agent. |
| Re-authorize | At finalize/stop; end the stream when the token expires mid-stream. |
| Cleanup | The upstream provider session closes in `finally` on every exit path. |

Executed pattern and tests (7 cases): `streaming-protocols/reference/server-stream-lifecycle.md` §3.

## 3. Turn detection and barge-in

- Provider VAD (e.g. Gemini Live) stops generation when the user speaks; you still discard unplayed audio and tell the client (`interrupted` event).
- Truncate assistant history to what was actually spoken (`update_last_bot_on_cutoff`).
- Mute the transcriber (send silence, not nothing) while your own TTS plays, to avoid echo.
- Deliver audio at real-time pace so an interrupt can stop it: `reference/interrupt-handling.md`.

## 4. Failure → text fallback

| Failure | Client code | Server action |
|---------|-------------|---------------|
| STT error / timeout / empty or header-only audio | `AUDIO_INVALID` / `AUDIO_EMPTY` | no retry of the same audio |
| Provider quota (429) | `RATE_LIMITED` | bounded backoff with jitter, then stop |
| Caps exceeded / backpressure | `LIMIT_EXCEEDED` / `BACKPRESSURE` | close the stream |
| Auth failure / expiry | `UNAUTHORIZED` | close 1008 |
| Worker failed N times in a row | `VOICE_UNAVAILABLE` | end the session (`reference/worker-pipeline.md` BaseWorker) |
| Translation failure | pass original text through, flagged | — |

The client switches to text input on every error code. Never return silence as success; never auto-reconnect silently.

## 5. Uploads (batch path)

Reject by `Content-Length` before buffering, then enforce the exact byte cap while reading (413); reject payloads below a minimum size or without the expected container header (a misconfigured recorder uploads a header-only file that only fails at the provider as a 400); per-call STT timeout. Delete temp files after the call.

## 6. Privacy and logging

- Allowed log fields: session/attempt id, error code (enum), HTTP/provider status, mime type, byte count, duration ms, language code.
- Forbidden in logs, spans and metrics: transcript or synthesized text (even a preview), audio, file names, provider error text, `str(exc)`, `exc_info`. Use `log_exception` (`deployment-ci-cd/reference/python-observability.md` §2).
- Consent before capture; retention TTL for stored audio and transcripts; deletion propagates to traces, caches and eval sets; trace access is role-based and tenant-isolated.
- Make provider failures diagnosable without content: status, mime, payload bytes, duration (quota = 429, bad input = 400, auth = 401/403).

## 7. Model ids, auth and dependencies

- Model ids and voice names: settings only, no defaults (`reference/gemini-provider-setup.md` — executed settings class). Voice names come from the provider's current prebuilt-voice list.
- Deployed environments authenticate keyless (workload identity); a developer API key exists only locally; browsers use provider ephemeral tokens or your proxy — never the API key.
- Pin dependencies exactly with a lockfile (`uv add "google-genai==<verified>"`, `uv sync --locked`); never `>=` ranges in a scaffold. SDK: `google-genai`, never `google-generativeai`.
- Version boundary (PyPI, 2026-11-23): google-adk 2.15.0 requires `google-genai>=2.34,<3` and `websockets>=15.0.1,<16`. A service that includes ADK runs google-genai 2.x; a Live/TTS-only service can pin 3.6.1. The Live calls in section 8 have the same signatures on 2.34 (signature-checked).
- Audio files: WAV through stdlib `wave`; MP3 through the ffmpeg CLI. Not pydub: 0.25.1 imports `audioop`, removed in Python 3.13, so it fails to import on 3.14.

## 8. Gemini Live essentials (verified on google-genai 3.6.1)

| ❌ Wrong | ✅ Right |
|---------|---------|
| `session.send(input=..., end_of_turn=True)` (deprecated) | `send_client_content(turns=..., turn_complete=True)`; `send_realtime_input(audio=...)` |
| `send_realtime_input(types.Blob(...))` | keyword-only, ONE field per call: `send_realtime_input(audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))` |
| `await client.aio.live.connect(...)` / `async for m in session` | `async with client.aio.live.connect(model=settings.LIVE_MODEL, config=cfg) as session:` / `session.receive()` |
| one `async for` over `receive()` | `while True:` around it — `receive()` yields one model turn |
| detect expiry from exception text | `go_away` + `session_resumption` handle; `context_window_compression` for long sessions |

Limits from the provider docs (2026-11-22): audio-only sessions 15 min without compression, audio + video 2 min, connections ~10 min, resumption tokens valid 2 h. Code: `reference/gemini-live-api.md`.

## Reference files

| File | Contents |
|------|----------|
| `reference/gemini-live-api.md` | Verified Live API usage, relay across turns, resumption/go_away, proxy rules, errors |
| `reference/gemini-provider-setup.md` | Auth matrix, settings with no model defaults (executed), audio formats, quotas |
| `reference/gemini-tts.md` | Single/multi-speaker TTS, style control, WAV/MP3 export (executed), TTS endpoint, retries |
| `reference/worker-pipeline.md` | Async worker pipeline: base classes, `StreamingConversation` orchestrator, provider selection |
| `reference/worker-pipeline-gemini.md` | Gemini transcriber (executed), synthesizer, LangGraph/ADK agent workers, FastAPI wiring |
| `reference/interrupt-handling.md` | State machine, InterruptibleEvent, rate-limited playback, cutoff history, reconnect |
| `reference/voice-langgraph-integration.md` | LangGraph STT → LLM → TTS graph, endpoint, executed transcription test |
| `reference/voice-adk-integration.md` | ADK 2.15: STT/TTS in code, text-only agent (executed), `run_live` pointer |
| `reference/provider-comparison.md` | Provider-neutral selection criteria and decision record |
| `reference/common-pitfalls.md` | Echo, barge-in, audio format, session end, silent failures |

## Evaluation

Evaluate the text agent on transcripts with the normal golden set; evaluate STT/TTS separately on hash-pinned audio fixtures in the delivered language; a gated live tier replays fixtures through the real STT path (`eval-guide`). Test the protocol: no auth → refused before accept; caps → fixed codes; disconnect → upstream closed.

## Post-Code Review

Dispatch `ai-security-reviewer` (session admission, caps, privacy, prompt/tool safety), `security-reviewer` (auth, secrets), and `code-reviewer` (async lifecycle, error paths). Use `agentic-ai-reviewer` / `adk-reviewer` for the agent part.

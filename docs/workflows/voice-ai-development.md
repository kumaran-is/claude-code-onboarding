# Voice AI Development Workflow

Phases for building Gemini voice features — real-time Live API and TTS synthesis — with LangGraph and Google ADK. Voice is an optional extension: ship and evaluate the text path first.

**Skill:** `voice-ai-development`
**Models:** model ids and voice names come from settings (`LIVE_MODEL`, `TTS_MODEL_FAST`, `TTS_MODEL_QUALITY`, `LIVE_VOICE`), never literals in code or requests. Pick them from the provider's models page and probe each id on every backend you deploy to (`gemini-api-dev` skill).
**SDK:** `google-genai` (NEVER `google-generativeai` — deprecated). google-adk 2.15.0 requires `google-genai>=2.34,<3`: an ADK service runs google-genai 2.x; a Live/TTS-only service can pin 3.6.1.

---

## Phase 0: Decide Modality and Framework

Before writing a line of code, answer these two questions (skill `SKILL.md` section 1):

**Modality:**
| Need | Choose |
|------|--------|
| Real-time voice (barge-in, low latency) | Gemini Live API session behind your WebSocket proxy |
| Batch/one-shot speech synthesis | Gemini TTS models |
| Both (voice assistant) | Live API (or batch STT) for input, TTS for output |

**Framework:**
| Need | Choose |
|------|--------|
| Session memory + Google Cloud deploy | Google ADK (`voice-adk-integration.md`) |
| Fine-grained state control, LangChain tools | LangGraph (`voice-langgraph-integration.md`) |
| Unsure | Start with LangGraph (simpler to debug) |

---

## Phase 1: Environment Setup

```bash
# Exact pins + lockfile; versions you verified on PyPI (never unpinned or >= ranges)
uv add "google-genai==3.6.1"                       # Live/TTS-only service
uv add "langgraph==<verified>" "langchain-google-genai==<verified>"   # LangGraph pipeline
uv add "google-adk==2.15.0"                        # ADK pipeline (pulls google-genai 2.x)
# MP3 export: ffmpeg binary in the image (brew/apt). Not pydub: it fails to import on Python 3.14.

# Local development only: developer key in an uncommitted .env (deployed environments are keyless)
# .env: ENVIRONMENT=local, GEMINI_API_KEY=..., LIVE_MODEL=..., LIVE_VOICE=..., TTS_MODEL_FAST=..., TTS_MODEL_QUALITY=...
uv run python -c "from importlib.metadata import version; import sys; sys.stdout.write(version('google-genai') + '\n')"
```

**Gate:** settings load (`gemini-provider-setup.md`: missing `LIVE_MODEL` fails at startup) and the SDK imports.

---

## Phase 2: Live API — Real-time Voice Streaming

Reference: `.claude/skills/voice-ai-development/reference/gemini-live-api.md`

Steps:
1. Build the session config (section 3: `LiveConnectConfig`, input transcription, `session_resumption`, `context_window_compression`)
2. Send audio with `send_realtime_input(audio=types.Blob(...))`; end the user turn with `audio_stream_end=True` (section 3)
3. Relay model output across turns with `while True:` around `session.receive()`; handle `interrupted` (barge-in) and `go_away` (section 4)
4. Reconnect with the resumption handle (section 5)
5. Put your WebSocket proxy in front: auth and subprotocol BEFORE `accept()`, caps, bounded queue, audio as binary frames, control as text frames (section 6; `streaming-protocols/reference/server-stream-lifecycle.md` section 3)

**Validation:** the executed tests in `gemini-live-api.md` (real `AsyncSession` on a scripted websocket), plus a manual smoke test against your proxy with an authenticated client: binary PCM in, `{"type":"end_turn"}` as a text frame, binary PCM 24 kHz back. Never an in-band audio sentinel.

**Gate:** unauthenticated connection refused before `accept()`; audio round-trip works; `go_away` reconnect resumes the session.

---

## Phase 3: TTS — Text-to-Speech Synthesis

Reference: `.claude/skills/voice-ai-development/reference/gemini-tts.md`

Steps:
1. Choose the model setting (`TTS_MODEL_FAST` vs `TTS_MODEL_QUALITY`) — section 1
2. Implement single-speaker synthesis (section 2)
3. Add multi-speaker support if needed (section 3)
4. Add language switching if needed (section 4)
5. Export WAV/MP3 (section 5, executed) and wrap in a FastAPI endpoint (section 6)

**Validation:**
```bash
# The server picks the model from settings; the client sends text and an allow-listed voice only
curl -X POST http://localhost:8000/tts \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text": "Hello, this is a test.", "tier": "fast", "voice": "<voice from TTS_ALLOWED_VOICES>"}' \
  --output test.wav
file test.wav   # RIFF (little-endian) data, WAVE audio
```

**Gate:** WAV file is non-empty and plays; a voice outside `TTS_ALLOWED_VOICES` is rejected with 422.

---

## Phase 4: LangGraph Voice Pipeline (if using LangGraph)

Reference: `.claude/skills/voice-ai-development/reference/voice-langgraph-integration.md`

Steps:
1. Define `VoiceAgentState` (section 1)
2. Implement `voice_input_node` — transcription via the Live API (section 2, executed)
3. Implement `llm_response_node` — agent logic, text only (section 3)
4. Implement `voice_output_node` — async TTS client, no worker thread (section 4)
5. Assemble the graph `voice_input -> llm_response -> voice_output -> END` (section 5) and the endpoint (section 6)

**Validation:** the executed graph test in section 8 (real `AsyncSession` on a scripted websocket; patch the module's client object). Assert on the returned state, never print it.

**Gate:** all three nodes execute, state flows end to end, `audio_output` is non-empty, and an empty transcript ends the turn with a fixed error code.

---

## Phase 5: ADK Voice Pipeline (if using ADK)

Reference: `.claude/skills/voice-ai-development/reference/voice-adk-integration.md` (google-adk 2.15.0)

Steps:
1. Read section 1 first: STT and TTS are deterministic code around the agent; only text reaches the model, never audio or hex
2. One `LlmAgent` behind a `Runner` (section 2, executed). No `SequentialAgent`: ADK 2.x deprecates it in favour of `Workflow`
3. `user_id` from the authenticated principal; one session per conversation (`create_session` once)
4. HTTP endpoint with a capped body (section 3) or the WebSocket admission pattern (section 4); `run_live` for speech-to-speech (section 5)

**Validation:** the section 2 test (scripted `BaseLlm`, fake STT/TTS; the model saw only the transcript) and the section 6 endpoint tests: missing auth → 401 before any provider call, body over the cap → 413, header-only audio → 422 `AUDIO_EMPTY`.

**Gate:** tests pass on the pinned ADK version with `DeprecationWarning` raised as an error.

---

## Phase 6: Testing

Mandatory tests:
- [ ] Happy path: audio in -> transcript -> response -> audio out (scripted provider, no live call)
- [ ] Empty or header-only audio → fixed client code (`AUDIO_EMPTY` / `AUDIO_INVALID`), never a silent empty reply
- [ ] Barge-in: `interrupted` drops unplayed audio and cancels in-flight generation (`interrupt-handling.md`)
- [ ] Quota: `google.genai.errors.APIError` with `code == 429` → bounded backoff, then `RATE_LIMITED`
- [ ] Disconnect: upstream session closed in `finally`, tasks cancelled and drained
- [ ] Logs carry codes, sizes and ids only — no transcript, reply text or audio

```bash
uv run pytest tests/test_voice_agent.py -q   # report the command's own exit code
```

Mocked/scripted provider tests are not live validation: a gated live tier replays hash-pinned audio fixtures (`eval-guide`).

---

## Phase 7: Code Review and Security

Dispatch reviewers after implementation:
```
ai-security-reviewer — session admission, caps, prompt/tool safety, voice privacy
security-reviewer    — auth before accept, secrets, input validation
code-reviewer        — WebSocket lifecycle, error paths, no silent failures
adk-reviewer / agentic-ai-reviewer — the agent part
```

Security checklist:
- [ ] Deployed environments are keyless (workload identity); a developer key exists only in a local `.env`; browsers get ephemeral tokens or go through your proxy
- [ ] Authentication and subprotocol checked BEFORE `accept()`; frame/byte/time/idle caps; bounded queues
- [ ] Audio, transcripts and replies are never logged (PII); log byte counts and codes
- [ ] Content policy blocks surface as explicit errors — not silent empty audio
- [ ] Model id never accepted from the client; voices from the configured allow-list

---

## Phase 8: Deploy

Reference: `adk-deploy-guide` skill (ADK), `gcp-cloud-run` skill (LangGraph/FastAPI)

- Cloud Run with the service's own service account and the Vertex AI endpoint (`genai.Client(vertexai=True)`): no provider API key in the service, no `--set-env-vars` holding a secret
- Require authentication on the service (no `--allow-unauthenticated` for a paid voice session unless your proxy authenticates every connection)
- Session-local state (in-memory sessions or pipelines) needs sticky routing or a persistent session service; `InMemorySessionService` is single-instance only
- Cloud Run sends SIGTERM 10 s before SIGKILL: close upstream Live sessions and drain tasks within that window

**Gate:** health endpoint responds 200; an authenticated WebSocket round-trip works against the deployed URL; an unauthenticated one is refused.

---

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| `google-generativeai` SDK | different API surface, deprecated | `google-genai` only |
| `session.send(input=..., end_of_turn=True)` | deprecated call | `send_client_content(...)` / `send_realtime_input(audio=...)` |
| In-band `END` audio sentinel | control mixed with audio | text control frame; `audio_stream_end=True` upstream |
| One `async for` over `receive()` | second turn never read | `while True:` around it |
| Blocking the event loop with sync TTS | endpoint stalls under load | `client.aio.models.generate_content` (or `asyncio.to_thread` for a sync SDK call) |
| Empty audio on content block | silent failure | check the audio part is non-empty; raise a fixed code |
| ADK + google-genai 3.x in one project | resolver failure | google-adk 2.15.0 requires `google-genai<3` |
| pydub for MP3 | `ModuleNotFoundError: audioop` on 3.13+ | ffmpeg CLI (`gemini-tts.md` section 5) |
| Logging audio bytes | PII leak | log byte counts only |

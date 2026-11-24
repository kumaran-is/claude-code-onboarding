# Google ADK + Voice (optional extension)

> Framework: `google-adk` 2.15.0. ADK agent patterns in general: `google-adk` skill. Model ids and voices come from settings (`AGENT_MODEL`, `LIVE_MODEL`, `TTS_MODEL_FAST`, `LIVE_VOICE`), never literals.
> Executed on google-adk 2.15.0 (Python 3.14.10, DeprecationWarning raised as an error): section 2 (`voice_turn`) with a scripted `BaseLlm` subclass and fake STT/TTS, 1 test passes, no provider call; control: putting the audio hex into the prompt fails the "model saw text only" assertion. Signatures of `Runner`, `run_async`, `run_live`, `LiveRequestQueue`, `InMemorySessionService.create_session` read from the installed 2.15.0 package.
> Dependency boundary: google-adk 2.15.0 requires `google-genai>=2.34,<3` (it resolved 2.34.0), so an ADK voice service does not run on google-genai 3.6.1. Pin what the ADK release allows and keep the Live API helpers to the signatures shared by both lines (`gemini-live-api.md`).
---

## 1. Design correction (read first)

The earlier version of this file routed audio THROUGH the model: the client sent hex-encoded PCM, the server put `audio_bytes_hex:<...>` into the user message, and LLM "coordinator" agents copied that hex into `transcribe_audio` / `synthesize_audio` tool calls. Removed because:

| Problem | Consequence |
|---------|-------------|
| Audio bytes as hex text in the prompt | Prompt tokens grow with audio length (a few seconds of 16 kHz PCM is tens of thousands of hex characters): cost and context-window failure — a denial-of-wallet path |
| An LLM copies bytes into a tool argument | The model can truncate or alter the hex; there is no reason to make a deterministic step probabilistic |
| Three LLM agents for STT → reply → TTS | Three paid model calls per turn where one is needed |
| `user_id="voice-user"` for every connection | Every caller shared one identity and one session namespace (no tenant/user isolation) |
| `await websocket.accept()` before any auth; `"END"` text sentinel mixed with audio | Anonymous callers could drive paid calls; control and data shared a channel |

Rule: STT and TTS are deterministic code around the agent. Only text reaches the agent. User identity comes from the authenticated principal.

---

## 2. One voice turn (executed)

```python
from collections.abc import Awaitable, Callable

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME = "voice-assistant"


def build_runner(model: str | BaseLlm) -> tuple[Runner, InMemorySessionService]:
    agent = LlmAgent(
        name="voice_assistant",
        model=model,  # settings.AGENT_MODEL in production
        instruction=(
            "You are a helpful voice assistant. Reply in short plain sentences that "
            "read well aloud: no markdown, no lists."
        ),
    )
    sessions = InMemorySessionService()  # use a persistent session service in production
    return Runner(agent=agent, app_name=APP_NAME, session_service=sessions), sessions


async def voice_turn(
    runner: Runner,
    *,
    user_id: str,  # from the authenticated principal, never a constant
    session_id: str,
    pcm16_16khz: bytes,
    transcribe: Callable[[bytes], Awaitable[str]],
    synthesize: Callable[[str], Awaitable[bytes]],
) -> tuple[str, bytes]:
    transcript = await transcribe(pcm16_16khz)  # code, not a tool call: audio never enters the prompt
    if not transcript:
        raise ValueError("AUDIO_EMPTY")
    message = types.Content(role="user", parts=[types.Part(text=transcript)])
    reply = ""
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            reply = "".join(p.text or "" for p in event.content.parts)
    if not reply:
        raise RuntimeError("AGENT_EMPTY_REPLY")
    return reply, await synthesize(reply)  # code again: TTS outside the agent
```

Executed test: a scripted `BaseLlm` subclass records what the model received; the turn returns the scripted reply and the fake TTS bytes, and the model saw only `"turn on the lights"` — never audio. This is a scripted fake, not proof of live-model behaviour.

- `transcribe`: the executed `voice_input_node` pattern in `voice-langgraph-integration.md` (Live API input transcription), or any STT provider (`provider-comparison.md`).
- `synthesize`: `gemini-tts.md` `synthesize_speech` run with `asyncio.to_thread`, or any TTS provider.
- Create the session once per conversation: `await sessions.create_session(app_name=APP_NAME, user_id=principal.user_id, session_id=conversation_id)`.

---

## 3. HTTP endpoint

```python
@app.post("/voice/turn")
async def voice_turn_endpoint(
    request: Request, user: Principal = Depends(current_user)
) -> Response:
    pcm = await read_capped_body(request, max_bytes=MAX_TURN_BYTES, min_bytes=MIN_TURN_BYTES)  # 413 / 400 before any provider call
    try:
        reply, audio = await voice_turn(
            runner, user_id=user.id, session_id=user.conversation_id, pcm16_16khz=pcm,
            transcribe=stt, synthesize=tts,
        )
    except ValueError:
        return JSONResponse({"code": "AUDIO_EMPTY"}, status_code=422)      # client falls back to text input
    except Exception as exc:
        log_exception(logger, "voice_turn_failed", exc, request_id=request.state.request_id)
        return JSONResponse({"code": "VOICE_UNAVAILABLE"}, status_code=503)
    return Response(pcm_to_wav(audio), media_type="audio/wav")
```

Illustrative (not executed): `read_capped_body` rejects by `Content-Length` first, then enforces the exact byte cap while reading, and rejects payloads below a minimum size or without the expected container header. `log_exception`: `deployment-ci-cd/reference/python-observability.md` §2.

---

## 4. WebSocket voice

For a streaming turn over WebSocket, use the admission and caps pattern in `streaming-protocols/reference/server-stream-lifecycle.md` §3 (subprotocol + auth before `accept()`, one stream per actor, frame/byte/time/idle caps, bounded queue, audio as binary frames, `{"type":"end_turn"}` as a text control frame, attempt id + `seq` on every server message). On `end_turn`, call `voice_turn` with the buffered audio and the principal's `user_id`.

---

## 5. Native ADK live streaming (speech-to-speech)

ADK 2.15.0 exposes a bidirectional live runner: `Runner.run_live(*, user_id, session_id, live_request_queue, run_config, session=None)` with `LiveRequestQueue` (`send_realtime`, `send_content`, `send_activity_start`, `send_activity_end`, `send_audio_stream_end`, `close`) and `RunConfig` fields including `response_modalities`, `speech_config`, `input_audio_transcription`, `output_audio_transcription`, `session_resumption`, `context_window_compression`. Use it when a live speech-to-speech session is required (`../SKILL.md` architecture choice). It was not executed here: follow the `google-adk` skill and the ADK streaming docs for the current usage, and still put the WebSocket admission and caps in front of it.

---

## 6. Testing

- Unit-test `voice_turn` with a scripted `BaseLlm` subclass (section 2) and fake STT/TTS; assert the model never receives bytes or hex.
- Test the endpoint: missing auth → 401 before any provider call; body over the cap → 413 without reading it fully; header-only audio → 422 `AUDIO_EMPTY`; STT failure → 503 `VOICE_UNAVAILABLE` and the client shows text input.
- Assert logs contain codes, sizes and ids only (no transcript or reply text).
- Eval the agent on text transcripts with the normal golden set (`eval-guide`); evaluate STT separately on hash-pinned audio fixtures.

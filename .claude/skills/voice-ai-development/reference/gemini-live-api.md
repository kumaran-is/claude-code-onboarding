# Gemini Live API — Real-time Voice (optional provider extension)

> OPTIONAL. Use only when a live speech-to-speech session is required (see the architecture choice in `../SKILL.md`). Verified against `google-genai` 3.6.1 (Python) by executing the code in sections 3-5 against a real `AsyncSession` wired to a scripted fake websocket (no network, no provider call). Re-check signatures for your pinned SDK version.
>
> Model id and voice name come from settings (`LIVE_MODEL`, `LIVE_VOICE`), never from code or this file. Pick them from the provider's models page and prebuilt-voice list, then probe the id on every backend you deploy to (`gemini-api-dev` skill).

---

## 1. Facts to design around

| Fact | Value | Source |
|------|-------|--------|
| Input audio | raw 16-bit PCM, 16 kHz, little-endian, mime `audio/pcm;rate=16000` | Live API docs |
| Output audio | raw 16-bit PCM, 24 kHz, little-endian | Live API docs |
| Session length without compression | audio-only 15 min; audio + video 2 min | Live API session-management docs |
| Connection lifetime | around 10 min; the server sends `go_away` before it ends | same page |
| Longer sessions | `context_window_compression` (sliding window) | same page |
| Resume after a dropped connection | `session_resumption`; tokens valid 2 h after the last session ends | same page |
| Browser → provider directly | use ephemeral tokens, not a standard API key | Live API docs |

Limits change: re-read the session-management page before relying on a number (fetched 2026-11-22).

---

## 2. API correctness (WRONG → RIGHT)

| ❌ Wrong | ✅ Right | Evidence |
|---------|---------|----------|
| `await session.send(input=..., end_of_turn=True)` | `send_client_content(turns=..., turn_complete=True)` for text turns; `send_realtime_input(...)` for media | SDK marks `session.send` deprecated |
| `send_realtime_input(types.Blob(...))` (positional) | `send_realtime_input(audio=types.Blob(...))` | keyword-only: positional raises `TypeError` (executed) |
| `send_realtime_input(text=..., audio_stream_end=True)` | one field per call | raises `ValueError: Only one argument can be set` (executed) |
| `types.AudioChunk(...)` as realtime input | `types.Blob(data=..., mime_type=...)` | `audio=`/`video=`/`media=` accept `Blob` |
| `session = await client.aio.live.connect(...)` | `async with client.aio.live.connect(model=..., config=...) as session:` | `connect` returns an async context manager, not an awaitable |
| `async for msg in session:` | `async for msg in session.receive():` | `AsyncSession` is not iterable |
| One `async for msg in session.receive()` relay loop | wrap it in `while True:` | `receive()` yields ONE model turn then stops (executed: second turn never read) |
| `google.api_core.exceptions.ResourceExhausted` | `google.genai.errors.APIError` (`ClientError`/`ServerError`), branch on `exc.code` | `google-api-core` is not a dependency of `google-genai` |
| `"SESSION_EXPIRED" in str(exc)` | handle `msg.go_away` + reconnect with the resumption handle | string-matching exception text is fragile and leaks it into code paths |
| End of user turn = in-band `b"END"` audio sentinel | client sends a text control frame; server calls `send_realtime_input(audio_stream_end=True)` (or `activity_end` when automatic VAD is disabled) | control and audio are different channels |

---

## 3. Config and send helpers (executed)

```python
from google.genai import live, types


def live_config(voice_name: str, resume_handle: str | None) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),   # user speech → text events
        session_resumption=types.SessionResumptionConfig(handle=resume_handle),
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow()
        ),
    )


async def send_user_audio(session: live.AsyncSession, pcm16_16khz: bytes) -> None:
    await session.send_realtime_input(
        audio=types.Blob(data=pcm16_16khz, mime_type="audio/pcm;rate=16000")
    )


async def end_user_audio(session: live.AsyncSession) -> None:
    await session.send_realtime_input(audio_stream_end=True)


async def send_user_text(session: live.AsyncSession, text: str) -> None:
    await session.send_client_content(
        turns=types.Content(role="user", parts=[types.Part(text=text)]), turn_complete=True
    )
```

Executed wire shapes: `{"realtime_input": {"audio": {...}}}`, `{"realtime_input": {"audioStreamEnd": true}}`, `{"client_content": {..., "turnComplete": true}}`.

Camera frames (multimodal, optional): `send_realtime_input(video=types.Blob(data=jpeg, mime_type="image/jpeg"))` at a low frame rate; audio + video sessions have the much shorter limit in section 1.

---

## 4. Relay model output across turns (executed)

```python
class ClientChannel(Protocol):
    async def send_audio(self, pcm: bytes) -> None: ...
    async def send_event(self, kind: str, **fields: Any) -> None: ...


async def relay_model_to_client(session: live.AsyncSession, client: ClientChannel) -> str | None:
    """Returns the latest resumption handle when the server announces go_away."""
    handle: str | None = None
    while True:                                   # receive() yields ONE model turn, then stops
        async for msg in session.receive():
            update = msg.session_resumption_update
            if update and update.resumable and update.new_handle:
                handle = update.new_handle
            if msg.go_away is not None:
                return handle                     # caller reconnects with this handle
            content = msg.server_content
            if content is None:
                continue
            if content.interrupted:               # barge-in: client drops unplayed audio
                await client.send_event("interrupted")
                continue
            if msg.data:
                await client.send_audio(msg.data)
            if content.input_transcription and content.input_transcription.text:
                # interim text is replaceable; only finished=True is authoritative
                await client.send_event(
                    "final" if content.input_transcription.finished else "interim",
                    text=content.input_transcription.text,
                )
            if content.turn_complete:
                await client.send_event("turn_complete")
```

Executed scenario: resumption update `h1` → interim + final transcription → audio → turn complete → audio → interrupted → turn complete → resumption update `h2` → `go_away`. Result: both turns' audio relayed, events `interim, final, turn_complete, interrupted, turn_complete`, handle `h2` returned. `ruff` and `mypy --strict` clean.

Transcript text travels to the client in messages only. It is never logged, put in a span attribute or stored outside the conversation record (see `../SKILL.md` privacy rules).

---

## 5. Reconnect on go_away (sketch — compose from the executed pieces)

```python
async def run_live(settings: Settings, client: genai.Client, channel: ClientChannel,
                   audio_in: asyncio.Queue[bytes]) -> None:
    handle: str | None = None
    for attempt in range(settings.LIVE_MAX_RECONNECTS):
        config = live_config(settings.LIVE_VOICE, resume_handle=handle)
        async with client.aio.live.connect(model=settings.LIVE_MODEL, config=config) as session:
            async with asyncio.TaskGroup() as tg:
                sender = tg.create_task(pump_audio(session, audio_in))   # send_user_audio loop
                handle = await relay_model_to_client(session, channel)
                sender.cancel()
        if handle is None:
            await channel.send_event("error", code="LIVE_SESSION_ENDED")  # client → text input
            return
    await channel.send_event("error", code="LIVE_RECONNECT_LIMIT")
```

Not executed end to end (it needs a live session). The pieces it calls are executed above. A connection or protocol failure surfaces from `receive()` as `google.genai.errors.APIError` carrying the websocket close code; map it to a fixed client code, log `error_type` and `code` only, and let the caller decide whether to reconnect.

---

## 6. Serving it to a browser or app

Never expose the paid session through an open WebSocket. The server-side proxy MUST follow `streaming-protocols/reference/server-stream-lifecycle.md` section 3: subprotocol and authentication BEFORE `accept()`, one stream per actor, frame/byte/time/idle caps, bounded queue ending in `BACKPRESSURE`, audio as binary frames and control as text frames, attempt id + monotonic `seq` on every server message, upstream session closed in `finally`.

```
browser/app ──WS (auth before accept, caps)──► your proxy ──Live session──► provider
          ◄── binary PCM 24 kHz + JSON events {type, attempt, seq} ◄──────────┘
```

Direct client-to-provider connections are an alternative only with provider ephemeral tokens minted by your authenticated backend; you then lose server-side caps, so apply quota per user on token minting.

---

## 7. Errors (google-genai)

| Signal | Meaning | Handling |
|--------|---------|----------|
| `APIError.code == 429` / status `RESOURCE_EXHAUSTED` | quota | back off with jitter (bounded attempts), then fixed client code `RATE_LIMITED`; never auto-retry a live audio turn the user already spoke without telling them |
| `APIError.code == 400` | bad input (format, size, empty or header-only audio) | do not retry; `AUDIO_INVALID` |
| `APIError.code in (401, 403)` | credentials / permission | do not retry; alert; `UNAVAILABLE` to client |
| `APIError` with a websocket close code from `receive()` | connection ended | reconnect with the resumption handle if you have one, else end with a fixed code |
| `asyncio.CancelledError` | your own shutdown / client left | re-raise; close the session via the `async with` |

Log fields: `error_type`, `code`, `status`, mime type, byte count, duration, attempt id. Never the exception message, provider error text, transcript or audio (`deployment-ci-cd/reference/python-observability.md` section 2, `log_exception`).

---

## 8. Voices and style

Voice names come from the provider's prebuilt-voice list (the docs list about 30; their examples use names such as `Kore` and `Puck`). Do not hard-code a list here: it changes. Steer style through the system instruction ("speak calmly and briefly"). Custom voices, if your provider offers them, have their own consent and licensing requirements: check the provider's voices API docs before using one.

Framework wiring: LangGraph → `voice-langgraph-integration.md`; ADK → `voice-adk-integration.md`; worker pipeline with interrupts → `worker-pipeline.md`, `interrupt-handling.md`.

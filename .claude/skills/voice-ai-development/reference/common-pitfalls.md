# Common Pitfalls — Voice AI Engine with Gemini

Issues encountered when building voice AI engines with Gemini Live API and Gemini TTS. Includes both universal voice AI pitfalls and Gemini-specific traps.

---

## Gemini-Specific Pitfalls

### 1. Wrong SDK Package

**Problem:** Code fails to import or uses deprecated API surface.

**Cause:** Using `google-generativeai` instead of `google-genai`.

```python
# WRONG — deprecated, different API surface, no Live API support
from google.generativeai import ...
import google.generativeai as genai

# CORRECT — current SDK with Live API support
from google import genai
from google.genai import types
client = make_genai_client(settings)   # auth matrix: gemini-provider-setup.md
```

**Fix:** `uv add "google-genai==<verified version>"` (exact pin + lockfile). Uninstall `google-generativeai` if present.

---

### 2. Polling Gemini Live API

**Problem:** Transcriptions never arrive or API returns errors.

**Cause:** Using HTTP polling (`generate_content` with audio) instead of WebSocket for real-time audio.

```python
# WRONG — polling does not work for real-time audio
response = await client.aio.models.generate_content(
    model=settings.LIVE_MODEL,
    contents=audio_bytes  # Not how Live API works
)

# CORRECT — Live session (async context manager), keyword-only realtime input
async with client.aio.live.connect(model=settings.LIVE_MODEL, config=config) as session:
    await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
```

`await client.aio.live.connect(...)` (no `async with`) and positional `send_realtime_input(types.Blob(...))` both fail: the first returns a context manager, the second raises `TypeError` (verified on google-genai 3.6.1).

**Rule:** Gemini Live API is WebSocket-only. Any code that treats it like a regular `generate_content` call will fail.

---

### 3. Wrong Audio Format Sent to Gemini Live API

**Problem:** API returns `INVALID_ARGUMENT` or transcriptions are garbled.

**Cause:** Sending audio at wrong sample rate, wrong encoding, or without the correct MIME type.

| Requirement | Value |
|-------------|-------|
| Sample rate | **16,000 Hz** (not 8kHz, not 44.1kHz) |
| Channels | **1 (mono)** |
| Bit depth | **16-bit signed little-endian** |
| MIME type | `audio/pcm;rate=16000` |

```python
# WRONG — missing rate, wrong format (and positional: TypeError)
await session.send_realtime_input(types.Blob(data=chunk, mime_type="audio/raw"))

# CORRECT
await session.send_realtime_input(
    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
)
```

**Fix:** Validate audio format at the point it enters the pipeline. Convert client audio before passing to the transcriber if needed (use `pydub`).

---

### 4. Not Handling Barge-in (Gemini Stops Mid-Sentence)

**Problem:** Bot audio stops abruptly mid-sentence when user speaks, but the pipeline continues sending the remaining audio to the client.

**Cause:** Gemini Live API stops generating when it detects user voice (native barge-in). The audio that was already generated may still be in the synthesis queue or being delivered. If the delivery loop is not checking for interrupts, audio already queued continues playing.

**Fix:** Wire `InterruptibleEvent` and check stop condition before every chunk. See `interrupt-handling.md` § Rate-Limited Audio Delivery.

```python
# WRONG — no interrupt check
async for chunk_result in synthesis_result.chunk_generator:
    await websocket.send_bytes(chunk_result.chunk)

# CORRECT — interrupt check before every chunk
async for chunk_result in synthesis_result.chunk_generator:
    if stop_event.is_interrupted():
        return synthesis_result.get_message_up_to(chunk_idx * seconds_per_chunk), True
    await websocket.send_bytes(chunk_result.chunk)
    await asyncio.sleep(max(seconds_per_chunk - elapsed, 0))
```

---

### 5. Echo Feedback — Transcriber Picks Up Synthesized Audio

**Problem:** Bot responds to its own speech — conversation becomes an infinite loop.

**Cause:** Transcriber is active while bot is speaking. If the user's microphone picks up the speaker output, the transcriber transcribes the bot's own voice.

**Fix:** Mute the transcriber before sending audio to the output device. Unmute after delivery is complete.

```python
# In send_speech_to_output:
transcriber.mute()
try:
    # ... deliver audio chunks ...
finally:
    transcriber.unmute()
```

Also, send silence (not nothing) to keep the Gemini Live API session alive during mute:

```python
def send_audio(self, chunk: bytes) -> None:
    if not self.is_muted:
        self.input_queue.put_nowait(chunk)
    else:
        self.input_queue.put_nowait(b"\x00" * len(chunk))  # Silence, not skip
```

---

### 6. Gemini Live Session / Connection End

**Problem:** Transcriptions or audio stop after the first turn, or after several minutes.

**Causes (verified):**
- `session.receive()` yields ONE model turn and then stops: a single `async for` relay goes quiet after turn one. Wrap it in `while True:`.
- Connections last around 10 minutes (the server sends `go_away` first); sessions without context compression are limited (audio-only 15 min, audio + video 2 min).

**Fix:** handle `go_away`, keep the latest `session_resumption_update.new_handle`, reconnect with `SessionResumptionConfig(handle=...)`, enable `context_window_compression` for long sessions. Never detect expiry by searching exception text. Code: `gemini-live-api.md` sections 4-5.

---

## Universal Voice AI Pitfalls

### 7. Audio Jumping / Cutting Off

**Problem:** Bot's audio plays in fragments, with gaps or overlapping streams.

**Cause:** Sending text to the synthesizer in multiple small chunks (word-by-word or sentence-by-sentence) causes multiple TTS API calls, each producing a separate audio stream.

```python
# WRONG — multiple TTS calls
async for sentence in llm_stream:
    yield AgentResponse(text=sentence)  # Each sentence → separate TTS call

# CORRECT — buffer entire response, single TTS call
full_response = ""
async for chunk in llm_stream:
    full_response += chunk
yield AgentResponse(text=full_response)  # One TTS call
```

---

### 8. Interrupts Not Working — All Chunks Sent Immediately

**Problem:** User cannot interrupt the bot. Bot continues speaking even when user starts talking.

**Cause:** All audio chunks are sent to the client at once, filling the client's buffer. By the time an interrupt arrives, the audio is already queued for playback on the client.

**Fix:** Rate-limit chunk delivery to real-time speed. One chunk is sent, then the loop waits for the chunk's audio duration before sending the next.

```python
# WRONG — sends all chunks as fast as possible
async for chunk in synthesis_result.chunk_generator:
    output_device.consume_nonblocking(chunk)

# CORRECT — one chunk per real-time interval
async for chunk in synthesis_result.chunk_generator:
    if stop_event.is_interrupted():
        return  # Interrupt handled
    output_device.consume_nonblocking(chunk)
    await asyncio.sleep(max(seconds_per_chunk - elapsed, 0))
```

**Calculating `seconds_per_chunk`:**
```python
# Gemini TTS output: 24kHz, 16-bit PCM, 4096 bytes
seconds_per_chunk = 4096 / 2 / 24_000  # = 0.0853 seconds
```

---

### 9. Memory Leaks from Unclosed Streams

**Problem:** Memory usage grows continuously; WebSocket connections accumulate.

**Cause:** Gemini Live sessions, WebSocket connections, or asyncio tasks not closed on disconnect or error.

```python
# WRONG — no cleanup on error
async def conversation_endpoint(websocket):
    conversation = create_conversation()
    await conversation.start()
    async for message in websocket.iter_bytes():
        conversation.receive_audio(message)

# CORRECT — always terminate in finally
async def conversation_endpoint(websocket):
    conversation = None
    try:
        conversation = create_conversation()
        await conversation.start()
        async for message in websocket.iter_bytes():
            conversation.receive_audio(message)
    except WebSocketDisconnect:
        log.info("client_disconnected")
    except Exception as exc:
        log.error("conversation_error", error_type=type(exc).__name__)
        raise
    finally:
        if conversation:
            await conversation.terminate()
```

---

### 10. Conversation History Not Updated on Interrupt

**Problem:** After an interrupt, the bot's next response ignores what was cut off and treats it as if the full response was spoken.

**Cause:** Agent history still contains the full generated text, not the partial text that was actually spoken.

**Fix:** Call `update_last_bot_on_cutoff(partial_message)` after detecting cutoff:

```python
message_sent, cut_off = await send_speech_to_output(...)
if cut_off:
    agent.history.update_last_bot_on_cutoff(message_sent)
```

---

### 11. Silent Failures in Worker Loops

**Problem:** Pipeline appears to run but produces no output. No error messages.

**Cause:** Exception swallowed in worker `_run_loop`.

```python
# WRONG — swallows errors silently
async def _run_loop(self):
    while self.active:
        try:
            item = await self.input_queue.get()
            await self.process(item)
        except Exception:
            pass  # Error disappeared

# CORRECT — always log and handle
async def _run_loop(self):
    while self.active:
        try:
            item = await self.input_queue.get()
            await self.process(item)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log.error("worker_error", error_type=type(exc).__name__)
            # Continue for transient errors; raise for fatal
```

---

### 12. WebSocket Connection Drops

**Problem:** Conversations drop after ~30–60 seconds of silence.

**Cause:** No heartbeat. Proxy or firewall closes idle WebSocket connections.

**Fix:** Send a periodic ping from server:

```python
async def heartbeat(websocket: WebSocket) -> None:
    while True:
        try:
            await websocket.send_json({"type": "ping"})
            await asyncio.sleep(25)  # Ping every 25 seconds
        except Exception as exc:   # socket gone: log and stop; the receive loop ends the session
            log.info("heartbeat_stopped", error_type=type(exc).__name__)
            return
```

---

## Summary Table

| Pitfall | Root Cause | Fix |
|---------|-----------|-----|
| Wrong SDK | `google-generativeai` instead of `google-genai` | Use `google-genai` only |
| Live API polling | HTTP instead of WebSocket | `async with client.aio.live.connect(...)`; `send_realtime_input(audio=...)` |
| Wrong audio format | Wrong sample rate or MIME type | 16kHz PCM, `audio/pcm;rate=16000` |
| Barge-in not handled | No interrupt check in delivery loop | `InterruptibleEvent` + stop check |
| Echo feedback | Transcriber active during bot speech | `transcriber.mute()` before delivery |
| Relay stops / session ends | `receive()` is one turn; connection ~10 min | `while True` around `receive()`; `go_away` + resumption handle |
| Audio jumping | Multiple TTS calls | Buffer full response before TTS |
| Interrupts broken | All chunks sent immediately | Rate-limit to real-time speed |
| Memory leaks | No cleanup on disconnect | Always terminate in `finally` |
| History stale after interrupt | Full text in history, not partial | `update_last_bot_on_cutoff()` |
| Silent failures | Swallowed exceptions | Log + rethrow in worker loops |
| Connection drops | No heartbeat | Periodic ping every 25s |

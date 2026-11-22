# Interrupt Handling — State Machine, InterruptibleEvent, and Graceful Shutdown

Interrupt handling is non-negotiable in voice AI. Without it, users must wait for the bot to finish every sentence before speaking — a fatal UX flaw. This reference covers the full interrupt system.

---

## State Machine

The pipeline transitions through these states for each conversation turn:

```
LISTENING ──── (user speaks) ────> PROCESSING
    ^                                   |
    |                          (agent generates)
    |                                   |
    |                            SPEAKING
    |                                   |
    +──── (bot finishes) ───────────────+
    |
    +──── (user speaks during SPEAKING) ──> INTERRUPTED ──> LISTENING
```

| State | Transcriber | Agent | Synthesizer |
|-------|-------------|-------|-------------|
| LISTENING | Active, unmuted | Idle | Idle |
| PROCESSING | Active, unmuted | Generating | Idle |
| SPEAKING | Active, **muted** | Idle | Streaming audio |
| INTERRUPTED | Active, unmuted | Cancelling task | Stopping stream |

---

## Gemini Live API Native Barge-in

Gemini Live API handles Voice Activity Detection (VAD) natively. When the user speaks while Gemini is generating an audio response:
1. Gemini detects user voice automatically
2. Gemini stops generating the current turn
3. Gemini begins processing the new user input

**What this means for your pipeline:**
- You do NOT need to implement VAD yourself
- You DO still need to stop sending already-generated audio to the client
- You DO still need to mute the transcriber to prevent echo from any separate TTS playback
- The `InterruptibleEvent` pattern handles the client-side audio stop

---

## InterruptibleEvent Pattern

Every audio delivery event is wrapped in an `InterruptibleEvent`. When an interrupt occurs, the event is signaled and the audio loop stops mid-stream.

```python
# src/interrupt.py
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InterruptibleEvent:
    payload: Any
    is_interruptible: bool = True
    interruption_event: threading.Event = field(default_factory=threading.Event)
    interrupted: bool = False

    def interrupt(self) -> bool:
        """Signal this event to stop. Returns True if successfully interrupted."""
        if not self.is_interruptible:
            return False
        if not self.interrupted:
            self.interruption_event.set()
            self.interrupted = True
            return True
        return False

    def is_interrupted(self) -> bool:
        return self.interruption_event.is_set()
```

---

## broadcast_interrupt

The conversation orchestrator calls `broadcast_interrupt()` when a new transcription arrives while the bot is speaking.

```python
# src/conversation.py (interrupt section)
import asyncio
import queue
import structlog
from .interrupt import InterruptibleEvent

log = structlog.get_logger()


class StreamingConversation:
    def __init__(self, ...):
        ...
        self._interruptible_events: queue.Queue[InterruptibleEvent] = queue.Queue()
        self._is_human_speaking = True

    def broadcast_interrupt(self) -> bool:
        """
        Stop all in-flight audio events.
        Called when user speaks while bot is speaking.
        Returns True if any events were interrupted.
        """
        num_interrupted = 0
        while True:
            try:
                event = self._interruptible_events.get_nowait()
                if event.interrupt():
                    num_interrupted += 1
            except queue.Empty:
                break

        # Also cancel in-flight agent generation
        self._agent.cancel_current_task()

        if num_interrupted > 0:
            log.info("interrupt_broadcast", events_stopped=num_interrupted)

        return num_interrupted > 0
```

---

## Rate-Limited Audio Delivery with Interrupt Check

This is the critical function. Without rate limiting, all audio chunks are delivered instantly to the client, making interrupts impossible (the audio is already in the client's buffer).

```python
# src/conversation.py (audio delivery)
import asyncio
import time
import structlog
from .synthesizer_base import SynthesisResult
from .interrupt import InterruptibleEvent

log = structlog.get_logger()

# Gemini TTS output: 24kHz, 16-bit PCM, 4096 bytes per chunk
_SAMPLE_RATE = 24_000
_BYTES_PER_SAMPLE = 2
_CHUNK_SIZE = 4_096
_SECONDS_PER_CHUNK = _CHUNK_SIZE / _BYTES_PER_SAMPLE / _SAMPLE_RATE  # ~0.085s


async def send_speech_to_output(
    websocket,
    synthesis_result: SynthesisResult,
    stop_event: InterruptibleEvent,
    transcriber,
    agent,
) -> tuple[str, bool]:
    """
    Stream audio chunks to the client at real-time rate.
    Checks for interrupt between each chunk.
    Returns (message_sent, was_cut_off).
    """
    transcriber.mute()
    chunk_idx = 0
    message_sent = ""

    try:
        async for chunk_result in synthesis_result.chunk_generator:
            # Check for interrupt BEFORE sending chunk
            if stop_event.is_interrupted():
                seconds_spoken = chunk_idx * _SECONDS_PER_CHUNK
                message_sent = synthesis_result.get_message_up_to(seconds_spoken)
                log.info("audio_interrupted", chunk_idx=chunk_idx, seconds_spoken=f"{seconds_spoken:.2f}")
                return message_sent, True  # cut_off = True

            start_time = time.monotonic()

            # Send chunk to client
            await websocket.send_bytes(chunk_result.chunk)
            chunk_idx += 1

            if chunk_result.is_last_chunk:
                break

            # CRITICAL: Wait for chunk duration before sending next chunk.
            # This is what makes interrupts possible — only one chunk is
            # buffered on the client at a time.
            elapsed = time.monotonic() - start_time
            await asyncio.sleep(max(_SECONDS_PER_CHUNK - elapsed, 0))

        return synthesis_result.get_message_up_to(chunk_idx * _SECONDS_PER_CHUNK), False

    finally:
        transcriber.unmute()
```

---

## Wiring Interrupts in TranscriptionsWorker

The transcriptions worker detects when a new transcription arrives while the bot is speaking and triggers an interrupt.

```python
# src/workers/transcriptions_worker.py
import asyncio
import structlog
from .base import BaseWorker
from .transcriber_base import Transcription

log = structlog.get_logger()


class TranscriptionsWorker(BaseWorker):
    """
    Sits between the transcriber and agent.
    Detects interrupts and flags transcriptions accordingly.
    """

    def __init__(
        self,
        input_queue: asyncio.Queue,
        output_queue: asyncio.Queue,
        conversation,  # StreamingConversation reference for broadcast_interrupt
    ) -> None:
        super().__init__(input_queue=input_queue, output_queue=output_queue)
        self._conversation = conversation
        self._log = log.bind(worker="TranscriptionsWorker")

    async def process(self, transcription: Transcription) -> None:
        if not transcription.is_final:
            return  # Ignore partial transcriptions

        # Check if bot was speaking — if so, this is an interrupt
        if not self._conversation._is_human_speaking:
            interrupted = self._conversation.broadcast_interrupt()
            if interrupted:
                transcription.is_interrupt = True
                self._log.info("user_interrupted_bot", chars=len(transcription.message))

        await self.output_queue.put(transcription)
```

---

## Updating Agent History on Cutoff

When the bot is interrupted mid-sentence, the conversation history must be updated to reflect only what was actually spoken (not the full generated text).

```python
# In StreamingConversation._send_speech (after audio delivery):
if cut_off:
    # Update agent's conversation history with partial message
    self._agent.history.update_last_bot_on_cutoff(message_sent)
    self._log.info("history_updated_on_cutoff", partial_chars=len(message_sent))
```

---

## Error Recovery

### Gemini Live Session End (go_away) and Reconnect

Connections end (around 10 min; the server sends `go_away` first). Do NOT detect this by searching exception text (`"SESSION_EXPIRED" in str(exc)` is fragile and pulls exception text into control flow). Track the resumption handle and reconnect with it: `gemini-live-api.md` sections 4-5 (executed relay + reconnect sketch). In the worker, `_receive_loop` returns on `go_away` (see `worker-pipeline.md`); the orchestrator then closes the old session and calls `connect()` again (give it a `resume_handle` parameter that sets `SessionResumptionConfig(handle=...)`), with a bounded number of attempts and backoff. When attempts run out, send one client error frame (`LIVE_RECONNECT_LIMIT`) so the client switches to text input.

### Worker-Level Error Recovery

One failed item is logged and skipped; `MAX_CONSECUTIVE_FAILURES` in a row end the worker with `WorkerFailedError` and the session with an error state (`worker-pipeline.md` BaseWorker). Never loop forever logging the same provider failure while the user hears silence.

---

## Graceful Shutdown

```python
# src/conversation.py
async def terminate(self) -> None:
    """
    Shut down the pipeline in order: stop accepting input, drain queues, close connections.
    """
    self._log.info("conversation_terminating")

    # 1. Stop accepting new audio
    self._transcriber.terminate()

    # 2. Cancel any in-flight agent generation
    self._agent.cancel_current_task()

    # 3. Stop agent and synthesizer
    self._agent.terminate()
    self._synthesizer.terminate()

    # 4. Cancel output loop
    if self._output_task and not self._output_task.done():
        self._output_task.cancel()
        try:
            await self._output_task
        except asyncio.CancelledError:
            pass

    # 5. Allow brief drain (workers may have queued final items)
    await asyncio.sleep(0.2)

    self._log.info("conversation_terminated")
```

---

## Interrupt Checklist

Before shipping any voice engine, verify:

- [ ] `TranscriptionsWorker` detects and flags interrupts
- [ ] `broadcast_interrupt()` cancels both queued events and current agent task
- [ ] Audio chunks are rate-limited (`asyncio.sleep` between chunks)
- [ ] Interrupt is checked BEFORE each chunk is sent
- [ ] Transcriber is muted before bot speaks, unmuted after
- [ ] History is updated with partial message on cutoff
- [ ] Gemini Live session reconnects on timeout
- [ ] All workers terminate cleanly on disconnect

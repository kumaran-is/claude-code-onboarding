# Worker Pipeline — BaseWorker Pattern + Gemini Implementations

Async worker pipeline (optional voice extension): base classes, Gemini workers, FastAPI wiring. Executed: `GeminiTranscriberWorker` against a real `google-genai` 3.6.1 `AsyncSession` on a scripted websocket (interim + final transcripts across two turns, `go_away`). `ADKAgentWorker` session handling executed on google-adk 2.15.0 (DeprecationWarning as error; the old try/except pattern created 0 sessions because `get_session` returns `None`). Dependency boundary: google-adk 2.15.0 requires `google-genai>=2.34,<3`, so a service that includes the ADK worker resolves google-genai 2.x, not 3.6.1; the Live calls used here have the same signatures on 2.34 (signature-checked, not executed). The rest is illustrative wiring, not executed; `admit` = `streaming-protocols/reference/server-stream-lifecycle.md` §3, `make_genai_client` = `gemini-provider-setup.md`.

---

## Abstract Base Classes

### BaseWorker

```python
# src/workers/base.py
import asyncio
import structlog
from abc import ABC, abstractmethod
from typing import Any

log = structlog.get_logger()


class WorkerFailedError(Exception):
    """A worker hit MAX_CONSECUTIVE_FAILURES; the session must end with an error state."""


class BaseWorker(ABC):
    """
    Every voice pipeline component inherits from BaseWorker.
    Workers communicate exclusively via asyncio.Queue — no direct method calls.
    """

    def __init__(self, input_queue: asyncio.Queue, output_queue: asyncio.Queue) -> None:
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.active = False
        self._task: asyncio.Task | None = None
        self._log = log.bind(worker=self.__class__.__name__)

    def start(self) -> None:
        """Start the worker's processing loop as a background asyncio task."""
        self.active = True
        self._task = asyncio.create_task(self._run_loop())
        self._log.info("worker_started")

    MAX_CONSECUTIVE_FAILURES = 3

    async def _run_loop(self) -> None:
        """Main processing loop — runs until terminate() is called.

        One failed item is logged and skipped; N failures in a row end the worker with
        WorkerFailedError. The orchestrator watches worker tasks and turns that into ONE
        client error frame (fixed code, e.g. VOICE_UNAVAILABLE) so the client switches to
        text input. Never loop forever on a broken provider.
        """
        failures = 0
        while self.active:
            item = await self.input_queue.get()
            try:
                await self.process(item)
                failures = 0
            except asyncio.CancelledError:
                raise  # Never swallow CancelledError
            except Exception as exc:
                failures += 1
                self._log.error("worker_error", error_type=type(exc).__name__, consecutive=failures)
                if failures >= self.MAX_CONSECUTIVE_FAILURES:
                    raise WorkerFailedError(self.__class__.__name__) from exc

    @abstractmethod
    async def process(self, item: Any) -> None:
        """Process one item from the input queue. Override in subclasses."""
        raise NotImplementedError

    def terminate(self) -> None:
        """Stop the worker."""
        self.active = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._log.info("worker_terminated")
```

### BaseTranscriber

```python
# src/workers/transcriber_base.py
import asyncio
from abc import abstractmethod
from .base import BaseWorker


class Transcription:
    def __init__(
        self,
        message: str,
        confidence: float = 1.0,
        is_final: bool = True,
        is_interrupt: bool = False,
    ) -> None:
        self.message = message
        self.confidence = confidence
        self.is_final = is_final
        self.is_interrupt = is_interrupt


class BaseTranscriber(BaseWorker):
    """
    Receives raw PCM audio chunks, produces Transcription objects.
    Supports mute/unmute to prevent echo during bot speech.
    """

    def __init__(self, output_queue: asyncio.Queue) -> None:
        # Transcriber's input queue receives audio bytes
        super().__init__(
            input_queue=asyncio.Queue(),
            output_queue=output_queue,
        )
        self.is_muted = False

    def send_audio(self, chunk: bytes) -> None:
        """Called by the WebSocket receiver with each incoming audio chunk."""
        if not self.is_muted:
            self.input_queue.put_nowait(chunk)
        else:
            # Send silence to keep Gemini Live session alive without echoing
            self.input_queue.put_nowait(self._silent_chunk(len(chunk)))

    def mute(self) -> None:
        """Mute transcriber when bot starts speaking — prevents echo feedback."""
        self.is_muted = True
        self._log.debug("transcriber_muted")

    def unmute(self) -> None:
        """Unmute transcriber when bot finishes speaking."""
        self.is_muted = False
        self._log.debug("transcriber_unmuted")

    @staticmethod
    def _silent_chunk(size: int) -> bytes:
        return b"\x00" * size

    @abstractmethod
    async def process(self, chunk: bytes) -> None:
        raise NotImplementedError
```

### BaseAgent

```python
# src/workers/agent_base.py
import asyncio
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator
from .base import BaseWorker
from .transcriber_base import Transcription


@dataclass
class AgentResponse:
    text: str
    is_final: bool = True
    conversation_id: str = ""


@dataclass
class ConversationHistory:
    messages: list[dict] = field(default_factory=list)

    def add_human(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_bot(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def update_last_bot_on_cutoff(self, partial_text: str) -> None:
        """Called when bot is interrupted — update history with what was actually spoken."""
        for msg in reversed(self.messages):
            if msg["role"] == "assistant":
                msg["content"] = partial_text
                return


class BaseAgent(BaseWorker):
    """
    Receives Transcription objects, produces AgentResponse objects.
    Maintains conversation history across turns.
    """

    def __init__(self, input_queue: asyncio.Queue, output_queue: asyncio.Queue) -> None:
        super().__init__(input_queue=input_queue, output_queue=output_queue)
        self.history = ConversationHistory()
        self._current_task: asyncio.Task | None = None

    def cancel_current_task(self) -> None:
        """Cancel in-flight generation on interrupt."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self._log.info("agent_task_cancelled")

    async def process(self, transcription: Transcription) -> None:
        self.cancel_current_task()
        self.history.add_human(transcription.message)
        self._current_task = asyncio.create_task(
            self._generate_and_enqueue(transcription), name="agent-generation"
        )
        # the task is held on self (strong reference); its failure must not vanish unobserved
        self._current_task.add_done_callback(self._on_generation_done)

    def _on_generation_done(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            self._log.error("agent_generation_task_failed", error_type=type(task.exception()).__name__)

    async def _generate_and_enqueue(self, transcription: Transcription) -> None:
        try:
            full_response = ""
            async for chunk in self.generate_response(
                transcription.message,
                is_interrupt=transcription.is_interrupt,
            ):
                full_response += chunk
            # Buffer entire response before enqueuing — prevents audio jumping
            response = AgentResponse(text=full_response, conversation_id="")
            self.history.add_bot(full_response)
            await self.output_queue.put(response)
        except asyncio.CancelledError:
            self._log.info("agent_generation_cancelled")
            raise  # barge-in cancels this task; never swallow CancelledError

    @abstractmethod
    async def generate_response(
        self, human_input: str, is_interrupt: bool = False
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError
```

### BaseSynthesizer

```python
# src/workers/synthesizer_base.py
import asyncio
from abc import abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, Callable
from .base import BaseWorker
from .agent_base import AgentResponse


@dataclass
class ChunkResult:
    chunk: bytes
    is_last_chunk: bool


@dataclass
class SynthesisResult:
    chunk_generator: AsyncGenerator[ChunkResult, None]
    get_message_up_to: Callable[[float], str]  # seconds → partial text spoken so far


class BaseSynthesizer(BaseWorker):
    """
    Receives AgentResponse objects, produces SynthesisResult for the output device.
    """

    def __init__(self, input_queue: asyncio.Queue, output_queue: asyncio.Queue) -> None:
        super().__init__(input_queue=input_queue, output_queue=output_queue)

    async def process(self, response: AgentResponse) -> None:
        try:
            result = await self.create_speech(response)
            await self.output_queue.put(result)
        except Exception as exc:
            self._log.error("synthesizer_failed", error_type=type(exc).__name__)
            raise

    @abstractmethod
    async def create_speech(self, response: AgentResponse) -> SynthesisResult:
        raise NotImplementedError
```

---

## Concrete Gemini Implementations and FastAPI Wiring

Moved to `worker-pipeline-gemini.md`: `GeminiTranscriberWorker`, `GeminiSynthesizerWorker`, `LangGraphAgentWorker`, `ADKAgentWorker`, and the FastAPI WebSocket server that wires them.

---

## StreamingConversation Orchestrator

```python
# src/conversation.py
import asyncio
import time
import structlog
from fastapi import WebSocket

from .workers.transcriber_base import BaseTranscriber
from .workers.agent_base import BaseAgent
from .workers.synthesizer_base import BaseSynthesizer, SynthesisResult

log = structlog.get_logger()

# Audio chunk timing: 24kHz, 16-bit, 4096 bytes per chunk
_SECONDS_PER_CHUNK = 4096 / 2 / 24_000  # ~0.085 seconds


class StreamingConversation:
    def __init__(
        self,
        websocket: WebSocket,
        transcriber: BaseTranscriber,
        agent: BaseAgent,
        synthesizer: BaseSynthesizer,
        synthesis_queue: asyncio.Queue,
    ) -> None:
        self._ws = websocket
        self._transcriber = transcriber
        self._agent = agent
        self._synthesizer = synthesizer
        self._synthesis_queue = synthesis_queue
        self._is_human_speaking = True
        self._output_task: asyncio.Task | None = None
        self._log = log.bind(component="StreamingConversation")

    async def start(self) -> None:
        """Connect transcriber and start all workers."""
        await self._transcriber.connect()
        self._transcriber.start()
        self._agent.start()
        self._synthesizer.start()
        self._output_task = asyncio.create_task(self._output_loop())
        self._log.info("conversation_started")

    def receive_audio(self, chunk: bytes) -> None:
        """Called by WebSocket receiver for each incoming audio chunk."""
        self._transcriber.send_audio(chunk)

    async def _output_loop(self) -> None:
        """Consume SynthesisResult from queue and send audio to client."""
        while True:
            try:
                result: SynthesisResult = await self._synthesis_queue.get()
                await self._send_speech(result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log.error("output_loop_error", error_type=type(exc).__name__)
                await self._ws.send_text('{"type":"error","code":"VOICE_UNAVAILABLE"}')  # client → text input
                raise

    async def _send_speech(self, result: SynthesisResult) -> None:
        """Rate-limited audio delivery with interrupt check. See interrupt-handling.md."""
        self._transcriber.mute()
        self._is_human_speaking = False
        chunk_idx = 0

        try:
            async for chunk_result in result.chunk_generator:
                start_time = time.monotonic()

                # Send audio chunk to client
                await self._ws.send_bytes(chunk_result.chunk)
                chunk_idx += 1

                if chunk_result.is_last_chunk:
                    break

                # Rate-limit: wait for chunk duration before sending next
                elapsed = time.monotonic() - start_time
                await asyncio.sleep(max(_SECONDS_PER_CHUNK - elapsed, 0))
        finally:
            self._is_human_speaking = True
            self._transcriber.unmute()

    async def terminate(self) -> None:
        """Gracefully shut down all workers."""
        if self._output_task and not self._output_task.done():
            self._output_task.cancel()
        self._transcriber.terminate()
        self._agent.terminate()
        self._synthesizer.terminate()
        await asyncio.sleep(0.2)  # Allow queues to drain
        self._log.info("conversation_terminated")
```

---

## Provider Selection

The wiring above (`src/main.py`) constructs each worker from settings. A `VoiceComponentFactory` was removed here: it duplicated that wiring for one provider per role. Add a factory only when 3+ interchangeable providers exist (`.claude/rules/core-behaviors.md` §4); provider trade-offs: `provider-comparison.md`.

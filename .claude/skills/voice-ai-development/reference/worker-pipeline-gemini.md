# Worker Pipeline — Gemini Implementations + FastAPI Wiring

Concrete workers for the base classes in `worker-pipeline.md` (BaseWorker, BaseTranscriber, BaseAgent, BaseSynthesizer) and the FastAPI WebSocket server that wires them. Execution evidence and the dependency boundary (google-adk 2.15.0 requires `google-genai>=2.34,<3`) are stated in the header of `worker-pipeline.md`; `StreamingConversation` and provider selection stay there.

---

## Concrete Gemini Implementations

### GeminiTranscriberWorker

```python
# src/workers/gemini_transcriber.py
import asyncio
import contextlib
import structlog
from google import genai
from google.genai import live, types
from .transcriber_base import BaseTranscriber, Transcription

log = structlog.get_logger()


class GeminiTranscriberWorker(BaseTranscriber):
    """
    Streams raw PCM audio to a Gemini Live session and emits the INPUT transcription
    (what the user said) as Transcription objects. Model id comes from settings.
    API shapes: gemini-live-api.md (verified against google-genai 3.6.1).
    """

    def __init__(self, output_queue: asyncio.Queue, client: genai.Client, *, model: str) -> None:
        super().__init__(output_queue=output_queue)
        self._client = client
        self._model = model
        self._stack = contextlib.AsyncExitStack()
        self._session: live.AsyncSession | None = None
        self._receiver_task: asyncio.Task | None = None
        self._log = log.bind(worker="GeminiTranscriberWorker")

    async def connect(self) -> None:
        """Open the Live session (an async context manager). Call before start()."""
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            input_audio_transcription=types.AudioTranscriptionConfig(),
        )
        self._session = await self._stack.enter_async_context(
            self._client.aio.live.connect(model=self._model, config=config)
        )
        self._log.info("gemini_live_connected", model=self._model)
        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        assert self._session is not None
        try:
            while True:  # receive() yields ONE model turn, then stops
                async for msg in self._session.receive():
                    content = msg.server_content
                    heard = content.input_transcription if content else None
                    if heard and heard.text and heard.text.strip():
                        await self.output_queue.put(
                            Transcription(message=heard.text.strip(), is_final=bool(heard.finished))
                        )
                        self._log.info("transcribed", chars=len(heard.text), final=bool(heard.finished))
                    if msg.go_away is not None:
                        self._log.warning("gemini_live_go_away")   # orchestrator reconnects
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log.error("receiver_loop_failed", error_type=type(exc).__name__)
            raise

    async def process(self, chunk: bytes) -> None:
        """Send one audio chunk (keyword-only, one field per call)."""
        if self._session is None:
            self._log.error("gemini_live_not_connected")
            raise RuntimeError("GeminiTranscriberWorker: session not connected. Call connect() first.")
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )
        except Exception as exc:
            self._log.error("send_audio_failed", error_type=type(exc).__name__, audio_bytes=len(chunk))
            raise

    async def close(self) -> None:
        self.terminate()
        if self._receiver_task and not self._receiver_task.done():
            self._receiver_task.cancel()
        await self._stack.aclose()   # closes the Live session
```

Only `is_final=True` transcriptions may drive the agent; interim ones are display-only and replaced by the next.

### GeminiSynthesizerWorker

```python
# src/workers/gemini_synthesizer.py
import asyncio
import structlog
from google import genai
from google.genai import types
from .synthesizer_base import BaseSynthesizer, SynthesisResult, ChunkResult
from .agent_base import AgentResponse

log = structlog.get_logger()

# Gemini TTS output: 24kHz mono 16-bit PCM
_SAMPLE_RATE = 24_000
_BYTES_PER_SAMPLE = 2
_CHUNK_SIZE = 4_096  # bytes per chunk for streaming
_SECONDS_PER_CHUNK = _CHUNK_SIZE / _BYTES_PER_SAMPLE / _SAMPLE_RATE  # ~0.085s


class GeminiSynthesizerWorker(BaseSynthesizer):
    """
    Converts agent text responses to speech using Gemini TTS.
    Streams PCM audio chunks to the output device queue.
    """

    def __init__(
        self,
        input_queue: asyncio.Queue,
        output_queue: asyncio.Queue,
        client: genai.Client,
        *,
        model: str,   # settings.TTS_MODEL_FAST — never a literal
        voice: str,   # settings.LIVE_VOICE / TTS voice from the configured allowlist
    ) -> None:
        super().__init__(input_queue=input_queue, output_queue=output_queue)
        self._client = client
        self._model = model
        self._voice = voice
        self._log = log.bind(worker="GeminiSynthesizerWorker")

    async def create_speech(self, response: AgentResponse) -> SynthesisResult:
        """Synthesize text to PCM audio and return a SynthesisResult."""
        text = response.text
        self._log.info("synthesizing", chars=len(text), model=self._model, voice=self._voice)

        try:
            api_response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=self._voice
                            )
                        )
                    ),
                ),
            )
        except Exception as exc:
            self._log.error("tts_api_failed", text_chars=len(text), error_type=type(exc).__name__)
            raise

        candidate = api_response.candidates[0] if api_response.candidates else None
        parts = candidate.content.parts if candidate and candidate.content else None
        if not parts or not parts[0].inline_data or not parts[0].inline_data.data:
            self._log.error("tts_no_audio", text_chars=len(text))   # blocked or empty: an error, not silence
            raise RuntimeError("TTS returned no audio")
        audio_bytes: bytes = parts[0].inline_data.data
        self._log.info("tts_synthesized", bytes=len(audio_bytes))

        # Build message-up-to function for interrupt handling
        chars_per_second = len(text) / max(len(audio_bytes) / _BYTES_PER_SAMPLE / _SAMPLE_RATE, 0.001)

        def get_message_up_to(seconds: float) -> str:
            char_count = int(seconds * chars_per_second)
            return text[:char_count]

        async def chunk_generator():
            for i in range(0, len(audio_bytes), _CHUNK_SIZE):
                chunk = audio_bytes[i : i + _CHUNK_SIZE]
                is_last = (i + _CHUNK_SIZE) >= len(audio_bytes)
                yield ChunkResult(chunk=chunk, is_last_chunk=is_last)

        return SynthesisResult(
            chunk_generator=chunk_generator(),
            get_message_up_to=get_message_up_to,
        )
```

### LangGraphAgentWorker

```python
# src/workers/langgraph_agent.py
import asyncio
import structlog
from typing import AsyncGenerator, Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from .agent_base import BaseAgent

log = structlog.get_logger()


class VoiceAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    iteration_count: int  # Iron Law: always track iterations


def build_voice_graph(llm) -> StateGraph:
    """Build a minimal LangGraph StateGraph for voice agent."""

    async def agent_node(state: VoiceAgentState):
        if state["iteration_count"] >= 10:  # Iron Law: iteration limit
            return {"messages": [AIMessage(content="I need to stop here.")], "iteration_count": state["iteration_count"] + 1}
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response], "iteration_count": state["iteration_count"] + 1}

    def should_continue(state: VoiceAgentState):
        return END  # For voice: always stop after one agent turn

    graph = StateGraph(VoiceAgentState)
    graph.add_node("agent", agent_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    return graph.compile()


class LangGraphAgentWorker(BaseAgent):
    """
    Voice agent using LangGraph StateGraph.
    Maintains conversation history across turns.
    Uses ChatGoogleGenerativeAI (Gemini) as the LLM.
    """

    def __init__(
        self,
        input_queue: asyncio.Queue,
        output_queue: asyncio.Queue,
        system_prompt: str = "You are a helpful voice assistant. Keep responses concise and conversational.",
        *,
        gemini_model: str,                  # settings value — never a literal
        google_api_key: str | None = None,  # local dev only; deployed envs are keyless
    ) -> None:
        super().__init__(input_queue=input_queue, output_queue=output_queue)
        self._system_prompt = system_prompt
        llm = ChatGoogleGenerativeAI(
            model=gemini_model,
            google_api_key=google_api_key,
            streaming=True,
        )
        self._graph = build_voice_graph(llm)
        self._log = log.bind(worker="LangGraphAgentWorker")

    async def generate_response(
        self, human_input: str, is_interrupt: bool = False
    ) -> AsyncGenerator[str, None]:
        """Generate response via LangGraph. Yields text chunks."""
        messages = []
        if not any(m.get("role") == "system" for m in self.history.messages):
            messages.append(SystemMessage(content=self._system_prompt))
        for msg in self.history.messages:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=human_input))

        state: VoiceAgentState = {"messages": messages, "iteration_count": 0}

        try:
            result = await self._graph.ainvoke(state)
            last_message = result["messages"][-1]
            response_text = last_message.content if hasattr(last_message, "content") else str(last_message)
            self._log.info("langgraph_response_generated", chars=len(response_text))
            yield response_text
        except Exception as exc:
            self._log.error("langgraph_generation_failed", error_type=type(exc).__name__)
            raise
```

### ADKAgentWorker

```python
# src/workers/adk_agent.py
import asyncio
import structlog
from typing import AsyncGenerator
from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types as genai_types
from .agent_base import BaseAgent

log = structlog.get_logger()


class ADKAgentWorker(BaseAgent):
    """
    Voice agent: one ADK LlmAgent behind a Runner (session-aware execution).
    No SequentialAgent wrapper: ADK 2.x deprecates it in favour of Workflow, and a
    single-agent pipeline needs neither (google-adk skill).
    """

    def __init__(
        self,
        input_queue: asyncio.Queue,
        output_queue: asyncio.Queue,
        app_name: str = "voice-agent",
        system_prompt: str = "You are a helpful voice assistant. Keep responses concise.",
        *,
        gemini_model: str,                  # settings value — never a literal
    ) -> None:
        super().__init__(input_queue=input_queue, output_queue=output_queue)
        self._app_name = app_name
        self._session_id = f"voice-session-{id(self)}"
        self._user_id = "voice-user"
        self._log = log.bind(worker="ADKAgentWorker")

        self._agent = LlmAgent(
            name="voice_llm_agent",
            model=gemini_model,
            instruction=system_prompt,
        )
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=self._agent,
            app_name=app_name,
            session_service=self._session_service,
        )

    async def _ensure_session(self) -> None:
        """Create the ADK session if it does not exist (get_session returns None; it does not raise)."""
        existing = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
        )
        if existing is None:
            await self._session_service.create_session(
                app_name=self._app_name,
                user_id=self._user_id,
                session_id=self._session_id,
            )

    async def generate_response(
        self, human_input: str, is_interrupt: bool = False
    ) -> AsyncGenerator[str, None]:
        """Generate a response via the ADK Runner. Yields the final text."""
        await self._ensure_session()

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=human_input)],
        )

        full_response = ""
        try:
            async for event in self._runner.run_async(
                user_id=self._user_id,
                session_id=self._session_id,
                new_message=content,
            ):
                if event.is_final_response() and event.content:
                    for part in event.content.parts:
                        if part.text:
                            full_response += part.text
            self._log.info("adk_response_generated", chars=len(full_response))
            yield full_response
        except Exception as exc:
            self._log.error("adk_generation_failed", error_type=type(exc).__name__)
            raise
```

---

## FastAPI WebSocket Server (Pipeline Wiring)

```python
# src/main.py
import asyncio
import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google import genai

from .config import VoiceEngineConfig
from .workers.gemini_transcriber import GeminiTranscriberWorker
from .workers.gemini_synthesizer import GeminiSynthesizerWorker
from .workers.langgraph_agent import LangGraphAgentWorker  # or ADKAgentWorker
from .conversation import StreamingConversation

log = structlog.get_logger()
config = VoiceEngineConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.gemini_client = make_genai_client(config)   # auth matrix: gemini-provider-setup.md
    log.info("voice_engine_started")
    yield
    # Shutdown
    log.info("voice_engine_stopped")


app = FastAPI(title="Voice AI Engine", lifespan=lifespan)


@app.websocket("/conversation")
async def conversation_endpoint(websocket: WebSocket) -> None:
    # Subprotocol + authentication + one-stream-per-actor BEFORE accept(); admit() closes
    # with 1008 and returns None on refusal. Pattern and tests:
    # streaming-protocols/reference/server-stream-lifecycle.md section 3.
    principal = await admit(websocket)
    if principal is None:
        return
    log.info("client_connected", attempt_id=principal.attempt_id)   # ids only, never IP or transcript

    # Bounded queues: a slow stage ends the session with BACKPRESSURE instead of growing memory
    transcription_queue: asyncio.Queue = asyncio.Queue(maxsize=32)
    agent_queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    synthesis_queue: asyncio.Queue = asyncio.Queue(maxsize=8)

    client: genai.Client = websocket.app.state.gemini_client

    # Instantiate workers
    transcriber = GeminiTranscriberWorker(
        output_queue=transcription_queue,
        client=client,
        model=config.LIVE_MODEL,
    )
    agent = LangGraphAgentWorker(
        input_queue=transcription_queue,
        output_queue=agent_queue,
        gemini_model=config.AGENT_MODEL,
    )
    synthesizer = GeminiSynthesizerWorker(
        input_queue=agent_queue,
        output_queue=synthesis_queue,
        client=client,
        model=config.TTS_MODEL_FAST,
        voice=config.LIVE_VOICE,
    )

    # Create conversation orchestrator
    conversation = StreamingConversation(
        websocket=websocket,
        transcriber=transcriber,
        agent=agent,
        synthesizer=synthesizer,
        synthesis_queue=synthesis_queue,
    )

    try:
        await conversation.start()

        # Enforce frame/byte/time/idle caps here (run_attempt in server-stream-lifecycle.md)
        async for message in websocket.iter_bytes():
            conversation.receive_audio(message)

    except WebSocketDisconnect:
        log.info("client_disconnected")
    except Exception as exc:
        log.error("conversation_error", error_type=type(exc).__name__)
        raise
    finally:
        await conversation.terminate()
        await transcriber.close()        # closes the Live session


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

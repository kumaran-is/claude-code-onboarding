# LangGraph + Gemini Voice Agent

> Framework: LangGraph v1.0.7 + LangChain v1.2.8 + FastAPI 0.135.2
> Optional voice extension. Model ids and voices come from settings (`LIVE_MODEL`, `AGENT_MODEL`, `TTS_MODEL_FAST`, `LIVE_VOICE`), never literals. Executed: `voice_input_node` and its test (section 8) against a real `google-genai` 3.6.1 `AsyncSession` on a scripted websocket. Other snippets: illustrative.
> Logging: stdlib `logging` with `error_type` only; in a service use `log_exception` (`deployment-ci-cd/reference/python-observability.md` §2). Never log transcripts, response text or audio.
> Python: 3.14 + asyncio

## Architecture

```
User audio (PCM) --> [voice_input_node] --> transcript
                                               |
                                    [llm_response_node]
                                               |
                                         response_text
                                               |
                                    [voice_output_node] --> audio bytes
```

State flows through a LangGraph `StateGraph`. Each node is independently testable.

---

## 1. State Definition

```python
from typing import TypedDict


class VoiceAgentState(TypedDict):
    """
    Shared state across all nodes in the voice agent graph.

    audio_input:   Raw PCM bytes from user microphone (16-bit, 16kHz, mono).
    transcript:    Text transcription of the user's speech.
    response_text: LLM-generated text response.
    audio_output:  Synthesized audio bytes (PCM) for playback.
    error:         Error message if any node failed; None on success.
    session_id:    Identifier for the conversation session (for logging/tracing).
    turn_count:    Number of conversation turns completed.
    """
    audio_input: bytes
    transcript: str
    response_text: str
    audio_output: bytes
    error: str | None
    session_id: str
    turn_count: int
```

---

## 2. Voice Input Node — Transcription via Live API

```python
import asyncio
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)
client = genai.Client()


async def voice_input_node(state: VoiceAgentState) -> VoiceAgentState:
    """
    Transcribe one recorded user turn with Live API INPUT transcription.

    `input_audio_transcription` returns what the user said. Asking the model to
    "transcribe" in TEXT mode returns the model's reply, not a transcript.
    """
    audio_input = state.get("audio_input", b"")
    session_id = state.get("session_id", "unknown")

    if not audio_input:
        logger.error(
            "voice_input_node: audio_input is empty",
            extra={"session_id": session_id},
        )
        raise ValueError("audio_input must not be empty")

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.TEXT],
        input_audio_transcription=types.AudioTranscriptionConfig(),  # what the USER said
    )

    transcript_parts: list[str] = []

    try:
        async with client.aio.live.connect(model=settings.LIVE_MODEL, config=config) as session:
            await session.send_realtime_input(
                audio=types.Blob(data=audio_input, mime_type="audio/pcm;rate=16000")
            )
            await session.send_realtime_input(audio_stream_end=True)

            async for msg in session.receive():  # one turn; ends on turn_complete
                content = msg.server_content
                if content and content.input_transcription and content.input_transcription.text:
                    transcript_parts.append(content.input_transcription.text)

    except Exception as exc:
        logger.error(
            "voice_input_node: Live API transcription failed",
            extra={"error_type": type(exc).__name__, "session_id": session_id},
        )
        raise

    transcript = "".join(transcript_parts).strip()
    if not transcript:
        logger.warning(
            "voice_input_node: empty transcript received",
            extra={"session_id": session_id, "audio_bytes": len(audio_input)},
        )

    logger.info(
        "voice_input_node: transcription complete",
        extra={"session_id": session_id, "transcript_length": len(transcript)},
    )

    return {
        **state,
        "transcript": transcript,
        "error": None,
    }
```

---

## 3. LLM Response Node — Agent Logic

```python
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


def build_llm(model: str) -> ChatGoogleGenerativeAI:   # model = settings.AGENT_MODEL
    """Build LangChain LLM wrapper for Gemini."""
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0.7,
        max_output_tokens=512,
    )


_llm = build_llm()

SYSTEM_PROMPT = (
    "You are a helpful voice assistant. "
    "Respond concisely — your answer will be spoken aloud. "
    "Avoid lists, markdown, or formatting. Plain natural speech only."
)


async def llm_response_node(state: VoiceAgentState) -> VoiceAgentState:
    """
    Generate a text response from the transcript using LangChain + Gemini.
    """
    transcript = state.get("transcript", "")
    session_id = state.get("session_id", "unknown")

    if not transcript:
        logger.warning(
            "llm_response_node: empty transcript — using fallback response",
            extra={"session_id": session_id},
        )
        return {
            **state,
            "response_text": "I didn't catch that. Could you please repeat?",
            "error": None,
        }

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=transcript),
    ]

    logger.info(
        "llm_response_node: generating response",
        extra={"session_id": session_id, "transcript_length": len(transcript)},
    )

    try:
        response = await _llm.ainvoke(messages)
        response_text = response.content.strip()
    except Exception as exc:
        logger.error(
            "llm_response_node: LLM invocation failed",
            extra={"error_type": type(exc).__name__, "session_id": session_id},
        )
        raise

    logger.info(
        "llm_response_node: response generated",
        extra={"session_id": session_id, "response_length": len(response_text)},
    )

    return {
        **state,
        "response_text": response_text,
        "turn_count": state.get("turn_count", 0) + 1,
        "error": None,
    }
```

---

## 4. Voice Output Node — TTS Synthesis

```python
import asyncio
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)
client = genai.Client()


async def voice_output_node(state: VoiceAgentState) -> VoiceAgentState:
    """
    Synthesize response_text to audio using Gemini TTS.

    Uses settings.TTS_MODEL_FAST for real-time response speed
    (settings.TTS_MODEL_QUALITY for higher fidelity).
    """
    response_text = state.get("response_text", "")
    session_id = state.get("session_id", "unknown")

    if not response_text:
        logger.error(
            "voice_output_node: response_text is empty",
            extra={"session_id": session_id},
        )
        raise ValueError("response_text must not be empty before voice synthesis")

    logger.info(
        "voice_output_node: synthesizing audio",
        extra={"session_id": session_id, "text_length": len(response_text)},
    )

    audio_chunks: list[bytes] = []

    try:
        # Run blocking TTS in executor to avoid blocking the event loop
        def _synthesize() -> bytes:
            _client = genai.Client()
            response = _client.models.generate_content(
                model=settings.TTS_MODEL_FAST,
                contents=response_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=settings.LIVE_VOICE
                            )
                        )
                    ),
                ),
            )
            data = response.candidates[0].content.parts[0].inline_data.data
            if not data:
                raise RuntimeError("TTS returned empty audio — content may be blocked")
            return data

        audio_bytes = await asyncio.get_event_loop().run_in_executor(None, _synthesize)

    except Exception as exc:
        logger.error(
            "voice_output_node: TTS synthesis failed",
            extra={"error_type": type(exc).__name__, "session_id": session_id},
        )
        raise

    logger.info(
        "voice_output_node: synthesis complete",
        extra={"session_id": session_id, "audio_bytes": len(audio_bytes)},
    )

    return {
        **state,
        "audio_output": audio_bytes,
        "error": None,
    }
```

---

## 5. Graph Assembly

```python
import logging
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


def build_voice_agent_graph():
    """
    Assemble the voice agent StateGraph.

    Flow: voice_input -> llm_response -> voice_output -> END
    """
    graph = StateGraph(VoiceAgentState)

    graph.add_node("voice_input", voice_input_node)
    graph.add_node("llm_response", llm_response_node)
    graph.add_node("voice_output", voice_output_node)

    graph.set_entry_point("voice_input")
    graph.add_edge("voice_input", "llm_response")
    graph.add_edge("llm_response", "voice_output")
    graph.add_edge("voice_output", END)

    compiled = graph.compile()
    logger.info("Voice agent graph compiled: voice_input -> llm_response -> voice_output -> END")
    return compiled


# Module-level compiled graph — one instance per service
voice_agent = build_voice_agent_graph()
```

---

## 6. FastAPI Streaming Endpoint — End-to-End

```python
import asyncio
import contextlib
import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .ws_admission import admit   # streaming-protocols/reference/server-stream-lifecycle.md §3

logger = logging.getLogger(__name__)
MAX_TURN_BYTES = 960_000          # ~30 s of 16 kHz PCM16 per turn


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Voice agent API starting — graph compiled")
    yield
    logger.info("Voice agent API shutting down")


app = FastAPI(lifespan=lifespan)


class VoiceTurnRequest(BaseModel):
    """For HTTP turn-based voice (non-streaming)."""
    audio_base64: str  # Base64-encoded PCM bytes
    session_id: str = ""


@app.post("/voice/turn")
async def voice_turn(request: VoiceTurnRequest) -> dict:
    """
    Single-turn voice interaction: audio in -> audio out.

    Accepts base64-encoded PCM bytes, returns base64-encoded PCM response.
    For real-time streaming, use the WebSocket endpoint instead.
    """
    import base64

    session_id = request.session_id or str(uuid.uuid4())

    try:
        audio_bytes = base64.b64decode(request.audio_base64)
    except Exception as exc:
        logger.warning("Invalid base64 audio input", extra={"error_type": type(exc).__name__, "session_id": session_id})
        raise HTTPException(status_code=422, detail="audio_base64 must be valid base64-encoded PCM bytes")

    if not audio_bytes:
        raise HTTPException(status_code=422, detail="audio_base64 decoded to empty bytes")

    initial_state: VoiceAgentState = {
        "audio_input": audio_bytes,
        "transcript": "",
        "response_text": "",
        "audio_output": b"",
        "error": None,
        "session_id": session_id,
        "turn_count": 0,
    }

    try:
        result = await voice_agent.ainvoke(initial_state)
    except Exception as exc:
        logger.error("Voice agent turn failed", extra={"error_type": type(exc).__name__, "session_id": session_id})
        raise HTTPException(status_code=502, detail="Voice agent processing failed")

    if result.get("error"):
        logger.error(
            "Voice agent returned error state",
            extra={"session_id": session_id, "error": result["error"]},
        )
        raise HTTPException(status_code=502, detail=result["error"])

    return {
        "session_id": session_id,
        "transcript": result["transcript"],
        "response_text": result["response_text"],
        "audio_output_base64": base64.b64encode(result["audio_output"]).decode(),
        "turn_count": result["turn_count"],
    }


@app.websocket("/ws/voice/stream")
async def websocket_voice_stream(websocket: WebSocket) -> None:
    """
    WebSocket streaming voice: client sends PCM chunks, receives PCM response.

    Protocol:
      Client -> Server: binary frames = raw PCM (16-bit, 16kHz, mono)
      Client -> Server: text frame {"type":"end_turn"} (control never shares the audio channel)
      Server -> Client: binary frames = response PCM; text frames = JSON events
    Admission (subprotocol + auth BEFORE accept, one stream per actor) and the
    frame/byte/time/idle caps: streaming-protocols/reference/server-stream-lifecycle.md §3.
    """
    principal = await admit(websocket)   # closes 1008 and returns None on refusal
    if principal is None:
        return
    session_id = str(uuid.uuid4())
    logger.info("WebSocket voice stream opened", extra={"session_id": session_id})

    audio_chunks: list[bytes] = []

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                logger.info("WebSocket disconnected", extra={"session_id": session_id})
                break
            if (data := msg.get("bytes")) is not None:
                if sum(map(len, audio_chunks)) + len(data) > MAX_TURN_BYTES:
                    await websocket.send_text('{"type":"error","code":"LIMIT_EXCEEDED"}')
                    await websocket.close(code=1009)
                    break
                audio_chunks.append(data)
                continue

            if json.loads(msg.get("text") or "{}").get("type") == "end_turn":
                if not audio_chunks:
                    await websocket.send_text('{"type":"error","code":"AUDIO_EMPTY"}')
                    continue

                combined_audio = b"".join(audio_chunks)
                audio_chunks.clear()

                initial_state: VoiceAgentState = {
                    "audio_input": combined_audio,
                    "transcript": "",
                    "response_text": "",
                    "audio_output": b"",
                    "error": None,
                    "session_id": session_id,
                    "turn_count": 0,
                }

                try:
                    result = await voice_agent.ainvoke(initial_state)
                except Exception as exc:
                    logger.error(
                        "Voice agent processing failed",
                        extra={"error_type": type(exc).__name__, "session_id": session_id},
                    )
                    await websocket.send_text('{"type":"error","code":"VOICE_UNAVAILABLE"}')  # client → text input
                    continue

                if result.get("audio_output"):
                    await websocket.send_bytes(result["audio_output"])
                await websocket.send_text('{"type":"turn_complete"}')

    except Exception as exc:
        logger.error(
            "WebSocket voice stream error",
            extra={"error_type": type(exc).__name__, "session_id": session_id},
        )
        with contextlib.suppress(RuntimeError):   # socket may already be closed
            await websocket.close(code=1011)
        raise
```

---

## 7. End-to-End Example Flow

```
1. User presses microphone button in browser
2. Browser captures PCM audio, sends bytes via WebSocket to /ws/voice/stream
3. User releases button -> browser sends text frame {"type":"end_turn"}
4. voice_input_node: PCM bytes -> Gemini Live API -> transcript text
5. llm_response_node: transcript -> LangChain + Gemini -> response text
6. voice_output_node: response text -> Gemini TTS -> PCM audio bytes
7. FastAPI sends audio bytes back over WebSocket
8. Browser receives PCM, decodes, plays through Web Audio API
9. User hears the assistant's response
10. Cycle repeats for next turn
```

---

## 8. Testing the Graph

Executed (pytest-asyncio, `google-genai` 3.6.1): a REAL `AsyncSession` on a scripted websocket. Patch the module's client object, not `google.genai.Client` (the module-level client already exists when the test runs), and never mock `receive` as an `AsyncMock` (it returns a coroutine, not an async iterator).

```python
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import pytest
from google.genai import live

import voice_nodes                      # module holding `client` and voice_input_node
from tests.fakes import FakeWS          # recv() pops scripted server JSON; send() records client JSON


async def test_voice_input_node_transcribes(monkeypatch: pytest.MonkeyPatch) -> None:
    ws = FakeWS([
        {"serverContent": {"inputTranscription": {"text": "Hello, "}}},
        {"serverContent": {"inputTranscription": {"text": "how are you?", "finished": True}}},
        {"serverContent": {"turnComplete": True}},
    ])

    @contextlib.asynccontextmanager
    async def fake_connect(*, model: str, config: Any) -> AsyncIterator[live.AsyncSession]:
        assert config.input_audio_transcription is not None
        yield live.AsyncSession(api_client=voice_nodes.client._api_client, websocket=ws)

    monkeypatch.setattr(voice_nodes.client.aio.live, "connect", fake_connect)
    state = {"audio_input": b"\x00\x01" * 1000, "transcript": "", "response_text": "",
             "audio_output": b"", "error": None, "session_id": "s1", "turn_count": 0}
    result = await voice_nodes.voice_input_node(state)
    assert result["transcript"] == "Hello, how are you?"
    assert [list(m["realtime_input"]) for m in ws.sent] == [["audio"], ["audioStreamEnd"]]


async def test_empty_audio_rejected() -> None:
    state = {"audio_input": b"", "transcript": "", "response_text": "", "audio_output": b"",
             "error": None, "session_id": "s1", "turn_count": 0}
    with pytest.raises(ValueError):
        await voice_nodes.voice_input_node(state)
```

`FakeWS`: `recv(decode=False)` returns `json.dumps(next_message).encode()`; `send(raw)` appends `json.loads(raw)`. Result: 2 passed. This is a scripted fake, not proof of live-provider behaviour.

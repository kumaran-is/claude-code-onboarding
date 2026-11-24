# Voice AI Engine Development Workflow

Build a production-ready real-time conversational voice AI engine using Gemini Live API (STT), Gemini TTS (synthesis), and a LangGraph or ADK agent — all wired together via an async worker pipeline with full interrupt support.

**Skill:** `.claude/skills/voice-ai-development/SKILL.md` (optional voice extension; references under `.claude/skills/voice-ai-development/reference/`)

**Iron Law:** Every component runs in its own `asyncio.Queue`-based worker. No direct method calls between workers. Interrupt handling is wired before any other feature.

---

## Phase 1: Setup

**Goal:** Working Python project with all dependencies installed.

Pick ONE agent option before installing: google-adk 2.15.0 requires `google-genai>=2.34,<3` and `websockets>=15.0.1,<16`, so the ADK and LangGraph sets below cannot share one project. Both sets locked on Python 3.14.10 with uv 0.13.9 (2026-11-23); exact pins, lockfile, `uv sync --locked` in CI.

```bash
uv init voice-engine --python 3.14 && cd voice-engine
COMMON='fastapi==0.165.0 uvicorn[standard]==0.54.0 pydantic==2.14.4 pydantic-settings==2.16.3 structlog==26.1.0 numpy==2.5.5 aiolimiter==1.3.0'

# Option A: LangGraph agent
uv add $COMMON google-genai==3.6.1 websockets==17.4 langgraph==1.2.24 langchain-core==1.8.4
# Option B: ADK agent (resolves google-genai 2.34.0)
uv add $COMMON google-adk==2.15.0 websockets==15.0.1

uv add --dev pytest==9.2.0 pytest-asyncio==1.5.0 httpx==0.28.1 ruff==0.17.6 mypy==2.4.1
# MP3 export: ffmpeg binary in the image. Not pydub: it imports audioop, removed in Python 3.13.
```

**Create `.env`:**
```bash
# local only, never committed; pick model ids and voices from the provider's models page and voice list
GEMINI_API_KEY=
LIVE_MODEL=
LIVE_VOICE=
TTS_MODEL_FAST=
TTS_MODEL_QUALITY=
TTS_ALLOWED_VOICES=["<voice-a>","<voice-b>"]
```

**Create `src/config.py`** — pydantic-settings, load from `.env`, fail fast on missing vars.

**Verification gate:** `uv sync --locked` exits 0 and `src/config.py` fails fast when `LIVE_MODEL` is missing (test it).

**Common mistake:** Installing `google-generativeai` instead of `google-genai`. See `reference/common-pitfalls.md` §1.

---

## Phase 2: BaseWorker Pattern

**Goal:** Abstract `BaseWorker`, `BaseTranscriber`, `BaseAgent`, `BaseSynthesizer` classes.

**Files to create:**
- `src/workers/base.py` — `BaseWorker` with `asyncio.Queue`, `start()`, `_run_loop()`, `terminate()`
- `src/workers/transcriber_base.py` — adds `send_audio()`, `mute()`, `unmute()`
- `src/workers/agent_base.py` — adds `ConversationHistory`, `cancel_current_task()`
- `src/workers/synthesizer_base.py` — adds `SynthesisResult`, `ChunkResult`

**Reference:** `reference/worker-pipeline.md` § Abstract Base Classes

**Unit test:** Subclass `BaseWorker` with a mock `process()` method. Verify `start()` creates a task, items flow from input to output queue, `terminate()` stops the loop cleanly.

**Verification gate:** Tests pass. `BaseWorker` is never instantiated directly.

---

## Phase 3: Gemini STT Worker

**Goal:** `GeminiTranscriberWorker` that streams PCM audio to Gemini Live API and produces `Transcription` objects.

**File:** `src/workers/gemini_transcriber.py`

**Key decisions:**
- Model: from settings (`LIVE_MODEL`), never hard-coded — see `gemini-live-api.md` §1
- Protocol: WebSocket (`client.aio.live.connect()`) — never HTTP polling
- Audio MIME type: `audio/pcm;rate=16000`
- Concurrent sender + receiver tasks via `asyncio.create_task()`
- Reconnect on session timeout (see `reference/gemini-provider-setup.md` § Session limits and reconnect, `reference/gemini-live-api.md` §5)

**Reference:** `reference/worker-pipeline-gemini.md` § GeminiTranscriberWorker, `reference/gemini-live-api.md` §2–§3

**Unit test:** Mock the Gemini Live session. Send a fake audio chunk. Verify a `Transcription` appears in the output queue.

**Verification gate:** Worker connects to Gemini Live, sends audio, receives transcription. Mute/unmute flips correctly.

---

## Phase 4: Gemini TTS Worker

**Goal:** `GeminiSynthesizerWorker` that converts agent text to PCM audio chunks.

**File:** `src/workers/gemini_synthesizer.py`

**Key decisions:**
- Model: from settings (`TTS_MODEL_FAST` default, `TTS_MODEL_QUALITY` for high fidelity) — never hard-coded
- Voice: from settings, validated against `TTS_ALLOWED_VOICES` — see `reference/gemini-tts.md` and the provider's voice list
- Output: 24kHz mono 16-bit PCM, chunked at 4096 bytes (~85ms per chunk)
- `get_message_up_to(seconds)` function built from character-to-time mapping — required for interrupt partial message tracking

**Reference:** `reference/worker-pipeline-gemini.md` § GeminiSynthesizerWorker, `reference/gemini-tts.md` §2

**Unit test:** Mock `client.aio.models.generate_content`. Verify `SynthesisResult` contains a valid `chunk_generator` and `get_message_up_to`.

**Verification gate:** Worker synthesizes a known text string. Chunks are 4096 bytes each (except last). `get_message_up_to(0.5)` returns ~50% of the text.

---

## Phase 5: Agent Worker (LangGraph or ADK)

**Choose one based on your requirements:**

### Option A: LangGraphAgentWorker

**File:** `src/workers/langgraph_agent.py`

**Pattern:** `StateGraph` with a single `agent_node`. Always includes `iteration_count` in state (Iron Law from `agentic-ai-dev`). Full response buffered before enqueuing (prevents audio jumping).

**Reference:** `reference/worker-pipeline-gemini.md` § LangGraphAgentWorker

**Use when:** LangGraph is already in your stack; you need custom graph logic (tools, multi-step reasoning, HITL checkpoints).

### Option B: ADKAgentWorker

**File:** `src/workers/adk_agent.py`

**Pattern:** one `LlmAgent` behind a `Runner` (no `SequentialAgent`: deprecated in ADK 2.x in favour of `Workflow`). Create the session once (`get_session` returns `None` when missing; it does not raise). `InMemorySessionService` is single-instance; use a persistent session service when you scale out. Only text reaches the agent (`reference/voice-adk-integration.md` section 1).

**Reference:** `reference/worker-pipeline-gemini.md` § ADKAgentWorker

**Use when:** Google ADK is already in your stack; you want ADK's built-in session and memory management.

**Unit test (both):** Inject a mock LLM/runner. Send a `Transcription`. Verify an `AgentResponse` appears in output queue with non-empty `text`.

**Verification gate:** Agent generates a response for a test input. `ConversationHistory` has correct entries after response.

---

## Phase 6: Wire Pipeline

**Goal:** `StreamingConversation` orchestrator that connects all workers via queues and manages the WebSocket.

**Files:**
- `src/conversation.py` — `StreamingConversation`: queues, worker wiring, `_output_loop`, `_send_speech`
- `src/main.py` — FastAPI app with `asynccontextmanager` lifespan, `/conversation` WebSocket endpoint, `/health` endpoint

**Queue topology:**
```
WebSocket recv → transcriber.send_audio()
transcriber.output_queue → transcription_queue → agent.input_queue
agent.output_queue → agent_queue → synthesizer.input_queue
synthesizer.output_queue → synthesis_queue → _output_loop → WebSocket send
```

**Critical:** Use `asynccontextmanager` lifespan — NEVER `@app.on_event`.

**Reference:** `reference/worker-pipeline-gemini.md` § FastAPI WebSocket Server, `reference/worker-pipeline.md` § StreamingConversation Orchestrator

**Integration test:** Connect a test WebSocket client. Send synthetic PCM silence. Verify pipeline starts without errors. Verify `terminate()` cleans up all workers and tasks.

**Verification gate:** `uvicorn src.main:app --reload` starts cleanly. `/health` returns `{"status": "ok"}`. WebSocket `/conversation` accepts a connection.

---

## Phase 7: Interrupt Handling

**Goal:** Users can interrupt the bot mid-sentence. Pipeline recovers correctly.

**Files to create/update:**
- `src/interrupt.py` — `InterruptibleEvent` dataclass
- `src/workers/transcriptions_worker.py` — detects interrupt, flags `Transcription.is_interrupt`
- `src/conversation.py` — `broadcast_interrupt()`, rate-limited `_send_speech()` with stop check, transcriber mute before delivery

**Steps:**
1. Add `InterruptibleEvent` with `interrupt()` and `is_interrupted()` methods
2. Add `TranscriptionsWorker` between transcriber output and agent input — detects new transcription while bot speaks
3. Implement `broadcast_interrupt()` — drains interruptible event queue, cancels agent task
4. Update `_send_speech()` to: mute transcriber first, check `stop_event.is_interrupted()` before every chunk, wait `seconds_per_chunk` between chunks, unmute in `finally`
5. After cutoff: call `agent.history.update_last_bot_on_cutoff(message_sent)`

**Reference:** `reference/interrupt-handling.md` (complete)

**Test the interrupt path:**
```python
async def test_interrupt():
    conversation = create_test_conversation()
    await conversation.start()

    # Simulate bot speaking
    synthesis_result = create_mock_synthesis_result(duration_seconds=5)
    synthesis_task = asyncio.create_task(
        conversation._send_speech(synthesis_result)
    )

    # Interrupt after 1 second
    await asyncio.sleep(1)
    conversation.broadcast_interrupt()

    message_sent, cut_off = await synthesis_task
    assert cut_off is True
    assert len(message_sent) < len(synthesis_result.full_text)
```

**Verification gate:** Interrupt stops audio delivery within one chunk duration (~85ms). Transcriber unmutes after interrupt. History contains partial message.

---

## Phase 8: Test

**Unit tests (each worker in isolation):**
- `test_base_worker.py` — queue flow, terminate, error recovery continues
- `test_gemini_transcriber.py` — mock session, audio sending, mute/unmute
- `test_gemini_synthesizer.py` — mock API response, chunk generator, get_message_up_to
- `test_langgraph_agent.py` or `test_adk_agent.py` — mock LLM, history update, cancel task
- `test_interrupt.py` — InterruptibleEvent, broadcast_interrupt, rate-limited delivery, cutoff detection

**Integration test:**
- `test_pipeline.py` — full pipeline with mocked Gemini clients; verify audio flows end-to-end

```bash
pytest -q                              # All tests
pytest -q tests/test_interrupt.py      # Interrupt path specifically
pytest -q --cov=src --cov-report=term-missing  # With coverage
```

**Verification gate:** All tests pass. Interrupt path has test coverage.

---

## Phase 9: Deploy

**Dockerfile (multi-stage):**
```dockerfile
FROM python:3.14-slim AS base
WORKDIR /app
RUN pip install uv

FROM base AS builder
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM base AS runtime
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Environment variables required at runtime:**
- `GEMINI_API_KEY` — never in Dockerfile or image
- `GEMINI_LIVE_MODEL`, `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE`

**Health check:** `/health` endpoint — used by Cloud Run and load balancers.

**Production considerations:**
- Add WebSocket heartbeat (ping every 25s) to prevent proxy timeout
- Implement Gemini Live session reconnect with exponential backoff
- Add `structlog` request logging with conversation ID for tracing
- Rate-limit concurrent WebSocket connections

---

## Checklist Before Shipping

- [ ] Iron Law: every worker has its own `asyncio.Queue` — no direct calls between workers
- [ ] `google-genai` used throughout — never `google-generativeai`
- [ ] Gemini Live connected via WebSocket (`aio.live.connect`) — never HTTP polling
- [ ] Audio format: 16kHz PCM for input, correct MIME type sent
- [ ] Transcriber muted before bot speaks, unmuted in `finally`
- [ ] Interrupt check before every audio chunk in `_send_speech`
- [ ] `asyncio.sleep(seconds_per_chunk)` rate-limits audio delivery
- [ ] `update_last_bot_on_cutoff()` called after cutoff
- [ ] Gemini Live reconnect implemented
- [ ] All `except` blocks log with `structlog` — no silent failures
- [ ] No `print()` anywhere — structured logging only
- [ ] `asynccontextmanager` lifespan — no `@app.on_event`
- [ ] Tests cover happy path and interrupt path
- [ ] `security-reviewer` run — WebSocket input validated, API key not logged

---

## Common Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Transcriptions never arrive | Wrong SDK or polling Live API | Use `google-genai`, WebSocket protocol |
| `INVALID_ARGUMENT` from Gemini | Wrong audio format | 16kHz PCM, `audio/pcm;rate=16000` |
| Bot hears itself | Transcriber not muted | `transcriber.mute()` before delivery |
| User can't interrupt | No rate limiting on chunks | `asyncio.sleep(seconds_per_chunk)` |
| Audio fragments/gaps | Multiple TTS calls | Buffer full response before synthesizing |
| Pipeline stops after 30 min | Session expired | Implement reconnect in transcriber |

See `reference/common-pitfalls.md` for full details on each.

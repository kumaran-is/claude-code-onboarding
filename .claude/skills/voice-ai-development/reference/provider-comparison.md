# Voice Provider Selection

Provider-neutral. The pipeline (transcriber → agent → synthesizer, or one live speech-to-speech session) is the same whichever provider fills each role. Choose per role by measurement on YOUR audio, not by a provider table.

Prices, latencies, language counts and accuracy rankings change often and differ by tier, region and audio: this file deliberately lists none. Read each provider's current pricing, quota and model pages, and record the numbers you measured (with the date) in your decision record (`ai-decision-record` skill).

---

## 1. Pick the architecture first

| Option | Use when | Notes |
|--------|----------|-------|
| Batch: record → upload → STT → text agent → (optional) TTS | Turn-taking is fine; latency budget is seconds | Simplest, cheapest to operate, easiest to evaluate and to fall back to text |
| Streaming STT → text agent → streaming TTS | Users expect replies while speaking ends; you want to keep a text agent you already evaluate | Barge-in and echo handling are yours (`interrupt-handling.md`) |
| Live speech-to-speech session (e.g. Gemini Live) | Sub-second conversational turn-taking is the product requirement | Hardest to evaluate and govern; session limits, reconnects and per-minute cost |

Start with the simplest row that meets the latency target. Keep the provider choice in one module; clients stay provider-agnostic (they speak your WebSocket/HTTP protocol, never a provider's).

---

## 2. Selection criteria per role

| Criterion | STT | Agent LLM | TTS | How to measure |
|-----------|-----|-----------|-----|----------------|
| Quality | word error rate on your accents, noise and vocabulary | your golden-set eval | listening test / MOS-style rubric with real users | hash-pinned audio fixtures; same set for every candidate |
| Latency | time to first partial / final transcript | time to first token | time to first audio | p50/p95 from a load test in your region |
| Cost | per audio minute | per token | per character / audio second | provider pricing page on the decision date × your measured volumes |
| Languages | the languages you must support, in the delivered language | same | same, incl. mid-sentence switching if needed | per-language fixtures |
| Interrupts | streaming partials, VAD / end-of-speech signals | cancellable streaming | cancellable streaming | barge-in test (`interrupt-handling.md` checklist) |
| Data handling | retention, training opt-out, region, deletion | same | same; voice consent for custom voices | provider DPA + config |
| Auth | keyless (workload identity) in deployed envs where possible; else secret manager | same | same | `gemini-provider-setup.md` auth matrix pattern |
| Quotas | concurrent streams, minutes per period | tokens / requests per minute | characters / requests per minute | provider console for your tier |

---

## 3. Candidate providers (non-exhaustive, alphabetical per role)

| Role | Examples |
|------|----------|
| STT (streaming) | AssemblyAI, Azure Speech, Deepgram, Google (Gemini Live input transcription, Cloud Speech-to-Text), OpenAI |
| Agent LLM | Anthropic, Google Gemini, OpenAI, self-hosted models — through the provider abstraction in `agentic-ai-dev/reference/llm-inference-and-model-routing.md` |
| TTS | Amazon Polly, Azure TTS, ElevenLabs, Google (Gemini TTS, Cloud TTS), OpenAI |
| Live speech-to-speech | Google Gemini Live, OpenAI Realtime |

Inclusion is not endorsement; verify each candidate's current API before writing code (Context7 or the provider docs).

---

## 4. Configuration, not code

```python
class VoiceProviders(BaseSettings):
    STT_PROVIDER: Literal["gemini_live", "deepgram", "azure"]   # the ones you have adapters for
    TTS_PROVIDER: Literal["gemini_tts", "elevenlabs", "azure"]
    AGENT_MODEL: str        # every model id/voice comes from the environment, no defaults
    TTS_MODEL_FAST: str
    LIVE_VOICE: str
```

Switching a provider or model is a release: shadow or dual-run on the same golden audio set and sampled traffic, compare quality, safety, cost and p95 per metric, then switch behind a flag (`deployment-ci-cd/reference/llmops-release-and-rollout.md`).

---

## 5. Decision record template (fill with measured numbers)

| Role | Candidate | Quality (metric, value) | p95 latency | Cost / unit (pricing page date) | Languages OK | Data terms OK | Decision |
|------|-----------|-------------------------|-------------|---------------------------------|--------------|---------------|----------|
| STT | | | | | | | |
| TTS | | | | | | | |
| Agent | | | | | | | |

# Gemini TTS — Text-to-Speech Models

> OPTIONAL provider extension. Model ids and voice names come from settings (`TTS_MODEL_QUALITY`, `TTS_MODEL_FAST`, `TTS_VOICE`), never literals in code: pick them from the provider's models page and prebuilt-voice list, probe each id on every backend you deploy to (`gemini-api-dev`). SDK: `google-genai` — NEVER `google-generativeai` (deprecated). Signatures checked against `google-genai` 3.6.1; the snippets below were not executed against the live API.
>
> Logging in these snippets uses stdlib `logging` with an `error_type` field; in a service use the toolkit's structlog `log_exception` (`deployment-ci-cd/reference/python-observability.md` section 2). Never log the text being synthesized, audio, file names or exception messages.

## Overview

Gemini TTS converts text to high-quality speech with natural language style control. Features:
- **Style via natural language**: "whispered mysterious tone", "enthusiastic Australian accent"
- **Multi-speaker**: named speakers for podcast/dialogue generation
- **Many languages**: mid-sentence language switching (check the docs' supported-language list for yours)
- **Output**: raw PCM bytes (convertible to WAV/MP3)

---

## 1. Model Selection Guide

| Scenario | Setting | Reason |
|----------|---------|--------|
| Production audiobook / final voiceover | `TTS_MODEL_QUALITY` | Highest naturalness, prosody fidelity |
| Podcast / interview dialogue | `TTS_MODEL_QUALITY` | Multi-speaker quality critical |
| Real-time assistant reply | `TTS_MODEL_FAST` | Lower latency and cost |
| E-learning narration, drafts, notifications | `TTS_MODEL_FAST` | Good quality at scale |

Which provider model fills each tier is a configuration decision recorded with an eval run, not a code change (`deployment-ci-cd/reference/llmops-release-and-rollout.md`).

---

## 2. Single-Speaker TTS with Style Control

```python
import logging
import wave
import io
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)
client = genai.Client()


def synthesize_speech(
    text: str,
    *,
    style_prompt: str = "",
    model: str,
    voice_name: str,
) -> bytes:
    """
    Synthesize speech from text.

    Args:
        text: The text to synthesize.
        style_prompt: Natural language style instruction.
                      Examples:
                        "Speak in a warm, friendly tone"
                        "whispered mysterious tone"
                        "enthusiastic Australian accent"
                        "slow and deliberate, as if explaining to a child"
        model: TTS model ID.
        voice_name: Prebuilt voice name from settings (provider's voice list).

    Returns:
        Raw PCM audio bytes (16-bit, 24kHz, mono).

    Raises:
        ValueError: If text is empty.
        google.genai.errors.APIError: On API failure (branch on exc.code).
    """
    if not text or not text.strip():
        logger.error("synthesize_speech called with empty text")
        raise ValueError("text must not be empty")

    # Combine style instruction with content
    contents = f"{style_prompt}\n\n{text}".strip() if style_prompt else text

    logger.info(
        "Synthesizing speech",
        extra={"model": model, "voice": voice_name, "text_length": len(text)},
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            ),
        )
    except Exception as exc:
        logger.error("TTS synthesis failed", extra={"error_type": type(exc).__name__, "model": model})
        raise

    # A blocked or empty response has no candidate/part: treat it as an error, not silence
    candidate = response.candidates[0] if response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content else None
    audio_data = parts[0].inline_data.data if parts and parts[0].inline_data else None
    if not audio_data:
        logger.error("TTS returned empty audio data", extra={"model": model})
        raise RuntimeError("TTS API returned empty audio — content may have been blocked")

    logger.info("Speech synthesis complete", extra={"audio_bytes": len(audio_data)})
    return audio_data
```

---

## 3. Multi-Speaker TTS — Podcast / Dialogue

```python
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)
client = genai.Client()


def synthesize_dialogue(
    turns: list[dict[str, str]],
    *,
    model: str,
    voices: tuple[str, str],
) -> bytes:
    """
    Synthesize a multi-speaker dialogue.

    Args:
        turns: List of {"speaker": "Host", "text": "Welcome to the show!"}.
               Each unique speaker name gets a consistent voice.
               Maximum 2 named speakers per request.
        model: settings.TTS_MODEL_QUALITY recommended for podcasts.
        voices: two prebuilt voice names from settings.

    Returns:
        Raw PCM bytes of the complete dialogue.

    Raises:
        ValueError: If turns is empty or speaker count exceeds 2.
    """
    if not turns:
        logger.error("synthesize_dialogue called with empty turns")
        raise ValueError("turns must not be empty")

    unique_speakers = list({t["speaker"] for t in turns})
    if len(unique_speakers) > 2:
        logger.error(
            "Too many speakers for multi-speaker TTS",
            extra={"speaker_count": len(unique_speakers)},
        )
        raise ValueError(f"Maximum 2 speakers supported, got {len(unique_speakers)}")

    # Build the script text with speaker labels
    script = "\n\n".join(
        f'{turn["speaker"]}: {turn["text"]}' for turn in turns
    )

    # Assign voices from configuration, one per speaker
    voice_assignments = dict(zip(unique_speakers, voices, strict=False))
    multi_speaker_config = types.MultiSpeakerVoiceConfig(
        speaker_voice_configs=[
            types.SpeakerVoiceConfig(
                speaker=speaker,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                ),
            )
            for speaker, voice in voice_assignments.items()
        ]
    )

    logger.info(
        "Synthesizing dialogue",
        extra={"turns": len(turns), "speakers": unique_speakers, "model": model},
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=script,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    multi_speaker_voice_config=multi_speaker_config
                ),
            ),
        )
    except Exception as exc:
        logger.error("Multi-speaker TTS failed", extra={"error_type": type(exc).__name__})
        raise

    # A blocked or empty response has no candidate/part: treat it as an error, not silence
    candidate = response.candidates[0] if response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content else None
    audio_data = parts[0].inline_data.data if parts and parts[0].inline_data else None
    if not audio_data:
        logger.error("Multi-speaker TTS returned empty audio")
        raise RuntimeError("Multi-speaker TTS returned empty audio — content may have been blocked")

    logger.info("Dialogue synthesis complete", extra={"audio_bytes": len(audio_data)})
    return audio_data
```

---

## 4. Language Switching Mid-Sentence

```python
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)
client = genai.Client()


def synthesize_multilingual(
    text: str,
    *,
    model: str,
    voice_name: str,
) -> bytes:
    """
    Synthesize text that switches languages mid-sentence.

    Gemini TTS auto-detects language switches — no explicit markup needed.
    Check the supported-language list in the docs. Write the text naturally.

    Example text:
        "Welcome to our service. Bienvenido a nuestro servicio.
         我们很高兴为您服务。Nous sommes heureux de vous servir."
    """
    if not text or not text.strip():
        raise ValueError("text must not be empty")

    logger.info(
        "Synthesizing multilingual speech",
        extra={"model": model, "text_length": len(text)},
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            ),
        )
    except Exception as exc:
        logger.error("Multilingual TTS failed", extra={"error_type": type(exc).__name__})
        raise

    # A blocked or empty response has no candidate/part: treat it as an error, not silence
    candidate = response.candidates[0] if response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content else None
    audio_data = parts[0].inline_data.data if parts and parts[0].inline_data else None
    if not audio_data:
        raise RuntimeError("Multilingual TTS returned empty audio")

    return audio_data
```

---

## 5. Save Audio to File (WAV / MP3)

```python
import wave
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# PCM specs from Gemini TTS
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit


def save_as_wav(audio_bytes: bytes, output_path: str | Path) -> Path:
    """
    Save raw PCM audio bytes from Gemini TTS as a WAV file.

    Args:
        audio_bytes: Raw PCM bytes from synthesize_speech().
        output_path: Destination file path (.wav extension recommended).

    Returns:
        Path to the saved file.
    """
    output_path = Path(output_path)
    if not audio_bytes:
        logger.error("save_as_wav called with empty audio bytes")
        raise ValueError("audio_bytes must not be empty")

    try:
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_bytes)
    except Exception as exc:
        logger.error("Failed to save WAV file", extra={"error_type": type(exc).__name__})
        raise

    logger.info("WAV file saved", extra={"bytes": len(audio_bytes)})
    return output_path


def save_as_mp3(audio_bytes: bytes, output_path: str | Path) -> Path:
    """
    Convert and save raw PCM bytes as MP3 using pydub.

    Requires: uv add pydub && brew install ffmpeg (macOS) or apt install ffmpeg (Linux)
    """
    try:
        from pydub import AudioSegment
    except ImportError as exc:
        logger.error("pydub not installed — run: uv add pydub", extra={"error_type": type(exc).__name__})
        raise ImportError("pydub required for MP3 export. Run: uv add pydub") from exc

    output_path = Path(output_path)

    try:
        audio_segment = AudioSegment(
            data=audio_bytes,
            sample_width=SAMPLE_WIDTH,
            frame_rate=SAMPLE_RATE,
            channels=CHANNELS,
        )
        audio_segment.export(str(output_path), format="mp3")
    except Exception as exc:
        logger.error("Failed to save MP3 file", extra={"error_type": type(exc).__name__})
        raise

    logger.info("MP3 file saved")
    return output_path
```

---

## 6. FastAPI Endpoint — TTS API

```python
import logging
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .settings import settings  # TTS_MODEL_FAST, TTS_MODEL_QUALITY, TTS_ALLOWED_VOICES

logger = logging.getLogger(__name__)


class TTSRequest(BaseModel):
    # Callers pick a TIER and a voice from the configured allowlist; never a raw model id.
    text: str = Field(min_length=1, max_length=5_000)   # bounds cost per request
    tier: Literal["fast", "quality"] = "fast"
    voice: str
    style: str = Field(default="", max_length=200)

    @field_validator("voice")
    @classmethod
    def valid_voice(cls, v: str) -> str:
        if v not in settings.TTS_ALLOWED_VOICES:        # configured list, not hard-coded names
            raise ValueError("voice is not allowed")
        return v


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TTS API server starting")
    yield
    logger.info("TTS API server shutting down")


app = FastAPI(lifespan=lifespan)


@app.post("/tts", response_class=StreamingResponse)
async def text_to_speech(request: TTSRequest) -> StreamingResponse:
    """
    Synthesize speech from text.

    Returns WAV audio (the model returns raw PCM; wrap it in a WAV header).
    Authenticate and rate-limit this route: every call is billed.
    """
    import asyncio
    from .synthesize import pcm_to_wav, synthesize_speech  # your synthesis helpers

    model = settings.TTS_MODEL_QUALITY if request.tier == "quality" else settings.TTS_MODEL_FAST
    try:
        # synthesize_speech is blocking: run it off the event loop
        pcm = await asyncio.to_thread(
            synthesize_speech,
            request.text,
            style_prompt=request.style,
            model=model,
            voice_name=request.voice,
        )
        audio_bytes = pcm_to_wav(pcm)   # same wave-module logic as save_as_wav, into BytesIO
    except ValueError as exc:
        logger.warning("TTS validation error", extra={"error_type": type(exc).__name__})
        raise HTTPException(status_code=422, detail="Invalid speech request") from exc
    except RuntimeError as exc:
        logger.error("TTS synthesis error", extra={"error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail="Speech synthesis failed") from exc
    except Exception as exc:
        logger.error("Unexpected TTS error", extra={"error_type": type(exc).__name__})
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    return StreamingResponse(
        BytesIO(audio_bytes),
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=speech.wav"},
    )
```

---

## 7. Streaming TTS for Lower Latency

For long texts, stream chunks as they arrive rather than waiting for full synthesis. Confirm on the models page that your TTS model supports streamed output before relying on this (not verified here):

```python
import logging
from google import genai
from google.genai import types
from typing import AsyncIterator

logger = logging.getLogger(__name__)
client = genai.Client()


async def stream_tts(
    text: str,
    *,
    model: str,
    voice_name: str,
) -> AsyncIterator[bytes]:
    """
    Stream TTS audio chunks as they arrive for lower time-to-first-audio.

    Yields raw PCM byte chunks. Caller must assemble or play directly.
    """
    if not text or not text.strip():
        logger.error("stream_tts called with empty text")
        raise ValueError("text must not be empty")

    logger.info("Starting streaming TTS", extra={"model": model, "text_length": len(text)})

    try:
        async for chunk in await client.aio.models.generate_content_stream(
            model=model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            ),
        ):
            if chunk.candidates and chunk.candidates[0].content.parts:
                part = chunk.candidates[0].content.parts[0]
                if hasattr(part, "inline_data") and part.inline_data.data:
                    yield part.inline_data.data

    except Exception as exc:
        logger.error("Streaming TTS failed", extra={"error_type": type(exc).__name__, "model": model})
        raise
```

---

## 8. Error Handling Reference

| Error | Cause | Handling |
|-------|-------|----------|
| `ValueError: text must not be empty` | Empty input | Validate before calling API |
| `google.genai.errors.ClientError`, `exc.code == 429` | Quota / rate limit | Bounded backoff with jitter, then a fixed error to the caller |
| `ClientError`, `exc.code == 400` | Unsupported language or malformed request | Log `error_type` + code, raise HTTPException 422 |
| `ClientError`, `exc.code in (401, 403)` | Credentials / permission | No retry; alert |
| Response with no audio part / a block reason | Content policy block | Log the block reason enum (never content), surface to the user |
| `RuntimeError: empty audio` | API returned no audio bytes | Content likely blocked — surface to user |
| `ImportError: pydub` | MP3 export without pydub installed | Install pydub + ffmpeg, or export as WAV |

```python
import asyncio
import logging
import random

from google.genai import errors

logger = logging.getLogger(__name__)


async def synthesize_with_retry(text: str, **kwargs) -> bytes:
    """Synthesize speech with exponential backoff retry on rate limits."""
    from .synthesize import synthesize_speech
    import asyncio

    delay = 1.0
    max_retries = 3

    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(synthesize_speech, text, **kwargs)
        except errors.APIError as exc:
            if exc.code == 429 and attempt < max_retries - 1:
                logger.warning("tts_rate_limited", extra={"attempt": attempt, "retry_in_s": delay})
                await asyncio.sleep(delay + random.uniform(0, delay / 2))   # jitter
                delay *= 2
                continue
            logger.error("tts_failed", extra={"error_type": type(exc).__name__, "code": exc.code})
            raise   # 400/401/403/5xx and the last 429: no further retry
    raise AssertionError("unreachable")
```

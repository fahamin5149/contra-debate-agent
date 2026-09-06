from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np
from kokoro_onnx import Kokoro

from contra.audio.types import AudioChunk
from contra.config.models import TtsConfig
from contra.observability.logging import get_logger

log = get_logger(__name__)

KOKORO_RATE = 24_000


class KokoroTts:
    """Kokoro-82M via kokoro-onnx, CPU-resident.

    Known caveat (ADR-0006): ONNX has higher per-call overhead than PyTorch
    and is relatively slower on very short inputs (RTF 0.72 vs 0.49). The
    SentenceSegmenter's 15-char minimum exists to stop us paying that cost on
    three-word fragments.
    """

    def __init__(self, config: TtsConfig) -> None:
        self._kokoro = Kokoro(config.model_path, config.voices_path)
        self._voice = config.voice
        self._speed = config.speed
        self._cancelled = False

    @property
    def sample_rate(self) -> int:
        return KOKORO_RATE

    async def synthesise(
        self, text: str, span: tuple[int, int], sequence: int
    ) -> AsyncIterator[AudioChunk]:
        self._cancelled = False
        cleaned = text.strip()
        if not cleaned:
            return

        samples, rate = await asyncio.to_thread(
            self._kokoro.create, cleaned, self._voice, self._speed, "en-us"
        )
        if self._cancelled:
            return

        pcm16 = (np.clip(np.asarray(samples), -1.0, 1.0) * 32767).astype(np.int16)
        duration_ms = len(pcm16) / rate * 1000.0
        log.info("tts_synthesised", chars=len(cleaned), duration_ms=round(duration_ms))
        yield AudioChunk(
            samples=pcm16.tobytes(),
            text_span=span,
            duration_ms=duration_ms,
            sequence=sequence,
        )

    def cancel(self) -> None:
        self._cancelled = True

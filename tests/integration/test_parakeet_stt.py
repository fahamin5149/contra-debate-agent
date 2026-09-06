"""Parakeet STT integration tests.

The silence test is the important one: it verifies NFR-A-02, the single
property that decided ADR-0005. Whisper-family models hallucinate text into
dead air; a debate contains deliberate 2-3 second thinking pauses, and phantom
text entering the argument history means the agent rebuts sentences the user
never said.
"""

import numpy as np
import pytest
import soundfile as sf

from contra.audio.types import AudioFrame
from contra.config.models import SttConfig
from contra.speech.parakeet_stt import ParakeetStt

pytestmark = pytest.mark.slow

SILENCE_WAV = "tests/fixtures/audio/silence.wav"


def feed_wav(stt: ParakeetStt, path: str) -> None:
    pcm, sr = sf.read(path, dtype="int16")
    assert sr == 16000, f"fixture must be 16 kHz, got {sr}"
    for i in range(0, len(pcm) - 320, 320):
        stt.feed(AudioFrame(samples=pcm[i : i + 320].tobytes(), sample_rate=16000, timestamp_ms=0))


async def test_silence_produces_empty_transcript():
    """NFR-A-02 — the reason Parakeet was chosen over Whisper."""
    stt = ParakeetStt(SttConfig())
    feed_wav(stt, SILENCE_WAV)
    result = await stt.finalise()
    assert result.text.strip() == "", f"hallucinated on silence: {result.text!r}"


async def test_reset_clears_buffered_audio():
    stt = ParakeetStt(SttConfig())
    feed_wav(stt, SILENCE_WAV)
    stt.reset()
    result = await stt.finalise()
    assert result.text.strip() == ""
    assert result.confidence == 0.0


async def test_no_audio_yields_empty_without_calling_model():
    stt = ParakeetStt(SttConfig())
    result = await stt.finalise()
    assert result.text == ""


async def test_pure_digital_silence_also_produces_nothing():
    stt = ParakeetStt(SttConfig())
    zeros = np.zeros(16000 * 5, dtype=np.int16)
    for i in range(0, len(zeros) - 320, 320):
        stt.feed(
            AudioFrame(samples=zeros[i : i + 320].tobytes(), sample_rate=16000, timestamp_ms=0)
        )
    result = await stt.finalise()
    assert result.text.strip() == ""

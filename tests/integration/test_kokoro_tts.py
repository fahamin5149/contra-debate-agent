import pytest

from contra.config.models import TtsConfig
from contra.speech.kokoro_tts import KokoroTts

pytestmark = pytest.mark.slow


async def test_synthesises_audio_with_correct_span():
    tts = KokoroTts(TtsConfig())
    chunks = [c async for c in tts.synthesise("Productivity gains are contested.", (0, 33), 0)]
    assert chunks
    assert chunks[0].text_span == (0, 33)
    assert len(chunks[0].samples) > 0
    assert tts.sample_rate == 24000


async def test_empty_text_yields_nothing():
    tts = KokoroTts(TtsConfig())
    chunks = [c async for c in tts.synthesise("   ", (0, 3), 0)]
    assert chunks == []


async def test_short_unit_still_produces_audio():
    """ADR-0006 notes ONNX Kokoro is slow on short text; it must still work."""
    tts = KokoroTts(TtsConfig())
    chunks = [c async for c in tts.synthesise("Right, so.", (0, 10), 0)]
    assert chunks and len(chunks[0].samples) > 0


async def test_duration_is_plausible_for_the_text():
    tts = KokoroTts(TtsConfig())
    text = "Remote workers report higher output than office workers do."
    chunks = [c async for c in tts.synthesise(text, (0, len(text)), 0)]
    total_ms = sum(c.duration_ms for c in chunks)
    # ~60 chars of speech should land roughly in the 1.5-8 s range
    assert 1_500 < total_ms < 8_000, f"implausible duration {total_ms} ms"

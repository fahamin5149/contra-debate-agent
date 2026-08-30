import pytest

from contra.audio.types import AudioChunk, AudioFrame, PlaybackPosition
from contra.debate.types import Message, Transcript, TurnHandle


def test_audio_chunk_is_immutable():
    c = AudioChunk(samples=b"\x00\x01", text_span=(0, 10), duration_ms=20.0, sequence=0)
    with pytest.raises(Exception):
        c.sequence = 5  # type: ignore[misc]


def test_audio_chunk_rejects_inverted_span():
    with pytest.raises(ValueError):
        AudioChunk(samples=b"", text_span=(10, 5), duration_ms=1.0, sequence=0)


def test_audio_chunk_rejects_negative_start():
    with pytest.raises(ValueError):
        AudioChunk(samples=b"", text_span=(-1, 5), duration_ms=1.0, sequence=0)


def test_playback_position_zero_is_valid():
    p = PlaybackPosition(chunks_played=0, samples_played=0, last_complete_span_end=0)
    assert p.last_complete_span_end == 0


def test_message_roles_constrained():
    assert Message(role="user", content="hi").role == "user"
    with pytest.raises(ValueError):
        Message(role="bot", content="hi")  # type: ignore[arg-type]


def test_audio_frame_duration():
    f = AudioFrame(samples=b"\x00" * 640, sample_rate=16000, timestamp_ms=0.0)
    assert f.duration_ms == pytest.approx(20.0)


def test_turn_handle_and_transcript_defaults():
    assert TurnHandle(index=3).index == 3
    assert Transcript(text="hi").confidence == 1.0

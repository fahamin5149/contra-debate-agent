from contra.audio.types import AudioChunk
from contra.audio.webrtc_transport import PlaybackQueue


def chunk(seq: int, span: tuple[int, int], samples: int = 480) -> AudioChunk:
    return AudioChunk(
        samples=b"\x00\x00" * samples,
        text_span=span,
        duration_ms=samples / 24.0,
        sequence=seq,
    )


async def test_clear_reports_zero_when_nothing_played():
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 33)))
    pos = q.clear()
    assert pos.chunks_played == 0
    assert pos.last_complete_span_end == 0


async def test_fully_consumed_chunk_advances_span_end():
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 33), samples=480))
    while await q.read(960):
        pass
    pos = q.clear()
    assert pos.chunks_played == 1
    assert pos.last_complete_span_end == 33


async def test_partially_played_chunk_does_not_count():
    """Conservative by design: under-recording is safer than over-recording."""
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 33), samples=2400))
    await q.read(480)  # consume only part of it
    pos = q.clear()
    assert pos.chunks_played == 0
    assert pos.last_complete_span_end == 0


async def test_second_chunk_advances_span_further():
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 33), samples=480))
    await q.put(chunk(1, (33, 70), samples=480))
    while await q.read(960):
        pass
    pos = q.clear()
    assert pos.chunks_played == 2
    assert pos.last_complete_span_end == 70


async def test_clear_discards_queued_chunks():
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 10)))
    await q.put(chunk(1, (10, 20)))
    q.clear()
    assert not q.is_playing
    assert await q.read(480) == b""


async def test_reset_turn_clears_counters():
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 33), samples=480))
    while await q.read(960):
        pass
    q.reset_turn()
    pos = q.clear()
    assert pos.chunks_played == 0
    assert pos.last_complete_span_end == 0

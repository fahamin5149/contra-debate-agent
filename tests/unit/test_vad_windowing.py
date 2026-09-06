from contra.audio.types import AudioFrame
from contra.detect.silero_vad import WindowAccumulator


def frame(n_samples: int) -> AudioFrame:
    return AudioFrame(samples=b"\x00\x00" * n_samples, sample_rate=16000, timestamp_ms=0)


def test_accumulates_20ms_frames_into_512_sample_windows():
    """Silero v5 requires EXACTLY 512 samples at 16 kHz; our frames are 320."""
    acc = WindowAccumulator(window_samples=512)
    assert acc.push(frame(320)) == []  # 320 < 512
    windows = acc.push(frame(320))  # 640 >= 512
    assert len(windows) == 1
    assert len(windows[0]) == 512


def test_leftover_carries_to_next_window():
    acc = WindowAccumulator(window_samples=512)
    acc.push(frame(320))
    acc.push(frame(320))  # 128 left over
    assert acc.push(frame(320)) == []  # 448, still short
    assert len(acc.push(frame(320))) == 1  # 768 -> one window


def test_reset_discards_partial_buffer():
    acc = WindowAccumulator(window_samples=512)
    acc.push(frame(320))
    acc.reset()
    assert acc.push(frame(320)) == []


def test_large_frame_yields_multiple_windows():
    acc = WindowAccumulator(window_samples=512)
    windows = acc.push(frame(1600))
    assert len(windows) == 3
    assert all(len(w) == 512 for w in windows)

from __future__ import annotations

import fractions

import av
import numpy as np

__all__ = ["frame_to_pcm16_mono", "pcm16_to_frame", "make_resampler"]


def make_resampler(target_rate: int) -> av.audio.resampler.AudioResampler:
    """A reusable resampler. Reusing one instance preserves internal state,
    which matters for correct output when resampling a continuous stream."""
    return av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=target_rate)


def frame_to_pcm16_mono(
    frame: av.AudioFrame, resampler: av.audio.resampler.AudioResampler
) -> bytes:
    """Convert an inbound WebRTC frame to mono PCM16 at the resampler's rate."""
    out = b""
    for resampled in resampler.resample(frame):
        out += bytes(resampled.planes[0])[: resampled.samples * 2]
    return out


def pcm16_to_frame(pcm: bytes, rate: int, pts: int) -> av.AudioFrame:
    """Wrap mono PCM16 bytes in an av.AudioFrame for outbound WebRTC."""
    samples = np.frombuffer(pcm, dtype=np.int16).reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
    frame.sample_rate = rate
    frame.pts = pts
    frame.time_base = fractions.Fraction(1, rate)
    return frame

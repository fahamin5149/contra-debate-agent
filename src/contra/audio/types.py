from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFrame:
    """A fixed-size window of PCM16 mono audio."""

    samples: bytes
    sample_rate: int
    timestamp_ms: float

    @property
    def duration_ms(self) -> float:
        return (len(self.samples) / 2) / self.sample_rate * 1000.0


@dataclass(frozen=True)
class AudioChunk:
    """Synthesised audio plus the span of dispatched text it renders.

    text_span offsets are ABSOLUTE within the agent turn, not relative to the
    sentence. A per-sentence offset makes truncation across multiple chunks
    silently wrong. See internal API spec section D.
    """

    samples: bytes
    text_span: tuple[int, int]
    duration_ms: float
    sequence: int

    def __post_init__(self) -> None:
        start, end = self.text_span
        if start < 0 or end < start:
            raise ValueError(f"invalid text_span {self.text_span}")


@dataclass(frozen=True)
class PlaybackPosition:
    """How far playback actually got. Returned by AudioOutput.clear().

    A partially-played chunk counts as NOT played — under-recording what the
    user heard is far safer than over-recording it (FR-13).
    """

    chunks_played: int
    samples_played: int
    last_complete_span_end: int

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from contra.audio.types import AudioChunk, AudioFrame, PlaybackPosition


class AudioInput(Protocol):
    """Source of microphone audio, already echo-cancelled by the browser."""

    def frames(self) -> AsyncIterator[AudioFrame]: ...


class AudioOutput(Protocol):
    """Sink for synthesised audio that reports what was actually played."""

    async def enqueue(self, chunk: AudioChunk) -> None: ...

    def clear(self) -> PlaybackPosition:
        """Stop immediately, discard the queue, report how far playback got.

        The return value is what makes FR-13 possible.
        """
        ...

    def reset_turn(self) -> None: ...

    @property
    def is_playing(self) -> bool: ...

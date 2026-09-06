from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from contra.audio.types import AudioChunk, AudioFrame
from contra.debate.types import Transcript


class SttStage(Protocol):
    def feed(self, frame: AudioFrame) -> None: ...

    async def finalise(self) -> Transcript: ...

    def reset(self) -> None: ...


class TtsStage(Protocol):
    def synthesise(
        self, text: str, span: tuple[int, int], sequence: int
    ) -> AsyncIterator[AudioChunk]: ...

    def cancel(self) -> None: ...

    @property
    def sample_rate(self) -> int: ...

from __future__ import annotations

from enum import Enum
from typing import Protocol

from contra.audio.types import AudioFrame


class VadEvent(Enum):
    SPEECH_START = "speech_start"
    SPEECH_CONTINUE = "speech_continue"
    SILENCE = "silence"
    SILENCE_SUSTAINED = "silence_sustained"


class VadStage(Protocol):
    """Answers 'is sound happening', never 'is this person finished'.

    Turn commitment belongs to the turn detector (Phase 2). Conflating the two
    is the classic voice-agent design error.
    """

    def process(self, frame: AudioFrame) -> VadEvent: ...

    def reset(self) -> None: ...

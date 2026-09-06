from __future__ import annotations

from contra.audio.types import PlaybackPosition
from contra.debate.types import Message, TurnHandle

__all__ = ["ConversationState"]


def _round_back_to_word(text: str, end: int) -> str:
    """Cut text at `end`, backing up so we never end mid-word.

    Chunks are segmented on punctuation and clause boundaries, so `end` is
    normally already a clean boundary. This is the defensive case.
    """
    if end <= 0:
        return ""
    if end >= len(text):
        return text.rstrip()
    if text[end].isspace() or text[end - 1].isspace():
        return text[:end].rstrip()
    cut = text.rfind(" ", 0, end)
    return "" if cut == -1 else text[:cut].rstrip()


class ConversationState:
    """Holds the debate's memory.

    Three quantities diverge during an agent turn and they are NOT equal::

        generated  >=  dispatched  >=  actually played

    History must record the THIRD (FR-13). Recording the first means the agent
    later says "as I explained" about words the user never heard, which reads
    to the user as fabrication.
    """

    def __init__(self) -> None:
        self._system: str | None = None
        self._messages: list[Message] = []
        self._dispatched: dict[int, str] = {}
        self._closed: set[int] = set()
        self._next_index = 0

    def set_system_prompt(self, prompt: str) -> None:
        self._system = prompt

    def append_user_turn(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            self._messages.append(Message(role="user", content=cleaned))

    def begin_agent_turn(self) -> TurnHandle:
        handle = TurnHandle(index=self._next_index)
        self._next_index += 1
        self._dispatched[handle.index] = ""
        return handle

    def record_dispatched(self, handle: TurnHandle, text: str) -> None:
        """Record text handed to TTS. Call with the cumulative turn text."""
        self._check_open(handle)
        self._dispatched[handle.index] = text

    def generated_text(self, handle: TurnHandle) -> str:
        """Full dispatched text, retained for analysis. NEVER sent to the model."""
        return self._dispatched.get(handle.index, "")

    def commit_agent_turn(self, handle: TurnHandle) -> None:
        """Turn completed normally — everything dispatched was spoken."""
        self._check_open(handle)
        self._append_spoken(handle, self._dispatched[handle.index].strip())

    def truncate_to_spoken(self, handle: TurnHandle, position: PlaybackPosition) -> None:
        """Barge-in: record ONLY what actually reached the user's ears (FR-13)."""
        self._check_open(handle)
        dispatched = self._dispatched[handle.index]
        spoken = _round_back_to_word(dispatched, position.last_complete_span_end)
        self._append_spoken(handle, spoken)

    def messages(self) -> list[Message]:
        head = [Message(role="system", content=self._system)] if self._system else []
        return head + list(self._messages)

    def token_estimate(self) -> int:
        """~4 chars per token. Cheap proxy; exact counts need the tokenizer."""
        return sum(len(m.content) for m in self.messages()) // 4

    def _append_spoken(self, handle: TurnHandle, spoken: str) -> None:
        self._closed.add(handle.index)
        if spoken:
            self._messages.append(Message(role="assistant", content=spoken))

    def _check_open(self, handle: TurnHandle) -> None:
        if handle.index not in self._dispatched:
            raise ValueError(f"unknown turn handle {handle.index}")
        if handle.index in self._closed:
            raise ValueError(f"turn {handle.index} is already closed")

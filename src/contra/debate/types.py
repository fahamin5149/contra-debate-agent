from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]
_VALID_ROLES = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True)
class Message:
    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in _VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(_VALID_ROLES)}, got {self.role!r}")


@dataclass(frozen=True)
class TurnHandle:
    """Opaque reference to an in-progress agent turn."""

    index: int


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float = 1.0

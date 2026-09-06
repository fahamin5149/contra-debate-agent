from __future__ import annotations

__all__ = ["SentenceSegmenter"]

TERMINALS = ".!?"
CLAUSE = ",;:"


class SentenceSegmenter:
    """Converts an LLM token stream into TTS-sized speakable units.

    Small component, outsized effect on perceived latency: time-to-first-audio
    depends almost entirely on how quickly unit one is emitted.

    The minimum-unit rule exists because ONNX Kokoro has high per-call overhead
    and is slower than PyTorch on very short inputs (ADR-0006). Dispatching
    "Well," on its own pays that cost for three words.
    """

    def __init__(
        self,
        min_unit_chars: int = 15,
        max_unit_chars: int = 200,
        clause_threshold: int = 80,
    ) -> None:
        self._min = min_unit_chars
        self._max = max_unit_chars
        self._clause_threshold = clause_threshold
        self._buf = ""

    def feed(self, token: str) -> list[str]:
        self._buf += token
        out: list[str] = []
        while (split := self._find_split()) is not None:
            unit = self._buf[:split].strip()
            self._buf = self._buf[split:].lstrip()
            if unit:
                out.append(unit)
        return out

    def flush(self) -> list[str]:
        unit = self._buf.strip()
        self._buf = ""
        return [unit] if unit else []

    def _find_split(self) -> int | None:
        buf = self._buf
        n = len(buf)

        if n >= self._max:
            cut = buf.rfind(" ", self._min, self._max)
            return cut if cut > 0 else self._max

        # Terminal punctuation, but only once we have seen the following
        # whitespace. Waiting for whitespace is what stops "13.5" splitting
        # into "13." and "5".
        for i in range(n - 1):
            if buf[i] in TERMINALS and buf[i + 1].isspace() and (i + 1) >= self._min:
                return i + 1

        if n >= self._clause_threshold:
            for i in range(n - 1):
                if buf[i] in CLAUSE and buf[i + 1].isspace() and (i + 1) >= self._min:
                    return i + 1
        return None

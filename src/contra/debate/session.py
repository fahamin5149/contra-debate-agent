from __future__ import annotations

import time
from enum import Enum
from typing import Any

from contra.debate.conversation import ConversationState
from contra.debate.segmenter import SentenceSegmenter
from contra.observability.logging import get_logger

log = get_logger(__name__)


class SessionState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ENDED = "ended"


class Session:
    """Phase 1 loop: VAD -> STT -> LLM -> segment -> TTS -> playback.

    Uses a fixed silence timer, not semantic turn detection. Deliberately
    omitted until Phase 2: Smart Turn v2, barge-in, persistence, the real
    debate persona, and error recovery.
    """

    def __init__(
        self,
        audio_in: Any,
        audio_out: Any,
        vad: Any,
        stt: Any,
        llm: Any,
        tts: Any,
        system_prompt: str,
        min_unit_chars: int = 15,
        max_unit_chars: int = 200,
    ) -> None:
        self._in = audio_in
        self._out = audio_out
        self._vad = vad
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._min_unit = min_unit_chars
        self._max_unit = max_unit_chars
        self.state = SessionState.IDLE
        self.state_store = ConversationState()
        self.state_store.set_system_prompt(system_prompt)
        self.last_turn_ms: float | None = None
        self.turn_latencies: list[float] = []

    async def run(self) -> None:
        from contra.detect.interfaces import VadEvent

        self.state = SessionState.LISTENING
        heard_speech = False
        log.info("session_started")

        async for frame in self._in.frames():
            if self.state is SessionState.SPEAKING:
                continue  # Phase 1: no barge-in

            event = self._vad.process(frame)

            if event is VadEvent.SPEECH_START:
                heard_speech = True
                self._stt.reset()
                self._stt.feed(frame)
                log.info("speech_start")
            elif event is VadEvent.SPEECH_CONTINUE:
                self._stt.feed(frame)
            elif event is VadEvent.SILENCE_SUSTAINED and heard_speech:
                heard_speech = False
                await self._handle_turn()

        self.state = SessionState.ENDED
        log.info("session_ended")

    async def _handle_turn(self) -> None:
        started = time.perf_counter()
        self.state = SessionState.THINKING

        transcript = await self._stt.finalise()
        if not transcript.text:
            log.info("empty_transcript_skipping_turn")
            self.state = SessionState.LISTENING
            return

        log.info("user_turn", chars=len(transcript.text))
        self.state_store.append_user_turn(transcript.text)

        handle = self.state_store.begin_agent_turn()
        segmenter = SentenceSegmenter(self._min_unit, self._max_unit)
        dispatched = ""
        sequence = 0
        first_audio_ms: float | None = None

        async def speak(unit: str, seq: int) -> tuple[str, float | None]:
            nonlocal dispatched
            span = (len(dispatched), len(dispatched) + len(unit))
            dispatched = f"{dispatched}{unit} "
            self.state_store.record_dispatched(handle, dispatched)
            first: float | None = None
            async for chunk in self._tts.synthesise(unit, span, seq):
                await self._out.enqueue(chunk)
                if first is None:
                    first = (time.perf_counter() - started) * 1000.0
            return dispatched, first

        async for token in self._llm.stream(self.state_store.messages()):
            for unit in segmenter.feed(token):
                _, first = await speak(unit, sequence)
                if first is not None and first_audio_ms is None:
                    first_audio_ms = first
                    self.state = SessionState.SPEAKING
                sequence += 1

        for unit in segmenter.flush():
            _, first = await speak(unit, sequence)
            if first is not None and first_audio_ms is None:
                first_audio_ms = first
                self.state = SessionState.SPEAKING
            sequence += 1

        self.state_store.commit_agent_turn(handle)
        self.last_turn_ms = first_audio_ms
        if first_audio_ms is not None:
            self.turn_latencies.append(first_audio_ms)
        log.info(
            "turn_complete",
            first_audio_ms=round(first_audio_ms) if first_audio_ms else None,
            chars=len(dispatched),
            units=sequence,
        )
        self._out.reset_turn()
        self.state = SessionState.LISTENING

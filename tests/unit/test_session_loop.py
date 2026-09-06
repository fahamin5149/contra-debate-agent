import asyncio
from collections.abc import AsyncIterator

from contra.audio.types import AudioChunk, AudioFrame, PlaybackPosition
from contra.debate.session import Session, SessionState
from contra.debate.types import Transcript
from contra.detect.interfaces import VadEvent


class FakeVad:
    """Reports speech for N frames, then sustained silence."""

    def __init__(self, speech_frames: int) -> None:
        self._left = speech_frames
        self._fired = False

    def process(self, frame):
        if self._left > 0:
            self._left -= 1
            if not self._fired:
                self._fired = True
                return VadEvent.SPEECH_START
            return VadEvent.SPEECH_CONTINUE
        return VadEvent.SILENCE_SUSTAINED

    def reset(self):
        pass


class FakeStt:
    def __init__(self, text: str = "Remote work is better."):
        self.fed = 0
        self._text = text

    def feed(self, frame):
        self.fed += 1

    async def finalise(self):
        return Transcript(text=self._text)

    def reset(self):
        self.fed = 0


class FakeLlm:
    def __init__(self):
        self.cancelled = False
        self.seen_messages = None

    async def stream(self, messages) -> AsyncIterator[str]:
        self.seen_messages = messages
        for tok in ["Productivity", " gains", " are", " contested.", " "]:
            yield tok

    async def cancel(self):
        self.cancelled = True


class FakeTts:
    async def synthesise(self, text, span, sequence) -> AsyncIterator[AudioChunk]:
        yield AudioChunk(
            samples=b"\x00\x00" * 240, text_span=span, duration_ms=10.0, sequence=sequence
        )

    def cancel(self):
        pass

    @property
    def sample_rate(self):
        return 24000


class FakeOutput:
    def __init__(self):
        self.chunks = []
        self.resets = 0

    async def enqueue(self, chunk):
        self.chunks.append(chunk)

    def clear(self):
        return PlaybackPosition(0, 0, 0)

    def reset_turn(self):
        self.resets += 1

    @property
    def is_playing(self):
        return False


class FakeInput:
    def __init__(self, n):
        self._n = n

    async def frames(self) -> AsyncIterator[AudioFrame]:
        for _ in range(self._n):
            yield AudioFrame(samples=b"\x00\x00" * 320, sample_rate=16000, timestamp_ms=0)
            await asyncio.sleep(0)


def build(out=None, stt=None, llm=None):
    return Session(
        audio_in=FakeInput(6),
        audio_out=out or FakeOutput(),
        vad=FakeVad(3),
        stt=stt or FakeStt(),
        llm=llm or FakeLlm(),
        tts=FakeTts(),
        system_prompt="You argue the other side.",
    )


async def test_one_turn_produces_audio_and_history():
    out = FakeOutput()
    session = build(out=out)
    await asyncio.wait_for(session.run(), timeout=5.0)
    assert out.chunks, "no audio was produced"
    msgs = session.state_store.messages()
    assert msgs[0].role == "system"
    assert msgs[1].role == "user"
    assert msgs[2].role == "assistant"
    assert "Productivity" in msgs[2].content


async def test_agent_turn_text_matches_what_was_enqueued():
    out = FakeOutput()
    session = build(out=out)
    await asyncio.wait_for(session.run(), timeout=5.0)
    spoken = session.state_store.messages()[-1].content
    max_span_end = max(c.text_span[1] for c in out.chunks)
    assert len(spoken) <= max_span_end


async def test_state_returns_to_listening_after_turn():
    session = build()
    await asyncio.wait_for(session.run(), timeout=5.0)
    assert session.state in (SessionState.LISTENING, SessionState.ENDED)


async def test_empty_transcript_skips_turn():
    out = FakeOutput()
    session = build(out=out, stt=FakeStt(text=""))
    await asyncio.wait_for(session.run(), timeout=5.0)
    assert out.chunks == []
    assert all(m.role == "system" for m in session.state_store.messages())


async def test_llm_receives_system_prompt_and_user_turn():
    llm = FakeLlm()
    session = build(llm=llm)
    await asyncio.wait_for(session.run(), timeout=5.0)
    roles = [m.role for m in llm.seen_messages]
    assert roles == ["system", "user"]


async def test_latency_is_recorded():
    session = build()
    await asyncio.wait_for(session.run(), timeout=5.0)
    assert session.last_turn_ms is not None
    assert session.turn_latencies

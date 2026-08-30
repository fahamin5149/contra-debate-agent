from __future__ import annotations

import asyncio
import fractions
from collections import deque
from collections.abc import AsyncIterator

import av
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription

from contra.audio.resample import make_resampler, pcm16_to_frame
from contra.audio.types import AudioChunk, AudioFrame, PlaybackPosition
from contra.observability.logging import get_logger

log = get_logger(__name__)

OUTPUT_RATE = 48_000  # WebRTC standard
FRAME_SECONDS = 0.02  # 20 ms


class PlaybackQueue:
    """Byte queue of synthesised audio that tracks what was actually consumed.

    The span bookkeeping here is what makes FR-13 possible: clear() reports how
    far playback got, and a partially-consumed chunk deliberately does NOT
    count. Under-recording what the user heard is far safer than over-recording.
    """

    def __init__(self) -> None:
        self._pending: deque[AudioChunk] = deque()
        self._current: AudioChunk | None = None
        self._offset = 0
        self._chunks_played = 0
        self._samples_played = 0
        self._last_complete_span_end = 0

    async def put(self, chunk: AudioChunk) -> None:
        self._pending.append(chunk)

    async def read(self, n_samples: int) -> bytes:
        """Pull up to n_samples (int16) of PCM. Returns b'' when empty."""
        want = n_samples * 2
        out = b""
        while len(out) < want:
            if self._current is None:
                if not self._pending:
                    break
                self._current = self._pending.popleft()
                self._offset = 0
            remaining = self._current.samples[self._offset :]
            take = remaining[: want - len(out)]
            out += take
            self._offset += len(take)
            self._samples_played += len(take) // 2
            if self._offset >= len(self._current.samples):
                self._chunks_played += 1
                self._last_complete_span_end = self._current.text_span[1]
                self._current = None
        return out

    def clear(self) -> PlaybackPosition:
        pos = PlaybackPosition(
            chunks_played=self._chunks_played,
            samples_played=self._samples_played,
            last_complete_span_end=self._last_complete_span_end,
        )
        self._pending.clear()
        self._current = None
        self._offset = 0
        return pos

    def reset_turn(self) -> None:
        self._chunks_played = 0
        self._samples_played = 0
        self._last_complete_span_end = 0

    @property
    def is_playing(self) -> bool:
        return self._current is not None or bool(self._pending)


class _OutboundTrack(MediaStreamTrack):
    """Pulls from the PlaybackQueue; emits silence when the queue is empty."""

    kind = "audio"

    def __init__(self, queue: PlaybackQueue, source_rate: int) -> None:
        super().__init__()
        self._queue = queue
        self._source_rate = source_rate
        self._samples_per_frame = int(source_rate * FRAME_SECONDS)
        self._pts = 0
        self._resampler = make_resampler(OUTPUT_RATE)

    async def recv(self) -> av.AudioFrame:
        # Pace to real time: one 20 ms frame per 20 ms of wall clock.
        await asyncio.sleep(FRAME_SECONDS)
        need = self._samples_per_frame
        pcm = await self._queue.read(need)
        if len(pcm) < need * 2:
            pcm += b"\x00" * (need * 2 - len(pcm))

        src = pcm16_to_frame(pcm, self._source_rate, self._pts)
        self._pts += need
        resampled = self._resampler.resample(src)
        if not resampled:
            # Resampler buffered this input; emit silence to keep pacing.
            silent = pcm16_to_frame(
                b"\x00" * int(OUTPUT_RATE * FRAME_SECONDS) * 2, OUTPUT_RATE, self._pts
            )
            silent.time_base = fractions.Fraction(1, OUTPUT_RATE)
            return silent
        return resampled[0]


class WebRtcTransport:
    """Implements AudioInput and AudioOutput over a browser peer connection.

    Echo cancellation happens in the browser, upstream of this class: inbound
    audio arrives already cleaned (ADR-0012).
    """

    def __init__(
        self, sample_rate: int = 16_000, frame_ms: int = 20, tts_rate: int = 24_000
    ) -> None:
        self._sample_rate = sample_rate
        self._frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self._pc: RTCPeerConnection | None = None
        self._inbound: asyncio.Queue[AudioFrame] = asyncio.Queue(maxsize=200)
        self._queue = PlaybackQueue()
        self._tts_rate = tts_rate
        self._reader_task: asyncio.Task[None] | None = None
        self.frames_dropped = 0

    async def handle_offer(self, sdp: str, sdp_type: str) -> dict[str, str]:
        pc = RTCPeerConnection()
        self._pc = pc
        pc.addTrack(_OutboundTrack(self._queue, self._tts_rate))

        @pc.on("track")
        def on_track(track: MediaStreamTrack) -> None:
            log.info("inbound_track", kind=track.kind)
            if track.kind == "audio":
                self._reader_task = asyncio.create_task(self._read_track(track))

        @pc.on("connectionstatechange")
        async def on_state() -> None:
            log.info("pc_state", state=pc.connectionState)

        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=sdp_type))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        assert pc.localDescription is not None
        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def _read_track(self, track: MediaStreamTrack) -> None:
        resampler = make_resampler(self._sample_rate)
        buf = b""
        ts = 0.0
        try:
            while True:
                av_frame = await track.recv()
                for resampled in resampler.resample(av_frame):
                    buf += bytes(resampled.planes[0])[: resampled.samples * 2]
                while len(buf) >= self._frame_bytes:
                    piece, buf = buf[: self._frame_bytes], buf[self._frame_bytes :]
                    frame = AudioFrame(
                        samples=piece, sample_rate=self._sample_rate, timestamp_ms=ts
                    )
                    ts += frame.duration_ms
                    try:
                        self._inbound.put_nowait(frame)
                    except asyncio.QueueFull:
                        self.frames_dropped += 1
                        log.warning("inbound_queue_full", dropped=self.frames_dropped)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # track ended or peer went away
            log.info("inbound_track_ended", reason=str(exc))

    async def frames(self) -> AsyncIterator[AudioFrame]:
        while True:
            yield await self._inbound.get()

    async def enqueue(self, chunk: AudioChunk) -> None:
        await self._queue.put(chunk)

    def clear(self) -> PlaybackPosition:
        return self._queue.clear()

    def reset_turn(self) -> None:
        self._queue.reset_turn()

    @property
    def is_playing(self) -> bool:
        return self._queue.is_playing

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._pc is not None:
            await self._pc.close()

"""End-to-end WebRTC media loopback, with an aiortc peer standing in for the browser.

> **What this can and cannot verify.**
>
> This exercises the real signalling handshake and the real media path: SDP
> offer/answer, ICE on loopback, Opus encode/decode, resampling in both
> directions, and the span-tracking playback queue.
>
> It **cannot** verify acoustic echo cancellation. AEC lives in the browser and
> needs real speakers, a real microphone, and a real room. That is BM-05 and it
> requires a human (NFR-A-05, NFR-A-06).
"""

from __future__ import annotations

import asyncio
import fractions

import av
import numpy as np
import pytest
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription

from contra.audio.types import AudioChunk
from contra.audio.webrtc_transport import WebRtcTransport

pytestmark = pytest.mark.slow

CLIENT_RATE = 48_000
SAMPLES_PER_FRAME = 960  # 20 ms


class ToneTrack(MediaStreamTrack):
    """Stands in for a browser microphone track."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._pts = 0

    async def recv(self) -> av.AudioFrame:
        await asyncio.sleep(0.02)
        t = (np.arange(SAMPLES_PER_FRAME) + self._pts) / CLIENT_RATE
        pcm = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16).reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(pcm, format="s16", layout="mono")
        frame.sample_rate = CLIENT_RATE
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, CLIENT_RATE)
        self._pts += SAMPLES_PER_FRAME
        return frame


async def _connect(transport: WebRtcTransport) -> tuple[RTCPeerConnection, asyncio.Queue]:
    client = RTCPeerConnection()
    client.addTrack(ToneTrack())

    received: asyncio.Queue = asyncio.Queue()

    @client.on("track")
    def on_track(track: MediaStreamTrack) -> None:
        async def drain() -> None:
            try:
                while True:
                    await received.put(await track.recv())
            except Exception:  # noqa: BLE001 - track ends when the test finishes
                pass

        asyncio.create_task(drain())

    offer = await client.createOffer()
    await client.setLocalDescription(offer)
    assert client.localDescription is not None

    answer = await transport.handle_offer(client.localDescription.sdp, client.localDescription.type)
    await client.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
    return client, received


async def test_signalling_handshake_produces_an_answer():
    transport = WebRtcTransport()
    client, _ = await _connect(transport)
    try:
        assert client.remoteDescription is not None
        assert client.remoteDescription.type == "answer"
    finally:
        await client.close()
        await transport.close()


async def test_inbound_audio_reaches_the_transport_as_16khz_frames():
    """Verifies the full inbound path: Opus -> aiortc -> resample -> AudioFrame."""
    transport = WebRtcTransport(sample_rate=16_000, frame_ms=20)
    client, _ = await _connect(transport)
    try:
        frames = []
        gen = transport.frames()
        for _ in range(5):
            frames.append(await asyncio.wait_for(gen.__anext__(), timeout=10.0))
        assert len(frames) == 5
        for f in frames:
            assert f.sample_rate == 16_000
            assert len(f.samples) == 640, "20 ms at 16 kHz mono PCM16 = 640 bytes"
        assert transport.frames_dropped == 0
    finally:
        await client.close()
        await transport.close()


async def test_outbound_audio_reaches_the_client():
    """Verifies the full outbound path: AudioChunk -> queue -> resample -> Opus."""
    transport = WebRtcTransport(tts_rate=24_000)
    client, received = await _connect(transport)
    try:
        t = np.arange(24_000) / 24_000
        pcm = (np.sin(2 * np.pi * 330 * t) * 10_000).astype(np.int16)
        await transport.enqueue(
            AudioChunk(samples=pcm.tobytes(), text_span=(0, 20), duration_ms=1000.0, sequence=0)
        )
        frame = await asyncio.wait_for(received.get(), timeout=10.0)
        assert frame.sample_rate > 0
        assert frame.samples > 0
    finally:
        await client.close()
        await transport.close()


async def test_playback_position_advances_after_audio_is_consumed():
    """The FR-13 mechanism, exercised over a real peer connection."""
    transport = WebRtcTransport(tts_rate=24_000)
    client, received = await _connect(transport)
    try:
        pcm = np.zeros(4_800, dtype=np.int16)  # 200 ms at 24 kHz
        await transport.enqueue(
            AudioChunk(samples=pcm.tobytes(), text_span=(0, 33), duration_ms=200.0, sequence=0)
        )
        for _ in range(15):
            await asyncio.wait_for(received.get(), timeout=10.0)
        position = transport.clear()
        assert position.chunks_played == 1
        assert position.last_complete_span_end == 33
    finally:
        await client.close()
        await transport.close()

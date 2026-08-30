from __future__ import annotations

import asyncio

from fastapi import FastAPI

from contra.audio.webrtc_transport import WebRtcTransport
from contra.config.models import Config
from contra.debate.llm_client import LlmClient
from contra.debate.session import Session
from contra.detect.silero_vad import SileroVad
from contra.observability.logging import get_logger
from contra.speech.kokoro_tts import KokoroTts
from contra.speech.parakeet_stt import ParakeetStt
from contra.ui.server import create_app

log = get_logger(__name__)

# Phase 1 uses a generic prompt. The real debate persona is a versioned file
# under prompts/ and lands in Phase 3 (ADR-0011).
PHASE1_PROMPT = (
    "You are a debate opponent in a live spoken conversation. Argue against "
    "whatever position the user states. Keep replies to two or three short "
    "sentences. No markdown, no lists, no stage directions."
)


def build_app(config: Config) -> tuple[FastAPI, WebRtcTransport, Session]:
    """The ONLY module that constructs concrete implementations.

    Swapping a component is a one-line change here (NFR-M-01).
    """
    log.info("loading_models")
    tts = KokoroTts(config.tts)
    transport = WebRtcTransport(
        sample_rate=config.audio.sample_rate,
        frame_ms=config.audio.frame_ms,
        tts_rate=tts.sample_rate,
    )
    vad = SileroVad(
        "models/silero_vad.onnx",
        config.vad.threshold,
        config.vad.silence_confirm_ms,
        config.audio.sample_rate,
    )
    stt = ParakeetStt(config.stt)
    llm = LlmClient(config.llm)
    log.info("models_loaded")

    session = Session(
        audio_in=transport,
        audio_out=transport,
        vad=vad,
        stt=stt,
        llm=llm,
        tts=tts,
        system_prompt=PHASE1_PROMPT,
        min_unit_chars=config.tts.min_unit_chars,
        max_unit_chars=config.tts.max_unit_chars,
    )

    async def on_offer(sdp: str, sdp_type: str) -> dict[str, str]:
        answer = await transport.handle_offer(sdp, sdp_type)
        asyncio.create_task(session.run())
        return answer

    return create_app(config, on_offer), transport, session

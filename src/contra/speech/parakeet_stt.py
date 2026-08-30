from __future__ import annotations

import asyncio

import numpy as np
import onnx_asr
import onnxruntime as ort

from contra.audio.types import AudioFrame
from contra.config.models import SttConfig
from contra.debate.types import Transcript
from contra.observability.logging import get_logger

log = get_logger(__name__)


class ParakeetStt:
    """Parakeet TDT 0.6B v3 via onnx-asr — no PyTorch, no NeMo, no transformers.

    Chosen primarily because it almost never emits text during silence
    (NFR-A-02). Whisper-family models hallucinate "Thank you for watching!"
    into dead air; in a debate with deliberate thinking pauses that phantom
    text enters the argument history and the agent rebuts sentences the user
    never said (ADR-0005).

    Not a streaming model: we transcribe a complete utterance on VAD
    boundaries rather than word-by-word. Fine for turn-based debate.
    """

    def __init__(self, config: SttConfig) -> None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = config.num_threads
        opts.inter_op_num_threads = 1
        # (model_type, local_path) — never a bare path, which onnx-asr would
        # resolve against HuggingFace and break the offline guarantee.
        self._model = onnx_asr.load_model(
            config.model_type,
            config.model_dir,
            quantization=config.quantization,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._buf: list[bytes] = []

    def feed(self, frame: AudioFrame) -> None:
        self._buf.append(frame.samples)

    async def finalise(self) -> Transcript:
        if not self._buf:
            return Transcript(text="", confidence=0.0)
        pcm = b"".join(self._buf)
        self._buf.clear()
        waveform = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        # to_thread is mandatory: a blocking call here stalls audio capture.
        text = await asyncio.to_thread(self._model.recognize, waveform)
        log.info("stt_finalised", chars=len(text or ""), samples=len(waveform))
        return Transcript(text=(text or "").strip(), confidence=1.0)

    def reset(self) -> None:
        self._buf.clear()

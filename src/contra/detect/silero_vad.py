from __future__ import annotations

import numpy as np
import onnxruntime as ort

from contra.audio.types import AudioFrame
from contra.detect.interfaces import VadEvent
from contra.observability.logging import get_logger

log = get_logger(__name__)

WINDOW_SAMPLES = 512  # Silero v5 requires exactly this at 16 kHz


class WindowAccumulator:
    """Buffers variable-size frames into fixed-size windows.

    Our transport emits 20 ms frames (320 samples at 16 kHz) but Silero v5
    requires exactly 512. This bridges the mismatch without dropping audio.
    """

    def __init__(self, window_samples: int = WINDOW_SAMPLES) -> None:
        self._window = window_samples
        self._buf = np.zeros(0, dtype=np.float32)

    def push(self, frame: AudioFrame) -> list[np.ndarray]:
        pcm = np.frombuffer(frame.samples, dtype=np.int16).astype(np.float32) / 32768.0
        self._buf = np.concatenate([self._buf, pcm])
        out: list[np.ndarray] = []
        while len(self._buf) >= self._window:
            out.append(self._buf[: self._window])
            self._buf = self._buf[self._window :]
        return out

    def reset(self) -> None:
        self._buf = np.zeros(0, dtype=np.float32)


class SileroVad:
    """Silero VAD v5 via onnxruntime.

    Deliberately NOT the `silero-vad` pip package, which pulls in PyTorch
    (~200 MB CPU-only). Using the ONNX model directly keeps torch out of the
    dependency tree entirely, consistent with Parakeet and Kokoro.
    """

    def __init__(
        self,
        model_path: str,
        threshold: float = 0.5,
        silence_confirm_ms: int = 800,
        sample_rate: int = 16_000,
    ) -> None:
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._sess = ort.InferenceSession(
            model_path, sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._input_names = {i.name for i in self._sess.get_inputs()}
        self._threshold = threshold
        self._silence_confirm_ms = silence_confirm_ms
        self._sample_rate = sample_rate
        self._acc = WindowAccumulator()
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._speaking = False
        self._silence_ms = 0.0
        self._n_windows = 0
        self._peak_prob = 0.0

    def process(self, frame: AudioFrame) -> VadEvent:
        windows = self._acc.push(frame)
        if not windows:
            return VadEvent.SPEECH_CONTINUE if self._speaking else VadEvent.SILENCE

        prob = 0.0
        for window in windows:
            feeds: dict[str, np.ndarray] = {
                "input": window.reshape(1, -1).astype(np.float32),
                "state": self._state,
                "sr": np.array(self._sample_rate, dtype=np.int64),
            }
            feeds = {k: v for k, v in feeds.items() if k in self._input_names}
            out, self._state = self._sess.run(None, feeds)
            prob = max(prob, float(np.asarray(out).reshape(-1)[0]))

        window_ms = len(windows) * WINDOW_SAMPLES / self._sample_rate * 1000.0

        # Diagnostic: if audio_in shows signal but peak_prob stays near zero,
        # the threshold is the problem, not the audio path.
        self._n_windows += len(windows)
        self._peak_prob = max(self._peak_prob, prob)
        if self._n_windows >= 30:
            log.info("vad", peak_prob=round(self._peak_prob, 3), threshold=self._threshold)
            self._n_windows = 0
            self._peak_prob = 0.0

        if prob >= self._threshold:
            self._silence_ms = 0.0
            if not self._speaking:
                self._speaking = True
                return VadEvent.SPEECH_START
            return VadEvent.SPEECH_CONTINUE

        self._silence_ms += window_ms
        if self._speaking and self._silence_ms >= self._silence_confirm_ms:
            self._speaking = False
            return VadEvent.SILENCE_SUSTAINED
        return VadEvent.SILENCE

    def reset(self) -> None:
        self._acc.reset()
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._speaking = False
        self._silence_ms = 0.0

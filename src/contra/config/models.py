from __future__ import annotations

from dataclasses import dataclass, field


class ConfigError(Exception):
    """Raised at startup for any invalid configuration value.

    Failing loudly is deliberate: silently coercing a bad value produces the
    worst class of bug in this project — mysteriously poor debate quality,
    weeks later, with no signal connecting cause to effect.
    """

    def __init__(self, key: str, value: object, expected: str) -> None:
        super().__init__(f"{key} = {value!r}\n  Expected: {expected}")
        self.key = key
        self.value = value
        self.expected = expected


def _in_range(key: str, v: float, lo: float, hi: float) -> None:
    if not (lo <= v <= hi):
        raise ConfigError(key, v, f"{lo} to {hi}")


@dataclass(frozen=True)
class SamplingConfig:
    temperature: float = 0.7
    top_p: float = 0.8
    top_k: int = 20
    min_p: float = 0.0
    presence_penalty: float = 1.5
    repeat_penalty: float = 1.0

    def __post_init__(self) -> None:
        _in_range("llm.sampling.temperature", self.temperature, 0.0, 2.0)
        _in_range("llm.sampling.top_p", self.top_p, 0.0, 1.0)
        _in_range("llm.sampling.min_p", self.min_p, 0.0, 1.0)
        _in_range("llm.sampling.presence_penalty", self.presence_penalty, -2.0, 2.0)
        if self.top_k < 0:
            raise ConfigError("llm.sampling.top_k", self.top_k, ">= 0")


@dataclass(frozen=True)
class LlmConfig:
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "qwen3.5-9b"
    timeout_s: float = 30.0
    max_response_tokens: int = 220
    enable_thinking: bool = False
    sampling: SamplingConfig = field(default_factory=SamplingConfig)

    def __post_init__(self) -> None:
        if self.max_response_tokens <= 0:
            raise ConfigError("llm.max_response_tokens", self.max_response_tokens, "> 0")


@dataclass(frozen=True)
class WebRtcConfig:
    echo_cancellation: bool = True
    noise_suppression: bool = True
    auto_gain_control: bool = True


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 16000
    frame_ms: int = 20
    output_buffer_ms: int = 100
    webrtc: WebRtcConfig = field(default_factory=WebRtcConfig)

    def __post_init__(self) -> None:
        if self.output_buffer_ms > 200:
            raise ConfigError(
                "audio.output_buffer_ms",
                self.output_buffer_ms,
                "<= 200 — above this, NFR-P-03 barge-in (300 ms) is unreachable",
            )


@dataclass(frozen=True)
class VadConfig:
    threshold: float = 0.5
    min_speech_ms: int = 100
    silence_confirm_ms: int = 800

    def __post_init__(self) -> None:
        _in_range("vad.threshold", self.threshold, 0.0, 1.0)


@dataclass(frozen=True)
class SttConfig:
    # onnx-asr's first argument is a model NAME or TYPE, not a path. Passing a
    # directory there makes it resolve against HuggingFace — which would break
    # the offline guarantee (NFR-S-01). Use the architecture type plus an
    # explicit local `model_dir` so nothing touches the network.
    model_type: str = "nemo-conformer-tdt"
    model_dir: str = "models/parakeet-tdt-0.6b-v3-onnx"
    # int8 is the right variant for CPU inference (ADR-0004): faster than fp32
    # and 652 MB vs 2.4 GB on disk.
    quantization: str | None = "int8"
    num_threads: int = 4


@dataclass(frozen=True)
class TtsConfig:
    model_path: str = "models/kokoro-v1.0.onnx"
    voices_path: str = "models/voices-v1.0.bin"
    voice: str = "af_heart"
    speed: float = 1.0
    min_unit_chars: int = 15
    max_unit_chars: int = 200

    def __post_init__(self) -> None:
        if self.min_unit_chars >= self.max_unit_chars:
            raise ConfigError("tts.min_unit_chars", self.min_unit_chars, "< tts.max_unit_chars")


@dataclass(frozen=True)
class UiConfig:
    host: str = "127.0.0.1"
    port: int = 8000

    def __post_init__(self) -> None:
        if self.host not in ("127.0.0.1", "localhost", "::1"):
            raise ConfigError(
                "ui.host",
                self.host,
                "must bind to loopback. These services have no authentication; "
                "binding to a routable address exposes an open inference endpoint "
                "and its context window. See NFR-S-03.",
            )


@dataclass(frozen=True)
class DebateConfig:
    max_response_seconds: int = 45


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(frozen=True)
class Config:
    llm: LlmConfig = field(default_factory=LlmConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    debate: DebateConfig = field(default_factory=DebateConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

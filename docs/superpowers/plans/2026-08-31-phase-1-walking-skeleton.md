# Phase 1 — Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A spoken utterance into laptop speakers/mic produces a spoken reply, end to end, through the browser — with no barge-in, no semantic turn detection, no persistence, and no debate persona.

**Architecture:** Audio enters and leaves through a browser page over WebRTC so Chrome's AEC3 can cancel the agent's own voice ([ADR-0012](../../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md)). Python receives the inbound track via `aiortc`, runs VAD → STT on CPU, calls `llama-server` over localhost HTTP with SSE streaming, segments tokens into speakable units, synthesises them on CPU, and pushes audio back over the same peer connection. The debate core (`ConversationState`, `SentenceSegmenter`) is pure logic with no I/O imports.

**Tech Stack:** Python 3.11 · FastAPI + uvicorn · aiortc + PyAV · onnxruntime (Silero VAD, Parakeet TDT, Kokoro) · openai SDK against llama-server · vanilla HTML/JS browser page

**Spec:** [`docs/README.md`](../../README.md) — specifically [M1 in milestones](../../07-planning/02-milestones.md), [Phase 1 in the roadmap](../../07-planning/01-roadmap.md), and [component design](../../02-architecture/02-component-design.md)

---

## ⚠ Phase 0 is a gate — read this first

**No benchmark has run.** `benchmarks/results/` is empty. Every performance number in the design is `[SOURCED]` or `[ESTIMATED]` from other people's hardware.

The plan is split so this is honest rather than blocking:

| Track | Tasks | Depends on Phase 0? |
|---|---|---|
| **A — pure logic + plumbing** | 1–7 | **No.** Safe to build now. No model, no measurement changes any of it. |
| **B — models and integration** | 8–14 | **Yes.** Outcomes below can change what you build. |

**Run [BM-01, BM-03, BM-05](../../04-quality/03-benchmark-plan.md) before starting Task 8.** These specifically:

| Benchmark | If it fails | Effect on this plan |
|---|---|---|
| **BM-01** < 18 tok/s | Switch to Qwen3.5-4B | Task 5 config values change; no code change |
| **BM-03** STT RTF > 0.3 | Fall back to faster-whisper | **Task 10 is rewritten** for a different engine |
| **BM-03** dropped audio frames > 0 | GIL not releasing | **Serious** — Task 8/10/11 need subprocess isolation |
| **BM-05** double-talk < 10/20 | AEC unworkable on this hardware | Push-to-talk becomes default; **Task 7 and 12 change** |

Task 8 begins with a checklist confirming these have run.

---

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include these.

- **Python 3.11.x** — not 3.12, not 3.13 ([ADR-0009](../../02-architecture/adr/0009-python-as-orchestration-language.md), RISK-04)
- **All service ports bind `127.0.0.1` only** — never `0.0.0.0`. Non-overridable (NFR-S-03, T-01)
- **`debate/` imports no I/O library** — enforced by `ruff` banned-imports, not convention
- **Pipecat appears only in `pipeline/assembly.py`** — Task 14 only ([ADR-0003](../../02-architecture/adr/0003-pipecat-as-orchestration-framework.md))
- **Never block the event loop** — use `asyncio.to_thread` for all model inference
- **No file over ~400 lines** without a documented reason (NFR-M-05)
- **Never log transcript content above `DEBUG`** (NFR-S-01)
- **Audio never touches framework/UI state** — `RTCPeerConnection` and audio elements live outside any component tree
- **Internal audio format: 16 kHz mono PCM16** — VAD and Parakeet native, avoids resampling
- **No `--mmproj`** when launching llama-server — the 918 MB vision projector stays unloaded
- Unit tests must run in **< 10 s with no models and no GPU**

---

## File Structure

```
pyproject.toml                          # deps, ruff/mypy/pytest config
config/default.yaml                     # committed defaults
src/contra/
├── __main__.py                         # entry point
├── app.py                              # composition root — ONLY wiring module
├── config/
│   ├── models.py                       # typed config dataclasses
│   └── loader.py                       # YAML + env merge, validation
├── observability/logging.py            # structlog setup
├── audio/
│   ├── types.py                        # AudioFrame, AudioChunk, PlaybackPosition
│   ├── interfaces.py                   # AudioInput, AudioOutput protocols
│   ├── resample.py                     # PyAV resampling helpers
│   └── webrtc_transport.py             # aiortc impl of the protocols
├── detect/
│   ├── interfaces.py                   # VadStage protocol
│   └── silero_vad.py                   # Silero v5 via onnxruntime (NOT torch)
├── speech/
│   ├── interfaces.py                   # SttStage, TtsStage protocols
│   ├── parakeet_stt.py                 # onnx-asr
│   └── kokoro_tts.py                   # kokoro-onnx
├── debate/                             # ← NO I/O imports
│   ├── types.py                        # Message, TurnHandle, Transcript
│   ├── conversation.py                 # ConversationState — FR-13 lives here
│   ├── segmenter.py                    # SentenceSegmenter
│   ├── llm_client.py                   # llama-server SSE client
│   └── session.py                      # minimal state machine
└── ui/
    ├── server.py                       # FastAPI: static + WebRTC signalling
    └── static/{index.html,app.js}
tests/unit/                             # fakes only, no models
tests/integration/                      # marked slow
```

---

## Task 1: Project scaffold, config, and logging

**Files:**
- Create: `pyproject.toml`, `config/default.yaml`, `src/contra/__init__.py`, `src/contra/config/models.py`, `src/contra/config/loader.py`, `src/contra/observability/logging.py`
- Test: `tests/unit/test_config_loader.py`

**Interfaces:**
- Consumes: nothing
- Produces: `load_config(config_dir: Path) -> Config`; `Config` with fields `.llm`, `.audio`, `.vad`, `.stt`, `.tts`, `.ui`, `.debate`; `setup_logging(level: str) -> None`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "contra"
version = "0.1.0"
requires-python = ">=3.11,<3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "aiortc>=1.9",
    "av>=12.0",
    "numpy>=1.26,<2.2",
    "openai>=1.50",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "structlog>=24.1",
    "onnxruntime>=1.19",
    "onnx-asr>=0.5",
    "kokoro-onnx>=0.4",
    "soundfile>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.6", "mypy>=1.11"]

[project.scripts]
contra = "contra.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/contra"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["slow: requires models or network"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "TID"]

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"onnx_asr".msg = "Only in speech/. Core depends on interfaces."
"kokoro_onnx".msg = "Only in speech/."
"onnxruntime".msg = "Only in speech/ and detect/."
"aiortc".msg = "Only in audio/."
"av".msg = "Only in audio/."
"pipecat".msg = "Only in pipeline/assembly.py."
"torch".msg = "Not a dependency. Use onnxruntime."

[tool.ruff.lint.per-file-ignores]
"src/contra/speech/*" = ["TID251"]
"src/contra/detect/*" = ["TID251"]
"src/contra/audio/*" = ["TID251"]
"tests/*" = ["TID251"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true

[[tool.mypy.overrides]]
module = "contra.debate.*"
strict = true
```

- [ ] **Step 2: Create `config/default.yaml`**

```yaml
llm:
  base_url: "http://127.0.0.1:8080/v1"
  model: "qwen3.5-9b"
  timeout_s: 30
  max_response_tokens: 220
  enable_thinking: false
  sampling:
    temperature: 0.7
    top_p: 0.8
    top_k: 20
    min_p: 0.0
    presence_penalty: 1.5
    repeat_penalty: 1.0

audio:
  sample_rate: 16000
  frame_ms: 20
  output_buffer_ms: 100
  webrtc:
    echo_cancellation: true
    noise_suppression: true
    auto_gain_control: true

vad:
  threshold: 0.5
  min_speech_ms: 100
  silence_confirm_ms: 800   # Phase 1: fixed timer, no semantic detection

stt:
  model_dir: "models/parakeet-tdt-0.6b-v3-onnx"
  num_threads: 4

tts:
  model_path: "models/kokoro-v1.0.onnx"
  voices_path: "models/voices-v1.0.bin"
  voice: "af_heart"
  speed: 1.0
  min_unit_chars: 15
  max_unit_chars: 200

ui:
  host: "127.0.0.1"
  port: 8000

debate:
  max_response_seconds: 45

logging:
  level: "INFO"
```

- [ ] **Step 3: Write the failing test**

```python
# tests/unit/test_config_loader.py
import pytest
from pathlib import Path
from contra.config.loader import load_config, ConfigError

def test_loads_defaults(tmp_path: Path):
    (tmp_path / "default.yaml").write_text(
        "llm:\n"
        "  base_url: 'http://127.0.0.1:8080/v1'\n"
        "  model: 'qwen3.5-9b'\n"
        "  timeout_s: 30\n"
        "  max_response_tokens: 220\n"
        "  enable_thinking: false\n"
        "  sampling: {temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0,"
        " presence_penalty: 1.5, repeat_penalty: 1.0}\n"
        "ui: {host: '127.0.0.1', port: 8000}\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.llm.sampling.temperature == 0.7
    assert cfg.llm.sampling.presence_penalty == 1.5
    assert cfg.ui.port == 8000

def test_rejects_non_loopback_host(tmp_path: Path):
    (tmp_path / "default.yaml").write_text(
        "ui: {host: '0.0.0.0', port: 8000}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)
    assert "loopback" in str(exc.value).lower()

def test_rejects_out_of_range_temperature(tmp_path: Path):
    (tmp_path / "default.yaml").write_text(
        "llm:\n  sampling: {temperature: 3.5}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)
    assert "temperature" in str(exc.value)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contra.config'`

- [ ] **Step 5: Implement `src/contra/config/models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field

class ConfigError(Exception):
    def __init__(self, key: str, value: object, expected: str) -> None:
        super().__init__(f"{key} = {value!r}\n  Expected: {expected}")
        self.key = key

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

@dataclass(frozen=True)
class VadConfig:
    threshold: float = 0.5
    min_speech_ms: int = 100
    silence_confirm_ms: int = 800

@dataclass(frozen=True)
class SttConfig:
    model_dir: str = "models/parakeet-tdt-0.6b-v3-onnx"
    num_threads: int = 4

@dataclass(frozen=True)
class TtsConfig:
    model_path: str = "models/kokoro-v1.0.onnx"
    voices_path: str = "models/voices-v1.0.bin"
    voice: str = "af_heart"
    speed: float = 1.0
    min_unit_chars: int = 15
    max_unit_chars: int = 200

@dataclass(frozen=True)
class UiConfig:
    host: str = "127.0.0.1"
    port: int = 8000

    def __post_init__(self) -> None:
        if self.host not in ("127.0.0.1", "localhost", "::1"):
            raise ConfigError(
                "ui.host", self.host,
                "must bind to loopback. These services have no authentication; "
                "binding to a routable address exposes an open inference endpoint. "
                "See NFR-S-03.",
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
```

- [ ] **Step 6: Implement `src/contra/config/loader.py`**

```python
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import yaml
from contra.config.models import (
    AudioConfig, Config, ConfigError, DebateConfig, LlmConfig, LoggingConfig,
    SamplingConfig, SttConfig, TtsConfig, UiConfig, VadConfig, WebRtcConfig,
)

__all__ = ["load_config", "ConfigError"]

def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}

def _env_overrides() -> dict[str, Any]:
    """CONTRA_LLM_TIMEOUT_S=45 -> {'llm': {'timeout_s': '45'}}"""
    out: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith("CONTRA_"):
            continue
        parts = key[len("CONTRA_"):].lower().split("_", 1)
        if len(parts) != 2:
            continue
        section, field_name = parts
        out.setdefault(section, {})[field_name] = value
    return out

def _coerce(cls: type, data: dict[str, Any]) -> Any:
    """Build a frozen dataclass, coercing scalars to the annotated types."""
    import dataclasses
    kwargs: dict[str, Any] = {}
    fields = {f.name: f for f in dataclasses.fields(cls)}
    for name, raw in data.items():
        if name not in fields:
            continue
        target = fields[name].type
        if dataclasses.is_dataclass(target) and isinstance(raw, dict):
            kwargs[name] = _coerce(target, raw)
        elif target is bool or target == "bool":
            kwargs[name] = raw if isinstance(raw, bool) else str(raw).lower() == "true"
        elif target is int or target == "int":
            kwargs[name] = int(raw)
        elif target is float or target == "float":
            kwargs[name] = float(raw)
        else:
            kwargs[name] = raw
    return cls(**kwargs)

_SECTIONS: dict[str, type] = {
    "llm": LlmConfig, "audio": AudioConfig, "vad": VadConfig, "stt": SttConfig,
    "tts": TtsConfig, "ui": UiConfig, "debate": DebateConfig, "logging": LoggingConfig,
}

def load_config(config_dir: Path) -> Config:
    merged = _read(config_dir / "default.yaml")
    merged = _deep_merge(merged, _read(config_dir / "user.yaml"))
    merged = _deep_merge(merged, _env_overrides())

    sections: dict[str, Any] = {}
    for name, cls in _SECTIONS.items():
        raw = merged.get(name, {})
        if not isinstance(raw, dict):
            raise ConfigError(name, raw, "a mapping")
        if name == "llm":
            sampling = _coerce(SamplingConfig, raw.get("sampling", {}))
            rest = {k: v for k, v in raw.items() if k != "sampling"}
            sections[name] = _coerce(LlmConfig, rest).__class__(
                **{**{f: getattr(_coerce(LlmConfig, rest), f)
                      for f in ("base_url", "model", "timeout_s",
                                "max_response_tokens", "enable_thinking")},
                   "sampling": sampling}
            )
        elif name == "audio":
            webrtc = _coerce(WebRtcConfig, raw.get("webrtc", {}))
            rest = {k: v for k, v in raw.items() if k != "webrtc"}
            base = _coerce(AudioConfig, rest)
            sections[name] = AudioConfig(
                sample_rate=base.sample_rate, frame_ms=base.frame_ms,
                output_buffer_ms=base.output_buffer_ms, webrtc=webrtc,
            )
        else:
            sections[name] = _coerce(cls, raw)
    return Config(**sections)
```

- [ ] **Step 7: Implement `src/contra/observability/logging.py`**

```python
from __future__ import annotations
import logging
import sys
import structlog

def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout,
                        level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: 3 passed

- [ ] **Step 9: Verify lint and types pass**

```bash
ruff check . && ruff format --check . && mypy src/contra
```
Expected: no errors

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml config/ src/contra/config/ src/contra/observability/ tests/unit/test_config_loader.py
git commit -m "feat(config): typed config loader with loopback invariant and validation"
```

---

## Task 2: Core value types

**Files:**
- Create: `src/contra/audio/types.py`, `src/contra/debate/types.py`
- Test: `tests/unit/test_types.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `AudioFrame(samples: bytes, sample_rate: int, timestamp_ms: float)`
  - `AudioChunk(samples: bytes, text_span: tuple[int,int], duration_ms: float, sequence: int)`
  - `PlaybackPosition(chunks_played: int, samples_played: int, last_complete_span_end: int)`
  - `Message(role: str, content: str)`, `TurnHandle(index: int)`, `Transcript(text: str, confidence: float)`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_types.py
import pytest
from contra.audio.types import AudioChunk, AudioFrame, PlaybackPosition
from contra.debate.types import Message, Transcript, TurnHandle

def test_audio_chunk_is_immutable():
    c = AudioChunk(samples=b"\x00\x01", text_span=(0, 10), duration_ms=20.0, sequence=0)
    with pytest.raises(Exception):
        c.sequence = 5  # type: ignore[misc]

def test_audio_chunk_rejects_inverted_span():
    with pytest.raises(ValueError):
        AudioChunk(samples=b"", text_span=(10, 5), duration_ms=1.0, sequence=0)

def test_playback_position_zero_is_valid():
    p = PlaybackPosition(chunks_played=0, samples_played=0, last_complete_span_end=0)
    assert p.last_complete_span_end == 0

def test_message_roles_constrained():
    assert Message(role="user", content="hi").role == "user"
    with pytest.raises(ValueError):
        Message(role="bot", content="hi")  # type: ignore[arg-type]

def test_audio_frame_duration():
    f = AudioFrame(samples=b"\x00" * 640, sample_rate=16000, timestamp_ms=0.0)
    assert f.duration_ms == pytest.approx(20.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contra.audio'`

- [ ] **Step 3: Implement `src/contra/audio/types.py`**

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class AudioFrame:
    """A fixed-size window of PCM16 mono audio."""
    samples: bytes
    sample_rate: int
    timestamp_ms: float

    @property
    def duration_ms(self) -> float:
        return (len(self.samples) / 2) / self.sample_rate * 1000.0

@dataclass(frozen=True)
class AudioChunk:
    """Synthesised audio plus the span of dispatched text it renders.

    text_span offsets are ABSOLUTE within the agent turn, not relative to the
    sentence. A per-sentence offset makes truncation across multiple chunks
    silently wrong. See internal API spec section D.
    """
    samples: bytes
    text_span: tuple[int, int]
    duration_ms: float
    sequence: int

    def __post_init__(self) -> None:
        start, end = self.text_span
        if start < 0 or end < start:
            raise ValueError(f"invalid text_span {self.text_span}")

@dataclass(frozen=True)
class PlaybackPosition:
    """How far playback actually got. Returned by AudioOutput.clear().

    A partially-played chunk counts as NOT played — under-recording what the
    user heard is far safer than over-recording it (FR-13).
    """
    chunks_played: int
    samples_played: int
    last_complete_span_end: int
```

- [ ] **Step 4: Implement `src/contra/debate/types.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]
_VALID_ROLES = {"system", "user", "assistant"}

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_types.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/contra/audio/types.py src/contra/debate/types.py tests/unit/test_types.py
git commit -m "feat(types): core value types with FR-13 text_span contract"
```

---

## Task 3: ConversationState — the FR-13 component

> **This is the highest-value task in the plan.** FR-13 passes trivially in any non-streaming implementation and fails silently in a streaming one. The symptom appears many turns later as the agent referencing arguments the user never heard. Build it now, before barge-in exists in Phase 2, so the structure is right when barge-in is wired.

**Files:**
- Create: `src/contra/debate/conversation.py`
- Test: `tests/unit/test_conversation_state.py`

**Interfaces:**
- Consumes: `Message`, `TurnHandle` (Task 2); `PlaybackPosition` (Task 2)
- Produces: `ConversationState` with `append_user_turn(str)`, `begin_agent_turn() -> TurnHandle`, `record_dispatched(TurnHandle, str)`, `commit_agent_turn(TurnHandle)`, `truncate_to_spoken(TurnHandle, PlaybackPosition)`, `messages() -> list[Message]`, `token_estimate() -> int`, `set_system_prompt(str)`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_conversation_state.py
import pytest
from contra.audio.types import PlaybackPosition
from contra.debate.conversation import ConversationState

DISPATCHED = (
    "Productivity gains are contested. "        # chars   0-33
    "Remote workers report higher output. "     # chars  33-70
    "But managers report lower collaboration."  # chars  70-110
)

def test_full_turn_records_everything_spoken():
    s = ConversationState()
    s.append_user_turn("Remote work is better.")
    h = s.begin_agent_turn()
    s.record_dispatched(h, DISPATCHED)
    s.commit_agent_turn(h)
    msgs = s.messages()
    assert msgs[-1].role == "assistant"
    assert msgs[-1].content == DISPATCHED.strip()

def test_barge_in_truncates_history_to_spoken_audio():
    """FR-13: history records what was SPOKEN, not what was GENERATED."""
    s = ConversationState()
    s.append_user_turn("Remote work is better.")
    h = s.begin_agent_turn()
    s.record_dispatched(h, DISPATCHED)
    # only the first chunk (sentence 1) fully played
    s.truncate_to_spoken(h, PlaybackPosition(1, 48_000, last_complete_span_end=33))
    content = s.messages()[-1].content
    assert content == "Productivity gains are contested."
    assert "Remote workers" not in content
    assert "managers" not in content

def test_barge_in_before_any_audio_played_records_nothing():
    s = ConversationState()
    s.append_user_turn("Go.")
    h = s.begin_agent_turn()
    s.record_dispatched(h, DISPATCHED)
    s.truncate_to_spoken(h, PlaybackPosition(0, 0, last_complete_span_end=0))
    assert all(m.role != "assistant" for m in s.messages())

def test_truncation_rounds_back_to_word_boundary():
    s = ConversationState()
    h = s.begin_agent_turn()
    s.record_dispatched(h, "Remote workers report higher output.")
    # 27 lands mid-word inside "higher"
    s.truncate_to_spoken(h, PlaybackPosition(1, 100, last_complete_span_end=27))
    assert s.messages()[-1].content == "Remote workers report"

def test_generated_text_is_retained_separately_but_not_in_messages():
    s = ConversationState()
    h = s.begin_agent_turn()
    s.record_dispatched(h, DISPATCHED)
    s.truncate_to_spoken(h, PlaybackPosition(1, 48_000, 33))
    assert s.generated_text(h) == DISPATCHED
    assert s.messages()[-1].content == "Productivity gains are contested."

def test_invariant_i3_spoken_is_always_prefix_of_dispatched():
    """Invariant I-3, asserted directly."""
    s = ConversationState()
    for end in (0, 5, 33, 70, len(DISPATCHED)):
        h = s.begin_agent_turn()
        s.record_dispatched(h, DISPATCHED)
        s.truncate_to_spoken(h, PlaybackPosition(1, 1, end))
        spoken = next((m.content for m in reversed(s.messages())
                       if m.role == "assistant"), "")
        assert DISPATCHED.startswith(spoken.rstrip()), f"not a prefix at end={end}"
        assert len(spoken) <= max(end, 0)

def test_messages_alternate_after_system_block():
    """Invariant I-4."""
    s = ConversationState()
    s.set_system_prompt("You are a debate opponent.")
    for i in range(3):
        s.append_user_turn(f"user {i}")
        h = s.begin_agent_turn()
        s.record_dispatched(h, f"agent {i}")
        s.commit_agent_turn(h)
    roles = [m.role for m in s.messages()]
    assert roles == ["system"] + ["user", "assistant"] * 3

def test_double_commit_raises():
    s = ConversationState()
    h = s.begin_agent_turn()
    s.record_dispatched(h, "text")
    s.commit_agent_turn(h)
    with pytest.raises(ValueError):
        s.commit_agent_turn(h)

def test_token_estimate_grows_with_history():
    s = ConversationState()
    before = s.token_estimate()
    s.append_user_turn("a fairly long user turn with several words in it")
    assert s.token_estimate() > before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_conversation_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contra.debate.conversation'`

- [ ] **Step 3: Implement `src/contra/debate/conversation.py`**

```python
from __future__ import annotations

from contra.audio.types import PlaybackPosition
from contra.debate.types import Message, TurnHandle

__all__ = ["ConversationState"]

def _round_back_to_word(text: str, end: int) -> str:
    """Cut text at `end`, backing up so we never end mid-word.

    Chunks are segmented on punctuation and clause boundaries, so `end` is
    normally already a clean boundary. This is the defensive case.
    """
    if end <= 0:
        return ""
    if end >= len(text):
        return text.rstrip()
    if text[end].isspace() or text[end - 1].isspace():
        return text[:end].rstrip()
    cut = text.rfind(" ", 0, end)
    return "" if cut == -1 else text[:cut].rstrip()

class ConversationState:
    """Holds the debate's memory.

    Three quantities diverge during an agent turn and they are NOT equal:
      generated  >=  dispatched  >=  actually played
    History must record the THIRD (FR-13). Recording the first means the agent
    later says "as I explained" about words the user never heard.
    """

    def __init__(self) -> None:
        self._system: str | None = None
        self._messages: list[Message] = []
        self._dispatched: dict[int, str] = {}
        self._closed: set[int] = set()
        self._next_index = 0

    def set_system_prompt(self, prompt: str) -> None:
        self._system = prompt

    def append_user_turn(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            self._messages.append(Message(role="user", content=cleaned))

    def begin_agent_turn(self) -> TurnHandle:
        handle = TurnHandle(index=self._next_index)
        self._next_index += 1
        self._dispatched[handle.index] = ""
        return handle

    def record_dispatched(self, handle: TurnHandle, text: str) -> None:
        """Record text handed to TTS. Call with the cumulative turn text."""
        self._check_open(handle)
        self._dispatched[handle.index] = text

    def generated_text(self, handle: TurnHandle) -> str:
        return self._dispatched.get(handle.index, "")

    def commit_agent_turn(self, handle: TurnHandle) -> None:
        """Turn completed normally — everything dispatched was spoken."""
        self._check_open(handle)
        self._append_spoken(handle, self._dispatched[handle.index].strip())

    def truncate_to_spoken(self, handle: TurnHandle, position: PlaybackPosition) -> None:
        """Barge-in: record ONLY what actually reached the user's ears (FR-13)."""
        self._check_open(handle)
        dispatched = self._dispatched[handle.index]
        spoken = _round_back_to_word(dispatched, position.last_complete_span_end)
        self._append_spoken(handle, spoken)

    def messages(self) -> list[Message]:
        head = [Message(role="system", content=self._system)] if self._system else []
        return head + list(self._messages)

    def token_estimate(self) -> int:
        """~4 chars per token. Cheap proxy; exact counts need the tokenizer."""
        chars = sum(len(m.content) for m in self.messages())
        return chars // 4

    def _append_spoken(self, handle: TurnHandle, spoken: str) -> None:
        self._closed.add(handle.index)
        if spoken:
            self._messages.append(Message(role="assistant", content=spoken))

    def _check_open(self, handle: TurnHandle) -> None:
        if handle.index not in self._dispatched:
            raise ValueError(f"unknown turn handle {handle.index}")
        if handle.index in self._closed:
            raise ValueError(f"turn {handle.index} is already closed")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_conversation_state.py -v`
Expected: 9 passed

- [ ] **Step 5: Verify strict typing on the core**

Run: `mypy src/contra/debate`
Expected: Success — `debate/` is `strict = true`

- [ ] **Step 6: Verify the import boundary holds**

Run: `ruff check src/contra/debate`
Expected: no `TID251` violations — `debate/` imports no I/O library

- [ ] **Step 7: Commit**

```bash
git add src/contra/debate/conversation.py tests/unit/test_conversation_state.py
git commit -m "feat(debate): ConversationState with FR-13 spoken-history truncation

Invariant I-3 asserted directly: history is always a prefix of dispatched
text and never longer than what actually played."
```

---

## Task 4: SentenceSegmenter

**Files:**
- Create: `src/contra/debate/segmenter.py`
- Test: `tests/unit/test_segmenter.py`

**Interfaces:**
- Consumes: nothing
- Produces: `SentenceSegmenter(min_unit_chars=15, max_unit_chars=200)` with `feed(token: str) -> list[str]` and `flush() -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_segmenter.py
from contra.debate.segmenter import SentenceSegmenter

def feed_all(seg: SentenceSegmenter, text: str) -> list[str]:
    out: list[str] = []
    for ch in text:
        out.extend(seg.feed(ch))
    return out

def test_emits_on_terminal_punctuation_followed_by_space():
    seg = SentenceSegmenter()
    units = feed_all(seg, "Productivity gains are contested. Next one here.")
    assert units == ["Productivity gains are contested."]

def test_short_fragment_is_held_and_merged():
    """Kokoro ONNX is inefficient below ~15 chars (ADR-0006)."""
    seg = SentenceSegmenter()
    units = feed_all(seg, "Hi. That is a much longer sentence here. ")
    assert units == ["Hi. That is a much longer sentence here."]

def test_does_not_split_decimal_numbers():
    seg = SentenceSegmenter()
    units = feed_all(seg, "The figure is 13.5 percent of all workers. ")
    assert units == ["The figure is 13.5 percent of all workers."]

def test_emits_on_clause_break_when_buffer_is_long():
    seg = SentenceSegmenter()
    long_clause = "Remote workers consistently report far higher output levels, "
    units = feed_all(seg, long_clause + "but managers disagree with that entirely.")
    assert len(units) == 1
    assert units[0].endswith(",")

def test_force_emits_at_max_chars():
    seg = SentenceSegmenter(max_unit_chars=60)
    text = "word " * 40
    units = feed_all(seg, text)
    assert units
    assert all(len(u) <= 60 for u in units)

def test_flush_emits_remainder():
    seg = SentenceSegmenter()
    feed_all(seg, "An unterminated trailing sentence")
    assert seg.flush() == ["An unterminated trailing sentence"]

def test_flush_is_idempotent():
    seg = SentenceSegmenter()
    feed_all(seg, "Something here")
    assert seg.flush() == ["Something here"]
    assert seg.flush() == []

def test_no_empty_units_ever_emitted():
    seg = SentenceSegmenter()
    units = feed_all(seg, "  .  ...   ") + seg.flush()
    assert all(u.strip() for u in units)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_segmenter.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/contra/debate/segmenter.py`**

```python
from __future__ import annotations

__all__ = ["SentenceSegmenter"]

TERMINALS = ".!?"
CLAUSE = ",;:"

class SentenceSegmenter:
    """Converts an LLM token stream into TTS-sized speakable units.

    Small component, outsized effect on perceived latency: time-to-first-audio
    depends almost entirely on how quickly unit one is emitted.
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

        # Terminal punctuation, only once we've seen the following whitespace.
        # Waiting for whitespace is what stops "13.5" splitting into "13." + "5".
        for i in range(n - 1):
            if buf[i] in TERMINALS and buf[i + 1].isspace() and (i + 1) >= self._min:
                return i + 1

        if n >= self._clause_threshold:
            for i in range(n - 1):
                if buf[i] in CLAUSE and buf[i + 1].isspace() and (i + 1) >= self._min:
                    return i + 1
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_segmenter.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/contra/debate/segmenter.py tests/unit/test_segmenter.py
git commit -m "feat(debate): sentence segmenter with min-unit rule for Kokoro overhead"
```

---

## Task 5: LlmClient — streaming and real cancellation

**Files:**
- Create: `src/contra/debate/llm_client.py`
- Test: `tests/unit/test_llm_client.py`

**Interfaces:**
- Consumes: `Message` (Task 2), `LlmConfig` (Task 1)
- Produces: `LlmClient(config: LlmConfig, http_client: httpx.AsyncClient | None = None)` with `async stream(messages) -> AsyncIterator[str]`, `async cancel() -> None`, `async health() -> bool`, `async aclose() -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_llm_client.py
import httpx
import pytest
from contra.config.models import LlmConfig
from contra.debate.llm_client import LlmClient
from contra.debate.types import Message

SSE = (
    b'data: {"choices":[{"delta":{"content":"Product"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"content":"ivity"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"content":" gains"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    b"data: [DONE]\n\n"
)

def _mock_client(body: bytes = SSE) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))

async def test_streams_token_deltas_in_order():
    client = LlmClient(LlmConfig(), http_client=_mock_client())
    tokens = [t async for t in client.stream([Message(role="user", content="hi")])]
    assert tokens == ["Product", "ivity", " gains"]
    await client.aclose()

async def test_skips_malformed_frames_without_dying():
    body = (
        b"data: {not json}\n\n"
        b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
        b"data: [DONE]\n\n"
    )
    client = LlmClient(LlmConfig(), http_client=_mock_client(body))
    tokens = [t async for t in client.stream([Message(role="user", content="hi")])]
    assert tokens == ["ok"]
    await client.aclose()

async def test_cancel_stops_iteration():
    client = LlmClient(LlmConfig(), http_client=_mock_client())
    tokens = []
    async for t in client.stream([Message(role="user", content="hi")]):
        tokens.append(t)
        await client.cancel()
    assert tokens == ["Product"]
    await client.aclose()

async def test_request_body_carries_required_params():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured.update(json.loads(request.content))
        return httpx.Response(200, content=SSE,
                              headers={"content-type": "text/event-stream"})

    client = LlmClient(
        LlmConfig(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    async for _ in client.stream([Message(role="user", content="hi")]):
        pass
    assert captured["stream"] is True
    assert captured["presence_penalty"] == 1.5
    assert captured["max_tokens"] == 220
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
    await client.aclose()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/contra/debate/llm_client.py`**

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from contra.config.models import LlmConfig
from contra.debate.types import Message

__all__ = ["LlmClient"]

class LlmClient:
    """Streaming client for llama-server's OpenAI-compatible API.

    Uses httpx directly rather than the openai SDK so that cancel() can abort
    the underlying HTTP request. Merely abandoning the iterator is not enough:
    llama-server keeps generating until the connection closes, occupying the
    slot the NEXT turn needs. The visible symptom is that interrupting the
    agent makes the following response slower.
    """

    def __init__(self, config: LlmConfig, http_client: httpx.AsyncClient | None = None) -> None:
        self._cfg = config
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=config.timeout_s)
        self._cancelled = False
        self._response: httpx.Response | None = None

    def _payload(self, messages: list[Message]) -> dict:
        s = self._cfg.sampling
        return {
            "model": self._cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "temperature": s.temperature,
            "top_p": s.top_p,
            "top_k": s.top_k,
            "min_p": s.min_p,
            "presence_penalty": s.presence_penalty,
            "repeat_penalty": s.repeat_penalty,
            "max_tokens": self._cfg.max_response_tokens,
            "chat_template_kwargs": {"enable_thinking": self._cfg.enable_thinking},
        }

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        self._cancelled = False
        url = f"{self._cfg.base_url.rstrip('/')}/chat/completions"
        async with self._http.stream("POST", url, json=self._payload(messages)) as response:
            self._response = response
            response.raise_for_status()
            async for line in response.aiter_lines():
                if self._cancelled:
                    break
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue  # malformed frame: skip, keep going
                choices = parsed.get("choices") or []
                if not choices:
                    continue
                content = (choices[0].get("delta") or {}).get("content")
                if content:
                    yield content
        self._response = None

    async def cancel(self) -> None:
        """Abort generation. Must close the connection, not just stop reading."""
        self._cancelled = True
        if self._response is not None:
            await self._response.aclose()
            self._response = None

    async def health(self) -> bool:
        root = self._cfg.base_url.rstrip("/").removesuffix("/v1")
        try:
            r = await self._http.get(f"{root}/health", timeout=2.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/contra/debate/llm_client.py tests/unit/test_llm_client.py
git commit -m "feat(debate): streaming llama-server client with connection-closing cancel"
```

---

## Task 6: FastAPI server with WebRTC signalling

**Files:**
- Create: `src/contra/ui/server.py`, `src/contra/audio/interfaces.py`
- Test: `tests/unit/test_server_routes.py`

**Interfaces:**
- Consumes: `Config` (Task 1)
- Produces: `create_app(config, on_offer) -> FastAPI` where `on_offer(sdp: str, sdp_type: str) -> dict[str, str]` returns `{"sdp": ..., "type": "answer"}`; protocols `AudioInput`, `AudioOutput`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_server_routes.py
from fastapi.testclient import TestClient
from contra.config.models import Config
from contra.ui.server import create_app

async def fake_on_offer(sdp: str, sdp_type: str) -> dict[str, str]:
    return {"sdp": "v=0\r\nfake-answer", "type": "answer"}

def test_health_returns_ok():
    client = TestClient(create_app(Config(), fake_on_offer))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_offer_returns_answer():
    client = TestClient(create_app(Config(), fake_on_offer))
    r = client.post("/api/webrtc/offer", json={"sdp": "v=0\r\n", "type": "offer"})
    assert r.status_code == 200
    assert r.json()["type"] == "answer"

def test_offer_rejects_missing_sdp():
    client = TestClient(create_app(Config(), fake_on_offer))
    assert client.post("/api/webrtc/offer", json={"type": "offer"}).status_code == 422

def test_index_is_served():
    client = TestClient(create_app(Config(), fake_on_offer))
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_server_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contra.ui'`

- [ ] **Step 3: Implement `src/contra/audio/interfaces.py`**

```python
from __future__ import annotations
from collections.abc import AsyncIterator
from typing import Protocol

from contra.audio.types import AudioChunk, AudioFrame, PlaybackPosition

class AudioInput(Protocol):
    def frames(self) -> AsyncIterator[AudioFrame]: ...

class AudioOutput(Protocol):
    async def enqueue(self, chunk: AudioChunk) -> None: ...
    def clear(self) -> PlaybackPosition: ...
    @property
    def is_playing(self) -> bool: ...
```

- [ ] **Step 4: Implement `src/contra/ui/server.py`**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from contra.config.models import Config

STATIC_DIR = Path(__file__).parent / "static"

class Offer(BaseModel):
    sdp: str
    type: str

OnOffer = Callable[[str, str], Awaitable[dict[str, str]]]

def create_app(config: Config, on_offer: OnOffer) -> FastAPI:
    app = FastAPI(title="Contra", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/webrtc/offer")
    async def webrtc_offer(offer: Offer) -> dict[str, str]:
        return await on_offer(offer.sdp, offer.type)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
```

- [ ] **Step 5: Create a placeholder `src/contra/ui/static/index.html`**

Task 7 replaces this. It exists now so the route test passes.

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Contra</title></head>
<body><p>Placeholder — replaced in Task 7.</p></body></html>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_server_routes.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add src/contra/ui/ src/contra/audio/interfaces.py tests/unit/test_server_routes.py
git commit -m "feat(ui): FastAPI server with WebRTC signalling endpoint"
```

---

## Task 7: Browser page — getUserMedia with AEC, WebRTC both directions

> **The critical detail:** agent audio must be **played by the browser**, not by Python. Chrome's AEC3 can only cancel audio it is itself rendering. If Python played TTS through the system device, the browser would have no reference signal, AEC would be inert, and the agent would hear itself.

**Files:**
- Create: `src/contra/ui/static/index.html`, `src/contra/ui/static/app.js`
- Test: Manual — see Step 4

**Interfaces:**
- Consumes: `POST /api/webrtc/offer` (Task 6)
- Produces: a page that publishes one mic track and plays one inbound track

- [ ] **Step 1: Write `src/contra/ui/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Contra</title>
  <style>
    :root { color-scheme: light dark; }
    body { font: 15px/1.5 system-ui, sans-serif; max-width: 40rem;
           margin: 3rem auto; padding: 0 1rem; }
    #state { font-size: 1.1rem; font-weight: 600; padding: .5rem .9rem;
             border-radius: .4rem; display: inline-block;
             background: #8883; }
    #log { margin-top: 1.5rem; white-space: pre-wrap; font-family: ui-monospace,
           monospace; font-size: 13px; opacity: .85; }
    button { font: inherit; padding: .5rem 1rem; border-radius: .4rem; }
  </style>
</head>
<body>
  <h1>Contra</h1>
  <p><button id="start">Start session</button></p>
  <p>State: <span id="state">idle</span></p>
  <!-- Inbound agent audio MUST play here so Chrome's AEC has a reference signal -->
  <audio id="agent" autoplay></audio>
  <div id="log"></div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `src/contra/ui/static/app.js`**

```javascript
// Audio never touches UI state. The RTCPeerConnection and the <audio> element
// live entirely outside any rendering logic.
const startBtn = document.getElementById("start");
const stateEl  = document.getElementById("state");
const agentEl  = document.getElementById("agent");
const logEl    = document.getElementById("log");

function log(msg) {
  logEl.textContent += `${new Date().toLocaleTimeString()}  ${msg}\n`;
}
function setState(s) { stateEl.textContent = s; }

let pc = null;

async function start() {
  startBtn.disabled = true;
  setState("connecting");

  // Echo cancellation is MANDATORY — the user is on speakers (ADR-0012).
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
      sampleRate: 16000,
    },
    video: false,
  });

  const track = stream.getAudioTracks()[0];
  log(`mic: ${track.label}`);
  const settings = track.getSettings();
  log(`AEC=${settings.echoCancellation} NS=${settings.noiseSuppression} AGC=${settings.autoGainControl}`);
  if (settings.echoCancellation === false) {
    log("WARNING: echo cancellation is OFF — the agent will hear itself.");
  }

  pc = new RTCPeerConnection({ iceServers: [] });  // local only, no STUN needed
  pc.addTrack(track, stream);
  pc.addTransceiver("audio", { direction: "sendrecv" });

  pc.ontrack = (ev) => {
    log("inbound agent track attached");
    agentEl.srcObject = ev.streams[0];
  };
  pc.onconnectionstatechange = () => {
    log(`pc: ${pc.connectionState}`);
    if (pc.connectionState === "connected") setState("listening");
    if (["failed", "closed", "disconnected"].includes(pc.connectionState)) {
      setState("disconnected");
      startBtn.disabled = false;
    }
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await iceComplete(pc);

  const res = await fetch("/api/webrtc/offer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sdp: pc.localDescription.sdp,
      type: pc.localDescription.type,
    }),
  });
  const answer = await res.json();
  await pc.setRemoteDescription(answer);
  log("answer applied");
}

// Wait for ICE gathering so we can send a single complete offer (no trickle).
function iceComplete(pc) {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const check = () => {
      if (pc.iceGatheringState === "complete") {
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", check);
  });
}

startBtn.addEventListener("click", () => start().catch((e) => {
  log(`ERROR: ${e.message}`);
  setState("error");
  startBtn.disabled = false;
}));
```

- [ ] **Step 3: Verify the page loads and requests mic permission**

Run the server standalone with a stub offer handler:

```bash
python -c "
import uvicorn
from contra.config.models import Config
from contra.ui.server import create_app
async def stub(sdp, t): return {'sdp': '', 'type': 'answer'}
uvicorn.run(create_app(Config(), stub), host='127.0.0.1', port=8000)
"
```

Open `http://127.0.0.1:8000`, click **Start session**.
Expected: browser prompts for microphone permission; log shows `AEC=true NS=true AGC=true`.

- [ ] **Step 4: Manual verification checklist**

- [ ] Page loads at `127.0.0.1:8000`
- [ ] Mic permission prompt appears
- [ ] Log line reports `AEC=true` — if `false`, stop and investigate before continuing
- [ ] No console errors

- [ ] **Step 5: Commit**

```bash
git add src/contra/ui/static/
git commit -m "feat(ui): browser page with getUserMedia AEC and WebRTC offer flow"
```

---

## Task 8: aiortc transport implementing AudioInput/AudioOutput

> **Phase 0 gate.** Before starting: confirm `benchmarks/results/` contains BM-01, BM-03 and BM-05 results, and that each is PASS or has a documented response. If BM-03 reports dropped audio frames > 0, stop — the GIL is not releasing and this task needs subprocess isolation first.

**Files:**
- Create: `src/contra/audio/resample.py`, `src/contra/audio/webrtc_transport.py`
- Test: `tests/unit/test_webrtc_output_track.py`

**Interfaces:**
- Consumes: `AudioFrame`, `AudioChunk`, `PlaybackPosition` (Task 2); `AudioInput`, `AudioOutput` (Task 6)
- Produces: `WebRtcTransport(sample_rate=16000, frame_ms=20)` with `async handle_offer(sdp, type) -> dict`, `frames() -> AsyncIterator[AudioFrame]`, `async enqueue(chunk)`, `clear() -> PlaybackPosition`, `is_playing`, `async close()`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_webrtc_output_track.py
import pytest
from contra.audio.types import AudioChunk, PlaybackPosition
from contra.audio.webrtc_transport import PlaybackQueue

def chunk(seq: int, span: tuple[int, int], samples: int = 480) -> AudioChunk:
    return AudioChunk(samples=b"\x00\x00" * samples, text_span=span,
                      duration_ms=samples / 24.0, sequence=seq)

async def test_clear_reports_zero_when_nothing_played():
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 33)))
    pos = q.clear()
    assert pos.chunks_played == 0
    assert pos.last_complete_span_end == 0

async def test_fully_consumed_chunk_advances_span_end():
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 33), samples=480))
    for _ in range(1000):
        if not await q.read(960):
            break
    pos = q.clear()
    assert pos.chunks_played == 1
    assert pos.last_complete_span_end == 33

async def test_partially_played_chunk_does_not_count():
    """Conservative by design: under-recording is safer than over-recording."""
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 33), samples=2400))
    await q.read(480)  # consume only part of it
    pos = q.clear()
    assert pos.chunks_played == 0
    assert pos.last_complete_span_end == 0

async def test_clear_discards_queued_chunks():
    q = PlaybackQueue()
    await q.put(chunk(0, (0, 10)))
    await q.put(chunk(1, (10, 20)))
    q.clear()
    assert not q.is_playing
    assert await q.read(480) == b""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_webrtc_output_track.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/contra/audio/resample.py`**

```python
from __future__ import annotations
import av
import numpy as np

def frame_to_pcm16_mono(frame: av.AudioFrame, target_rate: int) -> bytes:
    """Resample an inbound WebRTC frame to mono PCM16 at target_rate."""
    resampler = av.audio.resampler.AudioResampler(
        format="s16", layout="mono", rate=target_rate
    )
    out = b""
    for resampled in resampler.resample(frame):
        out += bytes(resampled.planes[0])
    return out

def pcm16_to_frame(pcm: bytes, rate: int, pts: int) -> av.AudioFrame:
    """Wrap mono PCM16 bytes in an av.AudioFrame for outbound WebRTC."""
    samples = np.frombuffer(pcm, dtype=np.int16).reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
    frame.sample_rate = rate
    frame.pts = pts
    frame.time_base = __import__("fractions").Fraction(1, rate)
    return frame
```

- [ ] **Step 4: Implement `src/contra/audio/webrtc_transport.py`**

```python
from __future__ import annotations

import asyncio
import fractions
from collections import deque
from collections.abc import AsyncIterator

import av
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription

from contra.audio.resample import frame_to_pcm16_mono, pcm16_to_frame
from contra.audio.types import AudioChunk, AudioFrame, PlaybackPosition
from contra.observability.logging import get_logger

log = get_logger(__name__)

OUTPUT_RATE = 48_000          # WebRTC standard
OUTPUT_FRAME_SAMPLES = 960    # 20 ms at 48 kHz

class PlaybackQueue:
    """Byte queue of synthesised audio that tracks what was actually consumed.

    The span bookkeeping here is what makes FR-13 possible: clear() reports how
    far playback got, and a partially-consumed chunk deliberately does NOT count.
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
            remaining = self._current.samples[self._offset:]
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
        self._pts = 0
        self._resampler = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=OUTPUT_RATE
        )

    async def recv(self) -> av.AudioFrame:
        # Pace to real time: one 20 ms frame per 20 ms.
        await asyncio.sleep(0.02)
        need = int(self._source_rate * 0.02)
        pcm = await self._queue.read(need)
        if len(pcm) < need * 2:
            pcm += b"\x00" * (need * 2 - len(pcm))
        src = pcm16_to_frame(pcm, self._source_rate, self._pts)
        self._pts += need
        resampled = self._resampler.resample(src)
        frame = resampled[0]
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, OUTPUT_RATE)
        return frame

class WebRtcTransport:
    """Implements AudioInput and AudioOutput over a browser peer connection."""

    def __init__(self, sample_rate: int = 16_000, frame_ms: int = 20,
                 tts_rate: int = 24_000) -> None:
        self._sample_rate = sample_rate
        self._frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self._pc: RTCPeerConnection | None = None
        self._inbound: asyncio.Queue[AudioFrame] = asyncio.Queue(maxsize=200)
        self._queue = PlaybackQueue()
        self._tts_rate = tts_rate
        self._reader_task: asyncio.Task | None = None

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
        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def _read_track(self, track: MediaStreamTrack) -> None:
        buf = b""
        ts = 0.0
        try:
            while True:
                av_frame = await track.recv()
                buf += frame_to_pcm16_mono(av_frame, self._sample_rate)
                while len(buf) >= self._frame_bytes:
                    piece, buf = buf[: self._frame_bytes], buf[self._frame_bytes:]
                    frame = AudioFrame(samples=piece, sample_rate=self._sample_rate,
                                       timestamp_ms=ts)
                    ts += frame.duration_ms
                    try:
                        self._inbound.put_nowait(frame)
                    except asyncio.QueueFull:
                        log.warning("inbound_queue_full_dropping_frame")
        except Exception as exc:  # track ended
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
        if self._reader_task:
            self._reader_task.cancel()
        if self._pc:
            await self._pc.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_webrtc_output_track.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/contra/audio/resample.py src/contra/audio/webrtc_transport.py tests/unit/test_webrtc_output_track.py
git commit -m "feat(audio): aiortc transport with span-tracking playback queue"
```

---

## Task 9: Silero VAD via onnxruntime

> **Not the `silero-vad` pip package** — it pulls in PyTorch (~200 MB CPU-only, far more with CUDA). We use the ONNX model directly, consistent with Parakeet and Kokoro, keeping torch out of the dependency tree entirely.

**Files:**
- Create: `src/contra/detect/interfaces.py`, `src/contra/detect/silero_vad.py`
- Test: `tests/unit/test_vad_windowing.py`, `tests/integration/test_silero_vad.py`

**Interfaces:**
- Consumes: `AudioFrame` (Task 2)
- Produces: `VadEvent` enum (`SPEECH_START`, `SPEECH_CONTINUE`, `SILENCE`, `SILENCE_SUSTAINED`); `SileroVad(model_path, threshold, silence_confirm_ms)` with `process(frame: AudioFrame) -> VadEvent`, `reset()`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_vad_windowing.py
from contra.audio.types import AudioFrame
from contra.detect.silero_vad import WindowAccumulator

def frame(n_samples: int) -> AudioFrame:
    return AudioFrame(samples=b"\x00\x00" * n_samples, sample_rate=16000, timestamp_ms=0)

def test_accumulates_20ms_frames_into_512_sample_windows():
    """Silero v5 requires EXACTLY 512 samples at 16 kHz; our frames are 320."""
    acc = WindowAccumulator(window_samples=512)
    assert acc.push(frame(320)) == []          # 320 < 512
    windows = acc.push(frame(320))             # 640 >= 512
    assert len(windows) == 1
    assert len(windows[0]) == 512

def test_leftover_carries_to_next_window():
    acc = WindowAccumulator(window_samples=512)
    acc.push(frame(320))
    acc.push(frame(320))                       # 128 left over
    windows = acc.push(frame(320))             # 128 + 320 = 448, still short
    assert windows == []
    windows = acc.push(frame(320))             # 768 -> one window
    assert len(windows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_vad_windowing.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/contra/detect/interfaces.py`**

```python
from __future__ import annotations
from enum import Enum
from typing import Protocol

from contra.audio.types import AudioFrame

class VadEvent(Enum):
    SPEECH_START = "speech_start"
    SPEECH_CONTINUE = "speech_continue"
    SILENCE = "silence"
    SILENCE_SUSTAINED = "silence_sustained"

class VadStage(Protocol):
    def process(self, frame: AudioFrame) -> VadEvent: ...
    def reset(self) -> None: ...
```

- [ ] **Step 4: Implement `src/contra/detect/silero_vad.py`**

```python
from __future__ import annotations

import numpy as np
import onnxruntime as ort

from contra.audio.types import AudioFrame
from contra.detect.interfaces import VadEvent

WINDOW_SAMPLES = 512   # Silero v5 requires exactly this at 16 kHz

class WindowAccumulator:
    """Buffers variable-size frames into fixed-size windows."""

    def __init__(self, window_samples: int = WINDOW_SAMPLES) -> None:
        self._window = window_samples
        self._buf = np.zeros(0, dtype=np.float32)

    def push(self, frame: AudioFrame) -> list[np.ndarray]:
        pcm = np.frombuffer(frame.samples, dtype=np.int16).astype(np.float32) / 32768.0
        self._buf = np.concatenate([self._buf, pcm])
        out: list[np.ndarray] = []
        while len(self._buf) >= self._window:
            out.append(self._buf[: self._window])
            self._buf = self._buf[self._window:]
        return out

    def reset(self) -> None:
        self._buf = np.zeros(0, dtype=np.float32)

class SileroVad:
    """Answers 'is sound happening', never 'is this person finished'.

    Widening this component's remit is the classic voice-agent mistake. Turn
    commitment belongs to the turn detector (Phase 2) — in Phase 1 it is a
    fixed timer in the session loop.
    """

    def __init__(self, model_path: str, threshold: float = 0.5,
                 silence_confirm_ms: int = 800, sample_rate: int = 16_000) -> None:
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._sess = ort.InferenceSession(model_path, sess_options=opts,
                                          providers=["CPUExecutionProvider"])
        self._threshold = threshold
        self._silence_confirm_ms = silence_confirm_ms
        self._sample_rate = sample_rate
        self._acc = WindowAccumulator()
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._speaking = False
        self._silence_ms = 0.0

    def process(self, frame: AudioFrame) -> VadEvent:
        windows = self._acc.push(frame)
        if not windows:
            return VadEvent.SPEECH_CONTINUE if self._speaking else VadEvent.SILENCE

        prob = 0.0
        for window in windows:
            out, self._state = self._sess.run(
                None,
                {
                    "input": window.reshape(1, -1),
                    "state": self._state,
                    "sr": np.array(self._sample_rate, dtype=np.int64),
                },
            )
            prob = max(prob, float(out[0][0]))

        window_ms = len(windows) * WINDOW_SAMPLES / self._sample_rate * 1000.0
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
```

- [ ] **Step 5: Verify the ONNX signature matches**

The input names above (`input`, `state`, `sr`) and the `[2,1,128]` state shape are for **Silero VAD v5**. Confirm against the downloaded model before trusting them:

```bash
python -c "
import onnxruntime as ort
s = ort.InferenceSession('models/silero_vad.onnx')
print('inputs :', [(i.name, i.shape) for i in s.get_inputs()])
print('outputs:', [(o.name, o.shape) for o in s.get_outputs()])
"
```
Expected: inputs `input [B,N]`, `state [2,B,128]`, `sr` scalar. **If they differ, fix `silero_vad.py` to match** — do not proceed on assumption.

- [ ] **Step 6: Write the integration test**

```python
# tests/integration/test_silero_vad.py
import numpy as np
import pytest
from contra.audio.types import AudioFrame
from contra.detect.interfaces import VadEvent
from contra.detect.silero_vad import SileroVad

pytestmark = pytest.mark.slow

def frames_from(pcm: np.ndarray, frame_samples: int = 320):
    for i in range(0, len(pcm) - frame_samples, frame_samples):
        yield AudioFrame(samples=pcm[i:i + frame_samples].tobytes(),
                         sample_rate=16000, timestamp_ms=0)

def test_silence_never_reports_speech_start():
    vad = SileroVad("models/silero_vad.onnx")
    silence = np.zeros(16000, dtype=np.int16)
    events = [vad.process(f) for f in frames_from(silence)]
    assert VadEvent.SPEECH_START not in events

def test_tone_burst_reports_speech_start():
    vad = SileroVad("models/silero_vad.onnx")
    t = np.linspace(0, 1, 16000, endpoint=False)
    tone = (np.sin(2 * np.pi * 220 * t) * 12000).astype(np.int16)
    events = [vad.process(f) for f in frames_from(tone)]
    assert VadEvent.SPEECH_START in events or VadEvent.SPEECH_CONTINUE in events
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/test_vad_windowing.py -v && pytest tests/integration/test_silero_vad.py -v -m slow`
Expected: unit 2 passed; integration 2 passed

- [ ] **Step 8: Commit**

```bash
git add src/contra/detect/ tests/unit/test_vad_windowing.py tests/integration/test_silero_vad.py
git commit -m "feat(detect): Silero VAD v5 via onnxruntime, no torch dependency"
```

---

## Task 10: Parakeet STT

**Files:**
- Create: `src/contra/speech/interfaces.py`, `src/contra/speech/parakeet_stt.py`
- Test: `tests/integration/test_parakeet_stt.py`, fixture `tests/fixtures/audio/silence.wav`

**Interfaces:**
- Consumes: `AudioFrame` (Task 2), `Transcript` (Task 2), `SttConfig` (Task 1)
- Produces: `SttStage` protocol; `ParakeetStt(config)` with `feed(frame)`, `async finalise() -> Transcript`, `reset()`

- [ ] **Step 1: Create the `silence.wav` fixture**

> This fixture verifies NFR-A-02 — the single property that decided [ADR-0005](../../02-architecture/adr/0005-parakeet-tdt-for-stt.md). Whisper-family models hallucinate "Thank you for watching!" into dead air; in a debate with thinking pauses that phantom text enters the argument history. It is **force-included past `.gitignore`**, because a test whose fixture is ignored silently stops existing on a fresh clone.

```bash
python -c "
import numpy as np, soundfile as sf, pathlib
pathlib.Path('tests/fixtures/audio').mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(0)
room_tone = (rng.normal(0, 1, 16000*10) * 20).astype(np.int16)
sf.write('tests/fixtures/audio/silence.wav', room_tone, 16000, subtype='PCM_16')
print('written')
"
git add -f tests/fixtures/audio/silence.wav
```

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/test_parakeet_stt.py
import numpy as np
import pytest
import soundfile as sf
from contra.audio.types import AudioFrame
from contra.config.models import SttConfig
from contra.speech.parakeet_stt import ParakeetStt

pytestmark = pytest.mark.slow

def feed_wav(stt: ParakeetStt, path: str) -> None:
    pcm, sr = sf.read(path, dtype="int16")
    assert sr == 16000
    for i in range(0, len(pcm) - 320, 320):
        stt.feed(AudioFrame(samples=pcm[i:i + 320].tobytes(),
                            sample_rate=16000, timestamp_ms=0))

async def test_silence_produces_empty_transcript():
    """NFR-A-02 — the reason Parakeet was chosen over Whisper."""
    stt = ParakeetStt(SttConfig())
    feed_wav(stt, "tests/fixtures/audio/silence.wav")
    result = await stt.finalise()
    assert result.text.strip() == "", f"hallucinated on silence: {result.text!r}"

async def test_reset_clears_buffered_audio():
    stt = ParakeetStt(SttConfig())
    feed_wav(stt, "tests/fixtures/audio/silence.wav")
    stt.reset()
    result = await stt.finalise()
    assert result.text.strip() == ""
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/integration/test_parakeet_stt.py -v -m slow`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement `src/contra/speech/interfaces.py`**

```python
from __future__ import annotations
from collections.abc import AsyncIterator
from typing import Protocol

from contra.audio.types import AudioChunk, AudioFrame
from contra.debate.types import Transcript

class SttStage(Protocol):
    def feed(self, frame: AudioFrame) -> None: ...
    async def finalise(self) -> Transcript: ...
    def reset(self) -> None: ...

class TtsStage(Protocol):
    def synthesise(self, text: str, span: tuple[int, int],
                   sequence: int) -> AsyncIterator[AudioChunk]: ...
    def cancel(self) -> None: ...
```

- [ ] **Step 5: Implement `src/contra/speech/parakeet_stt.py`**

```python
from __future__ import annotations

import asyncio

import numpy as np
import onnx_asr

from contra.audio.types import AudioFrame
from contra.config.models import SttConfig
from contra.debate.types import Transcript
from contra.observability.logging import get_logger

log = get_logger(__name__)

class ParakeetStt:
    """Parakeet TDT 0.6B v3 via onnx-asr — no PyTorch, no NeMo, no transformers.

    Not a streaming model: we transcribe a complete utterance on VAD boundaries
    rather than word-by-word. Fine for turn-based debate (ADR-0005).
    """

    def __init__(self, config: SttConfig) -> None:
        self._model = onnx_asr.load_model(config.model_dir)
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
        log.info("stt_finalised", chars=len(text), samples=len(waveform))
        return Transcript(text=(text or "").strip(), confidence=1.0)

    def reset(self) -> None:
        self._buf.clear()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/integration/test_parakeet_stt.py -v -m slow`
Expected: 2 passed

> If `test_silence_produces_empty_transcript` **fails**, stop. Either the model is misconfigured or Parakeet is behaving unexpectedly on this input. Do not proceed — this is the property the STT choice rests on.

- [ ] **Step 7: Commit**

```bash
git add src/contra/speech/interfaces.py src/contra/speech/parakeet_stt.py tests/integration/test_parakeet_stt.py
git add -f tests/fixtures/audio/silence.wav
git commit -m "feat(speech): Parakeet TDT STT with silence-hallucination fixture (NFR-A-02)"
```

---

## Task 11: Kokoro TTS

**Files:**
- Create: `src/contra/speech/kokoro_tts.py`
- Test: `tests/integration/test_kokoro_tts.py`

**Interfaces:**
- Consumes: `AudioChunk` (Task 2), `TtsConfig` (Task 1), `TtsStage` protocol (Task 10)
- Produces: `KokoroTts(config)` with `synthesise(text, span, sequence) -> AsyncIterator[AudioChunk]`, `cancel()`, `sample_rate` property (24000)

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_kokoro_tts.py
import pytest
from contra.config.models import TtsConfig
from contra.speech.kokoro_tts import KokoroTts

pytestmark = pytest.mark.slow

async def test_synthesises_audio_with_correct_span():
    tts = KokoroTts(TtsConfig())
    chunks = [c async for c in tts.synthesise(
        "Productivity gains are contested.", span=(0, 33), sequence=0)]
    assert chunks
    assert chunks[0].text_span == (0, 33)
    assert len(chunks[0].samples) > 0
    assert tts.sample_rate == 24000

async def test_empty_text_yields_nothing():
    tts = KokoroTts(TtsConfig())
    chunks = [c async for c in tts.synthesise("   ", span=(0, 3), sequence=0)]
    assert chunks == []

async def test_short_unit_still_produces_audio():
    """ADR-0006 notes ONNX Kokoro is slow on short text; it must still work."""
    tts = KokoroTts(TtsConfig())
    chunks = [c async for c in tts.synthesise("Right, so.", span=(0, 10), sequence=0)]
    assert chunks and len(chunks[0].samples) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_kokoro_tts.py -v -m slow`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/contra/speech/kokoro_tts.py`**

```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np
from kokoro_onnx import Kokoro

from contra.audio.types import AudioChunk
from contra.config.models import TtsConfig
from contra.observability.logging import get_logger

log = get_logger(__name__)

KOKORO_RATE = 24_000

class KokoroTts:
    """Kokoro-82M via kokoro-onnx, CPU-resident.

    Known caveat (ADR-0006): ONNX has higher per-call overhead than PyTorch and
    is relatively slower on very short inputs. The SentenceSegmenter's 15-char
    minimum exists to stop us paying that cost on three-word fragments.
    """

    def __init__(self, config: TtsConfig) -> None:
        self._kokoro = Kokoro(config.model_path, config.voices_path)
        self._voice = config.voice
        self._speed = config.speed
        self._cancelled = False

    @property
    def sample_rate(self) -> int:
        return KOKORO_RATE

    async def synthesise(self, text: str, span: tuple[int, int],
                         sequence: int) -> AsyncIterator[AudioChunk]:
        self._cancelled = False
        cleaned = text.strip()
        if not cleaned:
            return
        samples, rate = await asyncio.to_thread(
            self._kokoro.create, cleaned, self._voice, self._speed, "en-us"
        )
        if self._cancelled:
            return
        pcm16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        duration_ms = len(pcm16) / rate * 1000.0
        log.info("tts_synthesised", chars=len(cleaned), duration_ms=round(duration_ms))
        yield AudioChunk(samples=pcm16.tobytes(), text_span=span,
                         duration_ms=duration_ms, sequence=sequence)

    def cancel(self) -> None:
        self._cancelled = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_kokoro_tts.py -v -m slow`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/contra/speech/kokoro_tts.py tests/integration/test_kokoro_tts.py
git commit -m "feat(speech): Kokoro-82M TTS emitting span-tagged audio chunks"
```

---

## Task 12: Session orchestrator and composition root

> Phase 1 uses a **fixed 800 ms silence timer**, not semantic turn detection. Smart Turn v2 is Phase 2. Barge-in is Phase 2. This loop deliberately does the simplest thing that produces a spoken reply.

**Files:**
- Create: `src/contra/debate/session.py`, `src/contra/app.py`, `src/contra/__main__.py`
- Test: `tests/unit/test_session_loop.py`

**Interfaces:**
- Consumes: everything from Tasks 1–11
- Produces: `SessionState` enum; `Session(...)` with `async run()`, `state` property; `build_app(config) -> tuple[FastAPI, WebRtcTransport]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_session_loop.py
import asyncio
from collections.abc import AsyncIterator

from contra.audio.types import AudioChunk, AudioFrame, PlaybackPosition
from contra.debate.session import Session, SessionState
from contra.debate.types import Transcript

class FakeVad:
    """Reports speech for N frames, then sustained silence."""
    def __init__(self, speech_frames: int) -> None:
        self._left = speech_frames
        self._fired = False
    def process(self, frame):
        from contra.detect.interfaces import VadEvent
        if self._left > 0:
            self._left -= 1
            if not self._fired:
                self._fired = True
                return VadEvent.SPEECH_START
            return VadEvent.SPEECH_CONTINUE
        return VadEvent.SILENCE_SUSTAINED
    def reset(self): pass

class FakeStt:
    def __init__(self): self.fed = 0
    def feed(self, frame): self.fed += 1
    async def finalise(self): return Transcript(text="Remote work is better.")
    def reset(self): self.fed = 0

class FakeLlm:
    def __init__(self): self.cancelled = False
    async def stream(self, messages) -> AsyncIterator[str]:
        for tok in ["Productivity", " gains", " are", " contested.", " "]:
            yield tok
    async def cancel(self): self.cancelled = True

class FakeTts:
    async def synthesise(self, text, span, sequence) -> AsyncIterator[AudioChunk]:
        yield AudioChunk(samples=b"\x00\x00" * 240, text_span=span,
                         duration_ms=10.0, sequence=sequence)
    def cancel(self): pass
    @property
    def sample_rate(self): return 24000

class FakeOutput:
    def __init__(self): self.chunks = []
    async def enqueue(self, chunk): self.chunks.append(chunk)
    def clear(self): return PlaybackPosition(0, 0, 0)
    def reset_turn(self): pass
    @property
    def is_playing(self): return False

class FakeInput:
    def __init__(self, n): self._n = n
    async def frames(self) -> AsyncIterator[AudioFrame]:
        for _ in range(self._n):
            yield AudioFrame(samples=b"\x00\x00" * 320, sample_rate=16000, timestamp_ms=0)
            await asyncio.sleep(0)

async def test_one_turn_produces_audio_and_history():
    out = FakeOutput()
    session = Session(
        audio_in=FakeInput(6), audio_out=out, vad=FakeVad(3),
        stt=FakeStt(), llm=FakeLlm(), tts=FakeTts(),
        system_prompt="You argue the other side.",
    )
    await asyncio.wait_for(session.run(), timeout=5.0)
    assert out.chunks, "no audio was produced"
    msgs = session.state_store.messages()
    assert msgs[0].role == "system"
    assert msgs[1].role == "user"
    assert msgs[2].role == "assistant"
    assert "Productivity" in msgs[2].content

async def test_agent_turn_text_matches_what_was_enqueued():
    out = FakeOutput()
    session = Session(
        audio_in=FakeInput(6), audio_out=out, vad=FakeVad(3),
        stt=FakeStt(), llm=FakeLlm(), tts=FakeTts(), system_prompt="x",
    )
    await asyncio.wait_for(session.run(), timeout=5.0)
    spoken = session.state_store.messages()[-1].content
    max_span_end = max(c.text_span[1] for c in out.chunks)
    assert len(spoken) <= max_span_end

async def test_state_returns_to_listening_after_turn():
    session = Session(
        audio_in=FakeInput(6), audio_out=FakeOutput(), vad=FakeVad(3),
        stt=FakeStt(), llm=FakeLlm(), tts=FakeTts(), system_prompt="x",
    )
    await asyncio.wait_for(session.run(), timeout=5.0)
    assert session.state in (SessionState.LISTENING, SessionState.ENDED)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_session_loop.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/contra/debate/session.py`**

```python
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

    Deliberately omitted (Phase 2): semantic turn detection, barge-in,
    persistence, the real debate persona, error recovery.
    """

    def __init__(self, audio_in: Any, audio_out: Any, vad: Any, stt: Any,
                 llm: Any, tts: Any, system_prompt: str,
                 min_unit_chars: int = 15, max_unit_chars: int = 200) -> None:
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

    async def run(self) -> None:
        from contra.detect.interfaces import VadEvent

        self.state = SessionState.LISTENING
        heard_speech = False

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

        async for token in self._llm.stream(self.state_store.messages()):
            for unit in segmenter.feed(token):
                span = (len(dispatched), len(dispatched) + len(unit))
                dispatched = f"{dispatched}{unit} "
                self.state_store.record_dispatched(handle, dispatched)
                async for chunk in self._tts.synthesise(unit, span, sequence):
                    await self._out.enqueue(chunk)
                    if first_audio_ms is None:
                        first_audio_ms = (time.perf_counter() - started) * 1000
                        self.state = SessionState.SPEAKING
                sequence += 1

        for unit in segmenter.flush():
            span = (len(dispatched), len(dispatched) + len(unit))
            dispatched = f"{dispatched}{unit} "
            self.state_store.record_dispatched(handle, dispatched)
            async for chunk in self._tts.synthesise(unit, span, sequence):
                await self._out.enqueue(chunk)
                if first_audio_ms is None:
                    first_audio_ms = (time.perf_counter() - started) * 1000
                    self.state = SessionState.SPEAKING
            sequence += 1

        self.state_store.commit_agent_turn(handle)
        self.last_turn_ms = first_audio_ms
        log.info("turn_complete", first_audio_ms=round(first_audio_ms or -1),
                 chars=len(dispatched))
        self._out.reset_turn()
        self.state = SessionState.LISTENING
```

- [ ] **Step 4: Implement `src/contra/app.py` (composition root)**

```python
from __future__ import annotations

import asyncio
from pathlib import Path

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

PHASE1_PROMPT = (
    "You are a debate opponent in a live spoken conversation. Argue against "
    "whatever position the user states. Keep replies to two or three short "
    "sentences. No markdown, no lists, no stage directions."
)

def build_app(config: Config) -> tuple[FastAPI, WebRtcTransport]:
    """The ONLY module that constructs concrete implementations."""
    tts = KokoroTts(config.tts)
    transport = WebRtcTransport(
        sample_rate=config.audio.sample_rate,
        frame_ms=config.audio.frame_ms,
        tts_rate=tts.sample_rate,
    )
    vad = SileroVad("models/silero_vad.onnx", config.vad.threshold,
                    config.vad.silence_confirm_ms, config.audio.sample_rate)
    stt = ParakeetStt(config.stt)
    llm = LlmClient(config.llm)

    session = Session(
        audio_in=transport, audio_out=transport, vad=vad,
        stt=stt, llm=llm, tts=tts, system_prompt=PHASE1_PROMPT,
        min_unit_chars=config.tts.min_unit_chars,
        max_unit_chars=config.tts.max_unit_chars,
    )

    async def on_offer(sdp: str, sdp_type: str) -> dict[str, str]:
        answer = await transport.handle_offer(sdp, sdp_type)
        asyncio.create_task(session.run())
        return answer

    return create_app(config, on_offer), transport
```

- [ ] **Step 5: Implement `src/contra/__main__.py`**

```python
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import uvicorn

from contra.app import build_app
from contra.config.loader import ConfigError, load_config
from contra.debate.llm_client import LlmClient
from contra.observability.logging import get_logger, setup_logging

def main() -> int:
    try:
        config = load_config(Path("config"))
    except ConfigError as exc:
        print(f"\n[X] Configuration error\n\n{exc}\n", file=sys.stderr)
        return 2

    setup_logging(config.logging.level)
    log = get_logger("contra")

    if not asyncio.run(LlmClient(config.llm).health()):
        print(
            "\n[X] Cannot reach the model server on 127.0.0.1:8080.\n\n"
            "  Start it first:\n"
            "      .\\scripts\\start.ps1\n\n"
            "  Or manually:\n"
            "      llama-server.exe -m C:\\local-models\\Qwen3.5-9B-UD-Q4_K_XL.gguf "
            "-ngl 99 -c 16384 -fa --host 127.0.0.1 --port 8080\n",
            file=sys.stderr,
        )
        return 3

    app, _ = build_app(config)
    log.info("ready", url=f"http://{config.ui.host}:{config.ui.port}")
    uvicorn.run(app, host=config.ui.host, port=config.ui.port, log_level="warning")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_session_loop.py -v`
Expected: 3 passed

- [ ] **Step 7: Verify the whole unit suite is still fast**

Run: `pytest tests/unit -v --durations=5`
Expected: all pass, total wall time **< 10 s**, no model loaded

- [ ] **Step 8: Commit**

```bash
git add src/contra/debate/session.py src/contra/app.py src/contra/__main__.py tests/unit/test_session_loop.py
git commit -m "feat: session loop and composition root for the walking skeleton"
```

---

## Task 13: End-to-end verification and M1 exit criteria

**Files:**
- Create: `benchmarks/results/M1-exit-criteria.md`
- Modify: `docs/07-planning/02-milestones.md` (tick M1 boxes)

**Interfaces:**
- Consumes: the running application
- Produces: a committed record of measured M1 exit criteria

- [ ] **Step 1: Start llama-server**

```powershell
C:\llama.cpp\llama-server.exe -m C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf `
  -ngl 99 -c 16384 -fa --host 127.0.0.1 --port 8080
```

Confirm in the log: `offloaded 33/33 layers to GPU`, and **no `mmproj`**.

- [ ] **Step 2: Start Contra and run one turn**

```powershell
python -m contra
```

Open `http://127.0.0.1:8000`, click **Start session**, say *"Remote work is better for productivity."*

Expected: transcription logged, LLM streams, audio plays back through the browser.

- [ ] **Step 3: Measure — agent must not trigger itself (NFR-A-05)**

With **speakers on at normal volume**, let the agent speak for 5 minutes total across several turns while you stay silent.

Record: number of times VAD reported `SPEECH_START` while `state == SPEAKING`.
**Pass = 0.**

- [ ] **Step 4: Measure WebRTC round-trip latency (NFR-P-15)**

In Chrome open `chrome://webrtc-internals`, select the peer connection, and read `currentRoundTripTime` from the candidate-pair stats.
**Pass ≤ 60 ms.**

- [ ] **Step 5: Measure turn latency**

From the structured logs, take `turn_complete.first_audio_ms` over 10 turns. Record median and max.
**No pass threshold in M1** — NFR-P-01 is an M3 gate. Record the number.

- [ ] **Step 6: Verify the architectural boundary holds**

```bash
ruff check src/contra
mypy src/contra
pytest tests/unit --durations=0
```
Expected: clean; unit suite < 10 s.

- [ ] **Step 7: Write `benchmarks/results/M1-exit-criteria.md`**

```markdown
# M1 — Walking skeleton exit criteria

Date: <YYYY-MM-DD> · GPU: RTX 4060 Laptop · driver <...> · llama.cpp <build>
Model: Qwen3.5-9B-UD-Q4_K_XL (5,966,095,584 bytes) · Python 3.11.x · mains power: yes

| Criterion | Target | Measured | Verdict |
|---|---|---|---|
| Spoken utterance -> spoken reply through browser | works | | |
| Agent self-trigger over speakers, 5 min (NFR-A-05) | 0 | | |
| WebRTC round trip (NFR-P-15) | <= 60 ms | | |
| Turn latency, median | recorded only | | |
| Turn latency, max | recorded only | | |
| Unit suite runtime | < 10 s | | |
| ruff import boundaries | clean | | |
| ConversationState stores spoken/generated separately | yes | | |

## Consequences for the design
<which documents change, and how>
```

- [ ] **Step 8: Commit**

```bash
git add benchmarks/results/M1-exit-criteria.md docs/07-planning/02-milestones.md
git commit -m "docs(m1): record measured walking-skeleton exit criteria"
```

---

## Task 14: Pipecat FR-13 spike (throwaway)

> **This is a spike — its output is an answer, not code you keep.** [ADR-0003](../../02-architecture/adr/0003-pipecat-as-orchestration-framework.md) names exactly one revisit trigger: *"Phase 1 spike shows FR-13 cannot be expressed cleanly in Pipecat's frame model."* Finding out now costs a day; finding out in Phase 2 costs a rewrite.

**Files:**
- Create: `spikes/pipecat_fr13/README.md` (findings), `spikes/pipecat_fr13/probe.py` (throwaway)
- Modify: `docs/02-architecture/adr/0003-pipecat-as-orchestration-framework.md` (record the outcome)

**Interfaces:**
- Consumes: `ConversationState` (Task 3)
- Produces: a written PASS/FAIL verdict, and an ADR update

- [ ] **Step 1: Install Pipecat in an isolated venv**

Keep it out of the main environment until the spike says it earns a place.

```bash
python -m venv .venv-spike
.venv-spike\Scripts\activate
pip install "pipecat-ai[webrtc,silero]"
```

- [ ] **Step 2: Write the probe**

The question is narrow: **can a Pipecat pipeline report how much synthesised audio was actually played, mapped back to a text offset?**

```python
# spikes/pipecat_fr13/probe.py
"""Probe: can Pipecat's frame model express FR-13 spoken-history truncation?

We do NOT need a working agent. We need to answer three questions:
  1. Can we attach text-span metadata to a TTS audio frame?
  2. Can we observe which audio frames were actually played (not just queued)?
  3. On an interruption, can we recover the played offset before state is lost?
"""
import inspect

from pipecat.frames.frames import (
    Frame, TTSAudioRawFrame, TTSStoppedFrame, StartInterruptionFrame,
)
from pipecat.processors.frame_processor import FrameProcessor

print("=== Q1: does TTSAudioRawFrame carry usable metadata? ===")
print([f for f in dir(TTSAudioRawFrame) if not f.startswith("_")])
print(inspect.signature(TTSAudioRawFrame.__init__))

print("\n=== Q2: what interruption frames exist? ===")
for cls in (StartInterruptionFrame, TTSStoppedFrame):
    print(cls.__name__, inspect.signature(cls.__init__))

print("\n=== Q3: can a processor sit downstream of playback? ===")
print([m for m in dir(FrameProcessor) if not m.startswith("_")])
```

Run: `python spikes/pipecat_fr13/probe.py`

- [ ] **Step 3: Answer the three questions in writing**

Create `spikes/pipecat_fr13/README.md`:

```markdown
# Spike: FR-13 expressibility in Pipecat

Date: <YYYY-MM-DD> · pipecat-ai version: <x.y.z>

## Q1 — Can we attach text-span metadata to a TTS audio frame?
<yes/no + how, or what blocks it>

## Q2 — Can we observe which audio frames were actually PLAYED?
<yes/no + which frame/callback exposes it>

## Q3 — On interruption, can we recover the played text offset?
<yes/no>

## Verdict
PASS  — FR-13 is expressible; adopt Pipecat in Phase 2 per ADR-0003.
FAIL  — FR-13 is not expressible; ADR-0003 revisit trigger has fired.
        Recommendation: keep the Task 12 asyncio loop and supersede ADR-0003.

## Evidence
<paste probe output and any code you had to write>
```

- [ ] **Step 4: Record the outcome in ADR-0003**

Append to the Revisit-when section:

```markdown
### Spike outcome — <YYYY-MM-DD>

FR-13 expressibility probe: **<PASS|FAIL>**. See `spikes/pipecat_fr13/README.md`.

<If PASS: Pipecat is adopted for Phase 2 pipeline assembly.>
<If FAIL: this ADR's revisit trigger has fired — supersede with an ADR keeping
the hand-written asyncio loop from Task 12.>
```

- [ ] **Step 5: Clean up the spike environment**

```bash
deactivate
rmdir /s /q .venv-spike
```

- [ ] **Step 6: Commit**

```bash
git add spikes/pipecat_fr13/ docs/02-architecture/adr/0003-pipecat-as-orchestration-framework.md
git commit -m "spike: probe FR-13 expressibility in Pipecat frame model"
```

---

## Self-review

**Spec coverage — M1 tasks from [milestones](../../07-planning/02-milestones.md):**

| Milestone task | Plan task |
|---|---|
| Project scaffold, config loader, logging | 1 |
| Browser page: getUserMedia with AEC, WebRTC both directions | 7 |
| Python WebRTC endpoint; signalling; AudioInput/AudioOutput | 6, 8 |
| Silero VAD integration | 9 |
| Parakeet STT behind SttStage | 10 |
| LlmClient with SSE streaming and cancellation | 5 |
| SentenceSegmenter with min-unit rule | 4 |
| Kokoro TTS behind TtsStage | 11 |
| ConversationState with FR-13 structure | 3 |
| Pipecat assembly; probe FR-13 expressibility | 14 |
| Unit tests for core components | 1–5, 8, 9, 12 |

**M1 exit criteria coverage:**

| Criterion | Where verified |
|---|---|
| Spoken utterance → spoken reply through browser | Task 13 Step 2 |
| Agent does not self-trigger over speakers (NFR-A-05) | Task 13 Step 3 |
| WebRTC round trip ≤ 60 ms (NFR-P-15) | Task 13 Step 4 |
| Turn latency measured | Task 13 Step 5 |
| Unit suite < 10 s, no models | Task 12 Step 7 |
| ruff import boundaries enforced | Task 1 Step 1, Task 3 Step 6 |
| `text_spoken` / `text_generated` separate | Task 3 |
| Pipecat FR-13 expressibility confirmed | Task 14 |

**Known deviation from the docs, flagged deliberately:**

Task 8 uses **`aiortc` directly** rather than Pipecat's transport, and Task 12 uses a hand-written asyncio loop. This keeps [ADR-0003](../../02-architecture/adr/0003-pipecat-as-orchestration-framework.md)'s *"Pipecat only in `pipeline/assembly.py`"* rule intact from day one, keeps `AudioInput`/`AudioOutput` independently testable, and defers the Pipecat integration risk to Task 14 where failure is cheap. Phase 1 uses none of Pipecat's actual value-adds — barge-in, turn detection, and AEC are all either deferred to Phase 2 or handled by the browser. **If Task 14 returns PASS, Phase 2 adopts Pipecat for pipeline assembly as ADR-0003 specifies.**

**Type consistency check:** `AudioChunk.text_span` is `tuple[int,int]` in Tasks 2, 8, 11, 12. `PlaybackPosition.last_complete_span_end` is `int` in Tasks 2, 3, 8. `TurnHandle.index` is `int` in Tasks 2, 3. `Transcript.text` is `str` in Tasks 2, 10, 12. `VadEvent` members are identical in Tasks 9 and 12.

**Deliberately NOT in this plan** (Phase 2+): semantic turn detection, barge-in wiring, transcript UI, SQLite persistence, the real debate persona, error recovery and the F-catalogue, context compaction.

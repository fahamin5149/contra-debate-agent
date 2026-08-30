# Configuration Management

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |
| **Decision** | [ADR-0011](../02-architecture/adr/0011-yaml-configuration-and-versioned-prompts.md) |

---

## 1. Layers

```
CONTRA_* environment variables      ← highest precedence
        ↓
config/user.yaml                    ← gitignored, machine-specific
        ↓
config/default.yaml                 ← committed, all defaults
```

Merged deeply, validated **once at startup** into typed objects, then injected.
No component reads global configuration directly.

---

## 2. `config/default.yaml`

```yaml
# ─────────────────────────────────────────────────────────────
# Contra — default configuration
# Override in config/user.yaml (gitignored) or CONTRA_* env vars.
# Every value here should cite the document that justifies it.
# ─────────────────────────────────────────────────────────────

llm:
  base_url: "http://127.0.0.1:8080/v1"   # loopback only — NFR-S-03
  model: "qwen3.5-9b"
  timeout_s: 30
  health_poll_s: 30

  sampling:                    # Unsloth instruct/general — Model Analysis §5.2
    temperature: 0.7
    top_p: 0.8
    top_k: 20
    min_p: 0.0
    presence_penalty: 1.5      # HIGH on purpose: stops recycled talking points
    repeat_penalty: 1.0        # disabled per vendor guidance
  max_response_tokens: 220     # ~45 s of speech — FR-31
  enable_thinking: false       # explicit; default on 9B but a model swap could change it

audio:
  transport: "webrtc"          # webrtc | native — ADR-0012. Native has NO AEC.
  sample_rate: 16000           # VAD + Parakeet native; avoids resampling
  frame_ms: 20                 # Silero's expected frame size
  output_buffer_ms: 100        # NFR-P-14; trades against barge-in speed
  pre_buffer_ms: 300           # retains speech onset across barge-in
  # Devices are chosen in the browser, not here — getUserMedia owns the picker.
  webrtc:
    echo_cancellation: true    # MANDATORY with speakers — NFR-A-05
    noise_suppression: true    # also helps against laptop fan noise
    auto_gain_control: true    # disable if it ducks user speech during double-talk

vad:
  threshold: 0.5
  min_speech_ms: 100           # rejects coughs and clicks
  silence_confirm_ms: 250      # Latency Budget §3

turn_detection:
  mode: "semantic"             # semantic | heuristic | ptt
  max_wait_ms: 1500            # extension when transcript is incomplete
  hard_timeout_ms: 2000        # safety valve — ADR-0007

stt:
  engine: "parakeet"           # parakeet | whisper
  model_path: "models/parakeet-tdt-0.6b-v3-onnx"
  partial_interval_ms: 500     # re-transcribe cadence (Parakeet isn't streaming)
  num_threads: 4               # P-cores; see §5

tts:
  engine: "kokoro"             # kokoro | piper
  model_path: "models/kokoro-v1.0.onnx"
  voice: "af_heart"
  speed: 1.0
  min_unit_chars: 15           # ADR-0006 short-text penalty
  max_unit_chars: 200

debate:
  intensity: "standard"        # socratic | standard | aggressive — FR-30
  max_response_seconds: 45
  context_tokens: 16384
  compaction_threshold: 0.8    # fraction of context before summarising

persistence:
  db_path: "data/contra.db"
  transcript_dir: "data/transcripts"
  export_markdown: true

ui:
  enabled: true
  host: "127.0.0.1"            # NFR-S-03 — never 0.0.0.0
  port: 8000
  show_metrics: true           # FR-42

logging:
  level: "INFO"
  file: "data/contra.log"
  log_transcripts: false       # NFR-S-01 — see §6
```

---

## 3. Validation

Every key is validated at startup. Invalid values **stop the process**.

```python
@dataclass(frozen=True)
class SamplingConfig:
    temperature: float
    top_p: float
    top_k: int
    min_p: float
    presence_penalty: float
    repeat_penalty: float

    def __post_init__(self) -> None:
        _in_range("temperature", self.temperature, 0.0, 2.0)
        _in_range("top_p", self.top_p, 0.0, 1.0)
        _in_range("presence_penalty", self.presence_penalty, -2.0, 2.0)
        if self.top_k < 0:
            raise ConfigError("llm.sampling.top_k", self.top_k, "must be >= 0")
```

```
ConfigError: llm.sampling.temperature = 3.5
  Expected: 0.0 to 2.0
  Source:   config/user.yaml line 7
```

> **Failing loudly is a deliberate choice.** Silently clamping 3.5 to 2.0 would
> produce a working system that argues badly, weeks before anyone connected the
> two. The error above costs five seconds; the alternative costs an afternoon of
> confused prompt tuning.

### Cross-field validation

Some constraints span keys and are easy to violate accidentally:

| Rule | Why |
|---|---|
| `turn_detection.max_wait_ms` < `hard_timeout_ms` | Otherwise the safety valve fires first and the semantic layer never matters |
| `tts.min_unit_chars` < `max_unit_chars` | Obvious, easy to typo |
| `debate.context_tokens` ≥ `llm.max_response_tokens` × 4 | Room for history, not just one response |
| `audio.output_buffer_ms` ≤ 200 | Above this, NFR-P-03 barge-in is unreachable |
| `ui.host` == `127.0.0.1` | **Security invariant** — see §4 |

---

## 4. The loopback invariant

```python
def _assert_loopback(host: str, name: str) -> None:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ConfigError(
            name, host,
            "must bind to loopback. These services have no authentication; "
            "binding to a routable address exposes an open inference endpoint "
            "and its context window. See NFR-S-03."
        )
```

Applied to `ui.host` and asserted against the `llm.base_url` host at startup.

**This is not overridable.** Not by `user.yaml`, not by environment variable.
`llama-server` has no authentication; bound to `0.0.0.0` on a laptop that joins
café Wi-Fi it is an open inference endpoint exposing whatever the user has been
arguing about.
[Threat Model](../06-governance/03-threat-model.md).

---

## 5. Machine-specific settings

`config/user.yaml` is where a given machine's reality lives:

```yaml
audio:
  webrtc:
    auto_gain_control: false   # AGC was ducking my voice during double-talk

stt:
  num_threads: 6      # P-cores only on i7-13620H (6P + 4E)

logging:
  level: "DEBUG"
```

> **The `num_threads` comment is real advice.** The i7-13620H has 6 performance
> and 4 efficiency cores. ONNX Runtime scheduled onto E-cores runs measurably
> slower, and the resulting latency variance looks like a mysterious P95 problem.
> Capping at the P-core count is a cheap fix worth trying if BM-03 shows high
> variance.

Audio devices are **not** configured here — the browser owns device selection via
`getUserMedia` and its own picker UI
([ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md)),
which also satisfies NFR-U-05 for free.

---

## 6. What configuration must never hold

| Never in config | Where instead |
|---|---|
| Secrets, API keys | Not applicable — fully local |
| Prompt text | `prompts/` — [ADR-0011](../02-architecture/adr/0011-yaml-configuration-and-versioned-prompts.md) |
| Absolute paths | Relative to app root (NFR-PORT-05) |
| Transcript content | The database |

**`logging.log_transcripts` defaults to `false` and deserves its comment.**
Enabling it writes the user's argument content to a plain text file with weaker
protection than the database. Legitimate for debugging; it should be a conscious
act, and the UI should indicate when it is on.

---

## 7. Runtime-mutable subset

Only these can change without a restart (`PATCH /api/config`):

| Key | Effect |
|---|---|
| `debate.intensity` | Next turn |
| `debate.max_response_seconds` | Next turn |
| `tts.voice` | Next utterance |
| `tts.speed` | Next utterance |
| `logging.level` | Immediate |

Everything else returns **409 Conflict** with a message saying a restart is
required — rather than accepting the change and silently doing nothing, which is
the more common and much worse behaviour.

---

## 8. Environment variables

```
CONTRA_LLM_BASE_URL
CONTRA_LLM_SAMPLING_TEMPERATURE
CONTRA_AUDIO_INPUT_DEVICE
CONTRA_DEBATE_INTENSITY
CONTRA_LOGGING_LEVEL
```

Pattern: `CONTRA_<SECTION>_<KEY>`, uppercase, `_` for nesting. Typed by the
target field, and a value that fails to parse is a startup error like any other.

Primarily for CI and benchmark scripts, which need to vary one setting without
editing files.

---

## 9. Effective configuration is logged and recorded

At startup, the merged configuration is logged at `INFO` with its provenance:

```
config.effective llm.sampling.temperature=0.7        source=default.yaml
config.effective audio.input_device="Headset Mic"    source=user.yaml
config.effective debate.intensity=aggressive         source=env
```

And the sampling parameters plus `prompt_version` are recorded per session
([Data Model §2.1](../02-architecture/06-data-model.md)).

> This closes the loop with the
> [Evaluation Framework](../04-quality/02-evaluation-framework.md). Debate
> quality is subjective and only assessable across many sessions. Being able to
> ask *"were sessions at temperature 0.7 better than at 0.9?"* requires knowing
> what each session actually ran with — and "I think I changed it around then"
> is not an answer.

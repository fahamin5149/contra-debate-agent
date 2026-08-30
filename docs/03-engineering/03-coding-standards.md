# Coding Standards

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

Only the rules that carry weight for *this* project. General Python style is
delegated to `ruff` and not restated here.

---

## 1. Automated enforcement

| Tool | Scope | Blocking |
|---|---|---|
| `ruff format` | All | Yes |
| `ruff check` | All, incl. import boundaries | Yes |
| `mypy --strict` | `src/contra/debate/` | Yes |
| `mypy` (normal) | Rest of `src/` | Yes |
| `pytest` | All | Yes |

**Anything a tool can enforce should not be a written rule.** The sections below
are the ones tools cannot check.

---

## 2. Architectural boundaries — enforced by lint

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"onnx_asr".msg       = "Only in speech/. Core depends on interfaces."
"kokoro_onnx".msg    = "Only in speech/."
"sounddevice".msg    = "Only in audio/."
"pipecat".msg        = "Only in pipeline/assembly.py."
"torch".msg          = "Only in detect/ and speech/."
```

`debate/` must import no I/O library. It is the layer whose logic we most need to
test cheaply and reason about clearly, and it is the layer that erodes fastest
without mechanical enforcement — someone needs one type from one library, and the
boundary quietly dissolves.

[Repository Structure §2.1](01-repository-structure.md#21-debate-imports-no-io-libraries).

---

## 3. Async discipline

The pipeline is async throughout. Two rules, both about the same failure.

### 3.1 Never block the event loop

```python
# WRONG — stalls audio for the duration of inference
async def transcribe(self, audio: bytes) -> str:
    return self._model.recognize(audio)          # blocking CPU call

# RIGHT
async def transcribe(self, audio: bytes) -> str:
    return await asyncio.to_thread(self._model.recognize, audio)
```

> This is the highest-consequence rule in the document. A blocking call inside
> the event loop stalls **audio capture and playback** — the user hears a
> dropout, or their speech is simply not recorded. On a pipeline where 20 ms
> frames must flow continuously, a 200 ms blocking inference call is ten lost
> frames.
>
> ONNX Runtime releases the GIL during inference, so `to_thread` genuinely
> parallelises here. That this holds must be verified in BM-03 —
> [ADR-0009](../02-architecture/adr/0009-python-as-orchestration-language.md)
> depends on it.

### 3.2 Every cancellable operation must actually cancel

Barge-in requires stopping TTS *and* LLM generation within 300 ms.

```python
# WRONG — abandons the iterator; the server keeps generating
async def cancel(self) -> None:
    self._stop_reading = True

# RIGHT — closes the connection, freeing the server slot
async def cancel(self) -> None:
    if self._task and not self._task.done():
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
```

The wrong version *appears* to work: audio stops, the user is happy. Meanwhile
the GPU keeps producing tokens nobody will hear, occupying the slot the next turn
needs — so interrupting makes the *following* response slower.
[Internal API Spec §A.4](../02-architecture/05-internal-api-spec.md).

### 3.3 Never swallow `CancelledError`

```python
# WRONG — breaks cancellation everywhere upstream
try:
    await something()
except Exception:
    log.warning("failed")

# RIGHT
try:
    await something()
except asyncio.CancelledError:
    raise
except Exception:
    log.warning("failed", exc_info=True)
```

`CancelledError` inherits from `BaseException` in 3.8+, so a bare
`except Exception` will not catch it — but `except BaseException` and some
library patterns will. Worth being explicit.

---

## 4. Typing

`mypy --strict` on `debate/`; normal elsewhere.

```python
from typing import Protocol

class SttStage(Protocol):
    def feed(self, frame: AudioFrame) -> None: ...
    async def finalise(self) -> Transcript: ...
```

**Protocols, not ABCs.** Structural typing means a test fake needs no inheritance
— it just needs the right shape. That keeps the fakes trivial, which keeps unit
tests cheap, which is the point.

**Frozen dataclasses for data crossing boundaries:**

```python
@dataclass(frozen=True)
class AudioChunk:
    samples: bytes
    text_span: tuple[int, int]
    duration_ms: float
    sequence: int
```

Immutability matters specifically for `AudioChunk` — it flows through the queue
and is later read to reconstruct spoken history (FR-13). A mutation anywhere in
that path would corrupt the truncation silently.

---

## 5. Error handling

### 5.1 Match the response to the severity

| Failure | Response |
|---|---|
| LLM unreachable | `DEGRADED`, speak an acknowledgement, attempt restart |
| One TTS sentence fails | Log, skip it, continue |
| Audio device disappears | Fatal — cannot continue |
| Config invalid | **Fail at startup**, naming the key |

The asymmetry is the point. A dropped sentence is a glitch; a dead LLM ends the
debate.
[Error Handling & Resilience](06-error-handling-and-resilience.md).

### 5.2 Errors carry remediation

```python
raise LlmUnavailableError(
    message="Cannot reach the model server on port 8080.",
    remediation="Start it with: .\\scripts\\start.ps1",
)
```

NFR-U-03 forbids errors that state a problem without stating an action. The
`remediation` field is required, not optional — a message without one fails
review.

### 5.3 Never silently default

```python
# WRONG
temperature = config.get("temperature", 0.7)

# RIGHT — validated at startup, absent means a config bug
temperature: float = config.llm.temperature
```

Silently coercing a bad value produces the worst class of bug in this project:
mysteriously poor debate quality, weeks later, with no signal connecting cause to
effect.

---

## 6. Logging

Structured, with a correlation ID per turn:

```python
log.info("stage_complete",
         turn_id=turn_id, stage="stt",
         duration_ms=205, confidence=0.94)
```

| Level | Use |
|---|---|
| `DEBUG` | Per-frame; off by default |
| `INFO` | Stage completions, state changes, turn boundaries |
| `WARNING` | Recovered failures, degraded operation |
| `ERROR` | Failures affecting the session |

**Never log transcript content above `DEBUG`.** Logs are less protected than the
database, and transcripts are the user's private argument content (NFR-S-01).

[Observability Spec](../04-quality/04-observability-spec.md).

---

## 7. Comments

Comment **why**, never what.

```python
# WRONG
# increment the sequence number
self.sequence += 1

# RIGHT
# Kokoro ONNX has high per-call overhead and is slower than PyTorch on very
# short inputs (RTF 0.72 vs 0.49). Below ~15 chars the overhead dominates, so
# we hold the fragment and merge it into the next unit. See ADR-0006.
if len(unit) < MIN_UNIT_CHARS:
    self._pending = unit
    return []
```

Every non-obvious constant should either cite an ADR or explain itself. A
threshold with no rationale becomes untouchable — nobody dares change it because
nobody knows what it protects.

---

## 8. Magic numbers

Named constants, at module level, with sources:

```python
FRAME_MS = 20                  # Silero VAD's expected frame size
SAMPLE_RATE = 16_000           # VAD and Parakeet native; avoids resampling
SILENCE_CONFIRM_MS = 250       # Latency Budget §3, step 1
TURN_TIMEOUT_MS = 2_000        # safety valve; ADR-0007
MIN_UNIT_CHARS = 15            # ADR-0006 short-text penalty
OUTPUT_BUFFER_MS = 100         # NFR-P-14; trades against barge-in speed
MAX_RESPONSE_TOKENS = 220      # ~45 s of speech; FR-31
```

---

## 9. Testing conventions

- Test names state the behaviour: `test_barge_in_truncates_history_to_spoken_audio`
- One assertion concept per test
- Fakes over mocks — Protocols make fakes trivial
- Every bug gets a regression test before the fix
- Timing-sensitive tests use injected clocks, never `sleep`

**Invariants are executable.** The state invariants in
[Data Flow & State §8](../02-architecture/04-data-flow-and-state.md) become
assertions, particularly I-3 (spoken-history truncation) — it is invisible in
normal operation and only manifests many turns later as odd agent behaviour.

---

## 10. Commits

```
<type>(<scope>): <subject>

feat(debate): hold position under repeated user objection
fix(audio): retain pre-buffer across barge-in transition
perf(llm): speculative prefill on silence detection
docs(adr): supersede ADR-0008 after OQ-01 resolved
```

Types: `feat` `fix` `perf` `refactor` `test` `docs` `chore` `bench`.

**A commit changing a prompt must state what behaviour it targets.** Prompt
changes are the highest-iteration and least-testable edits in the project; a
message reading "tweak prompt" is worthless three weeks later when trying to
work out which change made the agent worse.

---

## 11. File size

NFR-M-05: no file beyond ~400 lines without a documented reason.

Not aesthetics. A file you can hold in your head is one you can reason about and
edit reliably — and the same is true for a model editing it. When a file grows
past this, it is nearly always doing two things.

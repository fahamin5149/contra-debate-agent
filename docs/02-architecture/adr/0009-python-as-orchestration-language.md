# ADR-0009: Python 3.11 as the orchestration language

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | High | **Hard** |

## Context

Something must orchestrate the pipeline: audio I/O, VAD, turn detection, STT,
LLM streaming, segmentation, TTS, playback, and interruption.

The LLM itself runs in a separate C++ process
([ADR-0002](0002-llama-cpp-server-as-llm-runtime.md)), so this language choice
governs **coordination, not inference**. That distinction matters — it removes
raw compute performance from the decision.

## Decision

**Python 3.11**, with async/await for pipeline concurrency.

**Not 3.13**, despite 3.13 being installed on the development machine
**[VERIFIED]**.

## Rationale

### Why Python

Every component we need has a mature Python binding, and several have *only* a
Python binding:

| Component | Availability |
|---|---|
| Pipecat | Python only |
| `onnx-asr` (Parakeet) | Python |
| `kokoro-onnx` | Python |
| Silero VAD | Python (PyTorch/ONNX) |
| Smart Turn v2 | Python, via Pipecat |
| `openai` SDK | Python (among others) |

Choosing anything else means writing bindings or reimplementing model inference.
The compute-heavy work — the LLM — is already in C++ behind an HTTP boundary, so
Python's speed is not on the critical path. It orchestrates; it does not compute.

### Why 3.11 rather than 3.13

**[VERIFIED]** the dev machine has Python 3.13. We pin to 3.11 anyway.

> ML wheel availability lags Python releases, often by a year or more. On
> **Windows**, a missing wheel is not a minor inconvenience — it means compiling
> from source, which requires the MSVC build tools, and frequently fails on
> packages with C extensions and CUDA dependencies.
>
> `onnxruntime`, `silero-vad`, `sounddevice`, and Pipecat's transitive
> dependencies are all candidates for this. Python 3.11 has the broadest wheel
> coverage of any currently-supported version.

This is [RISK-04](../../06-governance/01-risk-register.md) and the pin is its
mitigation. The cost of pinning is zero; the cost of not pinning is potentially
days lost to a Windows build environment.

## Alternatives considered

### Rust — rejected

Genuinely attractive on the merits: real threads without the GIL, predictable
latency without garbage-collection pauses, excellent audio libraries (`cpal`),
single-binary distribution, and no dependency-hell risk.

Rejected because **the ecosystem is not there**. Pipecat has no Rust equivalent.
Parakeet, Kokoro, Silero, and Smart Turn would all need ONNX Runtime bindings
written and maintained by us. That is a project in itself, and it competes with
building the actual product.

Worth noting that a Go implementation of a Parakeet ONNX server exists
(`achetronic/parakeet`), which shows the approach is feasible — but only for one
component out of five.

### C# / .NET — rejected

Sensible on Windows: good audio APIs, ONNX Runtime support, strong tooling,
single-binary output. Same fundamental problem — no Pipecat, and every model
integration becomes bespoke.

### TypeScript / Node — rejected

Node is present on the machine. Excellent for the UI layer. Weak for local ML:
ONNX Runtime Node bindings are less mature, and audio I/O is awkward. Remains
the likely choice for the **browser UI**, which is a separate concern.

### C++ — rejected

Would match llama.cpp and give maximal control. Development velocity for a
project of this kind would be poor, and every model integration is manual.

### Python 3.12 — reasonable, not chosen

A defensible middle ground with better wheel coverage than 3.13. 3.11 is chosen
for maximum safety; if a dependency requires 3.12+, moving is trivial.

## Consequences

### Positive
- Every needed component has a mature binding.
- Fast development; the pipeline is I/O-bound coordination, which async Python
  handles well.
- Rich testing ecosystem (`pytest`, `pytest-asyncio`).
- Easy to instrument for the per-stage timings FR-53 requires.
- Large community for the specific stack (Pipecat + ONNX + local LLM).

### Negative
- **The GIL.** CPU-bound work — STT and TTS inference, which
  [ADR-0004](0004-cpu-placement-for-stt-and-tts.md) puts on the CPU — must
  release it or the audio event loop stalls.

  *Mitigation:* ONNX Runtime releases the GIL during inference, so this should be
  fine. **Should be** — it must be verified in BM-03, because if it does not
  hold, the entire CPU-placement decision is compromised. This is the single
  most important negative consequence in this ADR.

- **Garbage-collection pauses** add latency jitter, inflating P95
  ([Latency Budget §9](../07-latency-budget.md)).
- **Dependency management on Windows** is the main operational risk — hence the
  3.11 pin.
- Distribution is awkward: no single binary; users need a Python environment.
- 3.11 forgoes some newer language features. Irrelevant here.

### Neutral
- The UI may be TypeScript regardless; this ADR governs the orchestrator only.

## Revisit when

- **BM-03 shows GIL contention causing audio dropouts or latency spikes.**
  Mitigations in order: move inference to a subprocess; use ONNX Runtime's
  threading more aggressively; in the extreme, rewrite the audio path in a native
  extension.
- Distribution to non-technical users becomes a goal — packaging Python for
  Windows is genuinely unpleasant and might justify reconsidering.
- A credible Rust or Go voice-agent framework with these model integrations
  appears.

**Reversibility is Hard** because rewriting the orchestrator means rewriting
essentially all of our own code. This is the most expensive decision in the set
to reverse, which is why the GIL question deserves early measurement rather than
optimism.

## Toolchain

| | |
|---|---|
| Python | 3.11.x |
| Environment | `uv` (**[VERIFIED]** not installed — a setup prerequisite) or `venv` |
| Dependencies | `pyproject.toml`, fully pinned lockfile |
| Lint / format | `ruff` |
| Types | `mypy`, strict on the debate core |
| Tests | `pytest` + `pytest-asyncio` |

Details in [Development Environment](../../03-engineering/02-development-environment.md).

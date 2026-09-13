# BM-03 — CPU speech performance under GPU load

| | |
|---|---|
| **Date** | 2026-09-13 |
| **Verdict** | **PASS with design change** |
| **GPU load** | Continuous Qwen3.5-9B generation through llama.cpp/Vulkan |
| **CPU / power** | i7-13620H (10 cores, 16 logical processors); mains power |
| **Python / ONNX Runtime** | 3.11.9 / 1.29.0 |
| **STT / TTS / turn detector** | Parakeet TDT 0.6B v3 int8 / Piper 1.8.0 `en_US-lessac-medium` / Smart Turn v3.2 CPU |
| **Isolation** | Windows `spawn`; one model-owning worker at a time; 4 inference threads; logical CPUs 0–1 reserved |
| **Timer** | Process-scoped 1 ms Windows multimedia timer resolution |
| **Repeats** | Warm-up discarded; median of 5 measured runs |

## Corrected method

`python -m benchmarks.bm03_cpu_speech_rtf --threads 4 --repeats 5 --isolation subprocess --tts-engine piper --reserve-logical-cpus 0 1 --json benchmarks/results/BM-03-piper-raw.json`

The first 2026-09-12 run used a drifting `asyncio.sleep(0.02)` interval and
classified every interval above 30 ms as a dropped frame. On this Windows
machine, the same loop woke near 31 ms while otherwise idle, producing 308 false
"drops" in 10 seconds. Those counts are invalid and are retained below as
superseded evidence, not used for the verdict.

The corrected ticker schedules fixed 20 ms deadlines and counts only complete
service windows missed beyond a deadline. The parent performs only short IPC
waits; each child loads and owns its model. LLM generation remains continuous.
Raw results are in [BM-03-piper-raw.json](BM-03-piper-raw.json).

## Passing results

| Metric | Measured | Gate | Result |
|---|---:|---:|---|
| STT RTF, 5 s | 0.064 | ≤0.3 | PASS |
| STT RTF, 20 s | 0.057 | ≤0.3 | PASS |
| STT silence output | 0 words | 0 words | PASS |
| Piper full synthesis, exact 15 chars | 57.5 ms | TTFB ≤150 ms | PASS (conservative full-call bound) |
| Piper RTF, 40 chars | 0.052 | ≤0.5 | PASS |
| Piper RTF, 120 chars | 0.050 | ≤0.5 | PASS |
| Smart Turn | 15.0 ms | ≤150 ms | PASS |
| Missed 20 ms service windows | 0 | 0 | PASS |

Piper returned the full short-unit PCM in 57.5 ms, so its first byte necessarily
arrived within the 150 ms TTFB gate. This does not claim browser audibility;
BM-05 and the final M2 renderer test own that evidence.

## Superseded exploratory results

- Kokoro's short-unit full synthesis measured 420–653 ms after warm-up, so it
  does not meet NFR-P-13 on this target machine.
- Corrected fixed-deadline trials without a 1 ms timer request showed occasional
  missed windows (2–8 depending on configuration). A 1 ms process-scoped timer
  request removed them in the selected five-repeat run.
- Subprocess ownership is retained for bounded cancellation and replacement of
  obsolete native calls. This benchmark does **not** prove that the GIL caused
  the original invalid frame counts.

## Artifact identity

| Artifact | SHA-256 |
|---|---|
| Smart Turn v3.2 CPU | `2BB026316B14A660486A75B1733CD3FBAB8C2FD0314DC9AF7BE49F8CCA967E4F` |
| Piper `en_US-lessac-medium.onnx` | `5EFE09E69902187827AF646E1A6E9D269DEE769F9877D17B16B1B46EEAAF019F` |
| Piper voice config | `EFE19C417BED055F2D69908248C6BA650FA135BC868B0E6ABB3DA181DAB690A0` |

## Consequences for the design

- [ADR-0006](../../docs/02-architecture/adr/0006-kokoro-for-tts.md) is
  superseded by [ADR-0015](../../docs/02-architecture/adr/0015-piper-as-primary-tts.md).
- Piper becomes the default TTS; Kokoro remains an optional non-conforming
  quality mode until it meets NFR-P-13.
- Phase 2 keeps spawned model ownership, four inference threads, two reserved
  logical CPUs, and scoped timer-resolution lifecycle management.
- BM-03 no longer blocks M0. BM-05 and the incomplete M1 real-session evidence
  remain blocking entry gates for Phase 2 application implementation.

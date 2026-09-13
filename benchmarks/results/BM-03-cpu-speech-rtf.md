# BM-03 — CPU speech performance under GPU load

| | |
|---|---|
| **Date** | 2026-09-12 |
| **Verdict** | **FAIL** |
| **GPU load** | Continuous Qwen3.5-9B generation through llama.cpp/Vulkan |
| **CPU** | i7-13620H; mains power |
| **Python / ONNX Runtime** | 3.11.9 / 1.29.0 |
| **STT / TTS / turn detector** | Parakeet TDT 0.6B v3 int8 / Kokoro v1.0 / Smart Turn v3.2 CPU |
| **Smart Turn SHA-256** | `2BB026316B14A660486A75B1733CD3FBAB8C2FD0314DC9AF7BE49F8CCA967E4F` |

## Method

`python -m benchmarks.bm03_cpu_speech_rtf --threads 4 6 8 --repeats 2`

The harness kept an LLM streaming continuously, discarded model warm-up, and
reported the median of two measurements after an unreported warm-up. STT used 5-second and 20-second
Kokoro-generated speech waveforms. TTS used 15-, 40-, and 120-character units.
The 20 ms event-loop ticker recorded missed frame deadlines during inference.
Kokoro and Parakeet received explicitly bounded ONNX thread pools.

## Results

| Threads | STT RTF 5 s | STT RTF 20 s | TTS RTF 15 | TTS RTF 40 | TTS RTF 120 | Smart Turn | Missed frames |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 0.493 | 0.369 | 2.519 | 1.632 | 1.452 | 235.7 ms | 801 |
| 6 | 0.671 | 0.636 | 3.221 | 2.226 | 0.873 | 30.9 ms | 1,030 |
| 8 | **0.110** | **0.065** | **0.588** | **0.303** | **0.263** | **20.6 ms** | **170** |

Additional results:

- Silence produced **0 words** at every thread count (NFR-A-02).
- The best 15-character TTS wall time was **652.2 ms**, above the 150 ms target.
- Eight threads met STT, 40+-character TTS, and Smart Turn throughput targets.
- No configuration met the zero-dropped-frame criterion.

## Verdict

**FAIL.** The best throughput configuration is eight threads, but it still
missed 170 capture deadlines and the short-unit TTS target by more than 4×.
Thread placement is also highly sensitive: four- and six-thread runs were much
slower despite warm-up and repeated medians.

## Consequences for the design

- ADR-0009's thread-isolation assumption is not validated on the target machine.
- Phase 2 must isolate CPU inference in owned subprocess workers before relying
  on concurrent capture, or repeat this benchmark with another demonstrated
  isolation mechanism.
- The 15-character segmentation minimum must be revisited after isolation; do
  not hide the failure by raising the threshold without measuring conversation
  latency and cancellation behavior.
- M0 remains blocked until the mitigation is implemented and BM-03 passes on a
  repeat run.

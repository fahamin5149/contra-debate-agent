# BM-02 — Prefix cache effectiveness

| | |
|---|---|
| **Date** | 2026-09-12 |
| **Verdict** | **PASS** |
| **GPU** | NVIDIA RTX 4060 Laptop, 8,188 MiB, driver 616.64 |
| **CPU** | i7-13620H; mains power |
| **llama.cpp** | 0.3.0-dev, build 10679, commit `50f068fff` |
| **Backend** | Vulkan `Vulkan1`, `-ngl 99 -c 16384 -fa on` |
| **Model** | `Qwen3.5-9B-UD-Q4_K_XL.gguf`, SHA-256 `6F5D30666C2D8AE16A306E616D95341DCF3CC46810DF84D7E6F5A7D1E4C1B293` |
| **Python** | 3.11.9 |

## Method

`python -m benchmarks.bm02_prefix_cache --turns 20`

Each turn appended a user and assistant message and requested 50 tokens with
thinking disabled. The cached series kept the system prefix stable. The control
series changed the system prompt each turn. TTFT was measured at the first
non-empty streamed content token.

## Results

| Metric | Cached | Perturbed |
|---|---:|---:|
| Median TTFT | **320.9 ms** | **1,079.1 ms** |
| Turn-20 TTFT | **332.6 ms** | **1,576.9 ms** |
| Perturbed/cached median | **3.36×** | — |

| Speculative-prefill probe | Measured |
|---|---:|
| Equivalent uncached-context TTFT | 1,189.3 ms |
| `max_tokens: 0` prefill wall time | 1,140.2 ms |
| Immediate full-request TTFT after prefill | **192.3 ms** |
| TTFT speedup | **6.18×** |

The cached series stayed approximately flat after warm-up while the perturbed
series grew with context. One cached cold-slot outlier occurred at turn 7
(4,730.7 ms); it is retained in the raw console evidence and did not change the
median. Two control-series cold-slot outliers occurred at turns 2 and 4.

## Verdict

**PASS.** The cached-versus-perturbed median difference exceeds the benchmark's
2× confirmation threshold, and turn-20 cached TTFT remained below 400 ms.

## Consequences for the design

- OQ-03 can be closed after the required documentation propagation.
- RISK-03 can be retired or substantially reduced.
- NFR-P-12 is **[VERIFIED]** for this 20-turn benchmark configuration.
- Speculative prefill is viable on this build: an immediate full request after
  the zero-token prefill reached its first token 6.18× faster than the equivalent
  uncached request. The prefill itself still consumes 1.14 s of background work.

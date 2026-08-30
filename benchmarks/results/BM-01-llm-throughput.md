# BM-01 — LLM throughput and latency

| | |
|---|---|
| **Date** | 2026-08-31 |
| **Verdict** | ✅ **PASS** |
| **GPU** | NVIDIA RTX 4060 Laptop, 8,188 MiB, driver 610.47 |
| **CPU** | i7-13620H · **Mains power:** yes |
| **llama.cpp** | 0.3.0-dev, build 10679, commit `50f068fff` |
| **Backend** | ⚠️ **Vulkan**, not CUDA (see below) |
| **Model** | `Qwen3.5-9B-UD-Q4_K_XL.gguf` (5,966,095,584 bytes) |
| **Flags** | `-dev Vulkan1 -ngl 99 -c 16384 -fa on` |

## Results

| Run | TTFT | Tokens | Wall | Decode rate |
|---|---|---|---|---|
| 1 — remote work | 208 ms | 75 | 2.60 s | 31.4 tok/s |
| 2 — nuclear power | 312 ms | 54 | 1.94 s | 33.1 tok/s |
| 3 — social media | 327 ms | 70 | 2.42 s | 33.5 tok/s |

| Metric | Target | Measured | Verdict |
|---|---|---|---|
| Median TTFT (warm, short prompt) | ≤ 400 ms | **312 ms** | ✅ |
| Median decode rate | ≥ 25 tok/s | **33.1 tok/s** | ✅ |

**VRAM with model loaded:** 5,970 MiB used / 1,987 MiB free.

## Verdict: PASS

Comfortably above target, and **on Vulkan rather than CUDA** — which was not the
planned configuration.

At 33 tok/s a 220-token response (`max_response_tokens`) generates in **~6.7 s**
while taking ~45 s to speak, so generation stays well ahead of playback. The
streaming design has ample margin.

## The unplanned finding: Vulkan, not CUDA

Every document in this tree specifies a **CUDA** build. The winget-installed
`llama` binary is a **Vulkan** build, and it exposes both GPUs:

```
Available devices:
  Vulkan0: Intel(R) UHD Graphics              (8054 MiB, 7395 MiB free)
  Vulkan1: NVIDIA GeForce RTX 4060 Laptop GPU (7956 MiB, 7188 MiB free)
```

> **`-dev Vulkan1` is mandatory.** Without it, device selection may land on the
> Intel iGPU (`Vulkan0`), which would be catastrophically slow and would look
> like a model or config problem rather than a device-selection one.

Since Vulkan clears the target with 32% margin, **there is no reason to install a
CUDA build for Phase 1**. Revisit only if a later phase needs headroom that a
CUDA build might supply — CUDA is generally faster on NVIDIA, so this is a known
lever still in reserve.

## Consequences for the design

- **[RISK-02](../../docs/06-governance/01-risk-register.md) (throughput below
  target) is retired.** No need to fall back to Qwen3.5-4B.
- **[RISK-01](../../docs/06-governance/01-risk-register.md) (llama.cpp support
  for the hybrid DeltaNet architecture) is retired** — the model loads and
  generates correctly.
- [NFR-P-20](../../docs/00-product/05-non-functional-requirements.md)
  (≥ 25 tok/s) upgrades from `[SOURCED]` to **`[VERIFIED]`**.
- [NFR-P-12](../../docs/00-product/05-non-functional-requirements.md)
  (TTFT ≤ 400 ms) met on short prompts.

## Not yet measured

- **TTFT at realistic context depth.** These prompts were ~40 tokens. A turn-20
  debate carries ~3,000 tokens of history, and prefill cost grows with it. That
  is **BM-02** (prefix caching) and it remains the largest open latency risk.
- **Thermal decay.** No 30-minute sustained run yet; laptop GPUs throttle.
- Throughput under concurrent CPU load from STT/TTS — part of **BM-03**.

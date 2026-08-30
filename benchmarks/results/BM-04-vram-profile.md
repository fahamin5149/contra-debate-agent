# BM-04 — VRAM profile

| | |
|---|---|
| **Date** | 2026-08-31 |
| **Verdict** | ✅ **PASS — optimistic branch confirmed** |
| **GPU** | NVIDIA RTX 4060 Laptop, 8,188 MiB, driver 610.47 |
| **Backend** | Vulkan, `-dev Vulkan1 -ngl 99 -c 16384 -fa on` |

## The question this resolves

[Resource Budget §3](../../docs/02-architecture/08-resource-budget.md) could not
decide between two futures, and the difference decided whether the design was
comfortable or knife-edge:

| Branch | Headroom |
|---|---|
| Optimistic — Intel iGPU drives the display | ~1.04 GiB |
| Pessimistic — the 4060 drives the display | ~0.34 GiB |

## Measurements

### Desktop idle, nothing loaded

```
memory.total 8188 MiB | memory.used 0 MiB | memory.free 7956 MiB
compute processes: (none)
```

> **0 MiB used.** The Intel UHD iGPU drives the display and the RTX 4060 is
> completely clean. **The optimistic branch is confirmed** — the `[ASSUMED]`
> marker on that claim upgrades to `[VERIFIED]`.

### Model loaded (16K context)

| State | Used | Free |
|---|---|---|
| Idle | 0 MiB | 7,956 MiB |
| llama-server, 9B @ 16K ctx | **5,970 MiB** | **1,987 MiB** |
| \+ orchestrator (Parakeet, Kokoro, Silero loaded) | **5,975 MiB** | **1,982 MiB** |

## Two findings

### 1. Actual VRAM use is ~1 GiB below the estimate

| | Predicted | Measured |
|---|---|---|
| LLM total | 6.86 GiB (7,025 MiB) | **5.83 GiB (5,970 MiB)** |
| Headroom | 0.34 – 1.04 GiB | **1.94 GiB** |

The estimate was conservative. Likely causes: Vulkan's runtime overhead is
smaller than the ~0.70 GiB assumed for CUDA, and KV cache may be allocated
lazily per slot rather than reserved up front. **The arithmetic in
[Resource Budget §2](../../docs/02-architecture/08-resource-budget.md) should be
treated as an upper bound, not a prediction.**

### 2. ADR-0004 is confirmed in a single number

Loading Parakeet TDT (652 MB int8), Kokoro-82M (325 MB) and Silero VAD added
**5 MiB of VRAM** — because
[ADR-0004](../../docs/02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md)
puts every speech model on the CPU.

> Had those models gone on the GPU, they would have cost roughly 1.2–1.5 GiB —
> most of the headroom, and under the *pessimistic* branch they would not have
> fitted at all. The decision was made to survive an assumption that turned out
> false; it is still the right decision, and it now buys margin instead of
> merely avoiding failure.

## Consequences for the design

- The `[ASSUMED]` claim that the iGPU drives the display → **`[VERIFIED]`**
- Headroom is **1.94 GiB**, far better than either modelled branch
- **32K context is now affordable** (+0.5 GiB KV) if BM-02 shows a reason to want
  it — previously listed as "only if BM-04 is optimistic"
- NFR-R-01 (≤ 7.5 GiB) met with large margin

## Not yet measured

- VRAM across a 60-minute session (NFR-REL-05 leak check)
- VRAM at 32K context
- Whether KV cache grows as conversation depth increases — the 5,970 MiB figure
  was taken after short prompts only

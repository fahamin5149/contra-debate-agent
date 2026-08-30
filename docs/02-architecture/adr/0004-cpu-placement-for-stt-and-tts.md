# ADR-0004: LLM on GPU; all speech models on CPU

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | High | Easy |

> The central resource decision. Most other component choices follow from it.

## Context

The target machine has an RTX 4060 Laptop with **8,188 MiB (7.996 GiB)** of VRAM
**[VERIFIED]**.

Qwen3.5-9B and its runtime consume approximately **6.86 GiB**
([Resource Budget §2](../08-resource-budget.md)):

| Item | GiB |
|---|---|
| Weights | 5.556 |
| KV cache @ 16K FP16 | 0.500 |
| DeltaNet recurrent state | 0.100 |
| CUDA backend overhead | 0.700 |

Windows also reserves VRAM for the display. This is a hybrid-graphics laptop
with an Intel UHD iGPU; **[ASSUMED]** the iGPU drives the desktop, but this is
unverified (BM-04).

**Remaining headroom is therefore somewhere between 0.34 and 1.04 GiB** — and
which end of that range we are at is currently unknown.

The conventional approach puts STT (and sometimes TTS) on the GPU for speed.

## Decision

**The GPU has exactly one tenant: the LLM.**

STT (Parakeet), TTS (Kokoro), VAD (Silero), and semantic turn detection all run
on the **CPU**.

## Rationale

### 1. It removes a dangerous unknown

Sizing speech models into headroom that might be 0.34 GiB or might be 1.04 GiB
means the system's viability depends on an unverified assumption about which GPU
drives the display. Moving them off the GPU makes that question irrelevant to
correctness — it becomes merely informative.

### 2. The CPU is genuinely idle

This is the argument that makes the decision cheap rather than sacrificial.

With `-ngl 99`, all 32 layers execute on the GPU. The CPU marshals HTTP requests
and shuttles tokens. **During the LLM's ~5-second generation burst, an
i7-13620H's 16 threads sit essentially unused.**

That capacity is already bought and currently wasted. Published figures suggest
it is sufficient:

| Workload | Reported | Confidence |
|---|---|---|
| Parakeet TDT on CPU | ~4× faster than Whisper | **[SOURCED]** |
| Kokoro-82M on CPU | Faster than real-time | **[SOURCED]** |

### 3. It eliminates contention jitter

STT and TTS spiking on the same GPU during LLM generation causes exactly the
kind of variable latency that inflates P95
([Latency Budget §9](../07-latency-budget.md)). Physical separation of workloads
removes the interaction entirely.

### 4. Partial offload is not a fallback

If VRAM ran short, the instinctive fix is to offload a few LLM layers to CPU.
**This does not work** — throughput collapses rather than degrading, because
every token then crosses PCIe for the CPU-resident layers
([Resource Budget §6](../08-resource-budget.md)). Since we cannot shrink the
LLM's GPU share gracefully, protecting it absolutely is the only stable policy.

## Alternatives considered

### STT on GPU, TTS on CPU — rejected

The common compromise. faster-whisper small.en needs ~0.5 GiB, which fits in the
optimistic case and not the pessimistic one. Buys speed we do not need — Parakeet
on CPU already clears NFR-P-11 — in exchange for depending on BM-04's outcome.

### Everything on GPU — rejected

Does not fit under any assumption. Whisper large-v3 alone is ~3 GiB.

### Smaller LLM to make room — rejected *for now*

Qwen3.5-4B would free ~3 GiB, easily accommodating GPU-resident speech models.
But it costs argument quality (MMLU-Pro 82.5 → 79.1) to buy speed in components
that are already fast enough. Wrong trade **unless** BM-01 shows the 9B is too
slow — in which case the 4B swap happens for latency reasons and this ADR's
placement decision still holds.

### Reduce context to 8K — rejected as a first move

Frees 0.25 GiB. Kept as a contingency lever, not spent pre-emptively.

## Consequences

### Positive
- **Budget holds under the pessimistic assumption**: 6.86 + 0.80 = 7.66 GiB,
  leaving 0.34 GiB margin. The design does not depend on BM-04's result.
- No GPU contention; lower latency variance.
- Uses otherwise-wasted CPU capacity.
- Speech models can be swapped without any VRAM recalculation.
- If BM-04 is optimistic, the extra ~0.7 GiB becomes margin for 32K context or a
  better quant — real upside rather than a rescued constraint.

### Negative
- **CPU speech inference is slower than GPU.** Budgets get tighter: STT must hit
  RTF < 0.3 and TTS RTF < 0.5 (NFR-P-21, NFR-P-22).
- **Published CPU benchmarks come from idle machines.** Ours will be running an
  audio pipeline concurrently. This is the real risk —
  [RISK-06](../../06-governance/01-risk-register.md) — and BM-03 must measure
  **under concurrent GPU load**, not idle.
- The i7-13620H's hybrid P/E topology means thread placement matters; latency-
  critical work landing on E-cores runs measurably slower.
- Higher CPU load raises system temperature, and on a laptop that means fan
  noise — which reaches the microphone.

### Neutral
- Constrains us to CPU-viable speech models, which is what we chose anyway.

## Revisit when

- **BM-03 shows CPU RTF targets are missed under concurrent load.** Then either
  smaller speech models, or GPU placement contingent on a favourable BM-04.
- Hardware changes to ≥ 12 GB VRAM — at which point this entire constraint
  dissolves and speech models can go anywhere.
- We drop to Qwen3.5-4B for other reasons, freeing ~3 GiB.

## Verification

| ID | Measures |
|---|---|
| **BM-03** | Parakeet + Kokoro RTF on this CPU **during** LLM generation |
| **BM-04** | Actual free VRAM; which GPU drives the display |

Both run in [Phase 0](../../07-planning/01-roadmap.md), before implementation.

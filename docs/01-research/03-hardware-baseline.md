# Hardware Baseline

| | |
|---|---|
| **Status** | Measured 2026-08-30 |
| **Purpose** | Record the exact target machine, since nearly every design decision derives from it |

---

## 1. Measured configuration **[VERIFIED]**

Captured on the development machine.

### GPU

```
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 610.47
```

| | |
|---|---|
| Model | RTX 4060 **Laptop** GPU (Ada Lovelace) |
| VRAM | **8,188 MiB ≈ 8.0 GiB** |
| Driver | 610.47 |

> **A trap worth documenting.** Windows WMI reports this GPU as having 2 GB:
> ```
> Get-CimInstance Win32_VideoController  →  NVIDIA GeForce RTX 4060 Laptop GPU, VRAM_GB: 4.00
> ```
> `Win32_VideoController.AdapterRAM` is a 32-bit field and is unreliable for
> modern GPUs. **Always trust `nvidia-smi`.** Any capability check we write must
> use `nvidia-smi` or the NVML API, never WMI — a setup script that reads WMI
> will refuse to run on a perfectly capable machine.

**Laptop vs desktop matters.** The mobile RTX 4060 has a lower power envelope
and sustained clocks than its desktop namesake. Published desktop benchmarks are
an **upper bound**, not a prediction. Thermal throttling during a 60-minute
session is a genuine risk — [RISK-07](../06-governance/01-risk-register.md).

### Integrated GPU

```
Intel(R) UHD Graphics — driver 32.0.101.6733
```

This is a hybrid-graphics laptop. **[ASSUMED]** the display is driven by the
Intel iGPU, leaving the 4060's 8 GiB available to compute. If instead the
display runs on the 4060, expect **300–800 MiB** consumed by the desktop
compositor — which would eat most of our headroom.

**This must be verified**, not assumed: run `nvidia-smi` with the desktop idle
and check for non-zero baseline usage and any listed graphics processes.
Benchmark BM-04.

### CPU

| | |
|---|---|
| Model | 13th Gen Intel Core i7-13620H |
| Cores | 10 (6 Performance + 4 Efficiency) |
| Threads | 16 |

The hybrid P/E topology has a practical consequence: **thread affinity matters**.
Latency-critical work scheduled onto E-cores runs measurably slower. If STT or
TTS timings show unexplained variance, scheduler placement is a prime suspect.

### Memory & storage

| | |
|---|---|
| System RAM | 15.7 GiB |
| Model file | 5.56 GiB at `C:\local-models\` |

RAM is tighter than it looks. Windows takes 3–4 GiB, a browser takes 1–2 GiB, and
the model is memory-mapped during load. NFR-R-03 caps us at 10 GiB.

### Operating system & toolchain **[VERIFIED]**

| | |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13 (`AppData\Local\Programs\Python\Python313`) |
| Node.js | present |
| Git | present |
| Docker | present |
| FFmpeg | `C:\ffmpeg\bin\ffmpeg.exe` |
| **`uv`** | **MISSING** |

**Python 3.13 is a genuine risk.** ML wheels lag Python releases, and
`onnxruntime`, `silero-vad`, and audio libraries may not publish 3.13 wheels —
forcing source builds that need a C++ toolchain on Windows. **Mitigation: pin
the project to Python 3.11**, the version with the broadest ML wheel coverage.
[RISK-04](../06-governance/01-risk-register.md).

FFmpeg being present is convenient — several audio libraries want it on PATH.

---

## 2. Derived VRAM budget **[ESTIMATED]**

Full derivation: [Resource Budget](../02-architecture/08-resource-budget.md).

| Item | Size | Confidence |
|---|---|---|
| Qwen3.5-9B UD-Q4_K_XL weights | 5.56 GiB | **[VERIFIED]** |
| llama.cpp CUDA backend overhead | ~0.70 GiB | **[SOURCED]** |
| KV cache @ 16K, FP16, 8 attn layers | ~0.50 GiB | **[ESTIMATED]** |
| DeltaNet recurrent state | ~0.10 GiB | **[ESTIMATED]** |
| **LLM subtotal** | **~6.86 GiB** | |
| Windows/display reserve | ~0.10–0.80 GiB | **[ASSUMED]** |
| **Remaining** | **~0.3–1.1 GiB** | |

**The spread on that last row is the whole problem.** Whether we have 1.1 GiB or
0.3 GiB of headroom depends entirely on the iGPU assumption above. Under the
pessimistic case, nothing else fits on the GPU at all.

This uncertainty is the reason
[ADR-0004](../02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md) places
STT and TTS on the **CPU** rather than trying to squeeze them into headroom that
may not exist. It converts a risky assumption into a non-issue.

---

## 3. CPU capacity for speech models

The argument for CPU placement rests on a load asymmetry that is easy to miss:

**llama.cpp with `-ngl 99` leaves the CPU nearly idle.** All 32 layers execute on
the GPU; the CPU only marshals requests and moves tokens. During the LLM's
5-second generation burst, **16 threads sit unused.**

That is free capacity already paid for. Published figures suggest it is enough:

| Workload | Reported | Source |
|---|---|---|
| Parakeet TDT on CPU | ~4× faster than Whisper | **[SOURCED]** |
| Kokoro-82M on CPU | Faster than real-time | **[SOURCED]** |

Both must clear RTF < 1.0 (NFR-P-21, NFR-P-22) or their queues grow without
bound. Benchmark BM-03 verifies this **on this CPU**, under concurrent LLM load
— not idle, since scheduler contention is exactly what a naive benchmark misses.

---

## 4. Thermal and power

Laptop-specific concerns absent from desktop guidance:

| Concern | Impact | Mitigation |
|---|---|---|
| Sustained GPU thermal throttling | Token rate decays over a long session | Log tok/s per turn; watch for downward drift (NFR-REL-01) |
| Power profile | Battery mode caps clocks hard | Document: mains power required |
| CPU/GPU thermal coupling | Shared cooling; CPU-side STT/TTS raises GPU temps | Measure under combined load in BM-03 |
| Fan noise | **Enters the microphone** | Real for a voice product; assess during BM-03. Partly mitigated by the browser's noise suppression ([ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md)) |
| Speaker↔mic coupling | Laptop speakers and the built-in array sit centimetres apart — the worst case for AEC | [RISK-12](../06-governance/01-risk-register.md); measured in BM-05 |

> The fan-noise item is not a joke. A laptop under sustained GPU load runs its
> fans audibly, the microphone is centimetres away, and that noise raises WER and
> can trip VAD. It is a legitimate reason to prefer a headset microphone.

---

## 5. Minimum and recommended specification

For [Installation Guide](../05-operations/01-installation-guide.md) and any
future portability work.

### Minimum (as designed)

| | |
|---|---|
| GPU | NVIDIA, **8 GB VRAM**, CUDA compute ≥ 8.9 |
| CPU | 8 cores / 12 threads |
| RAM | 16 GB |
| Disk | 15 GB free |
| OS | Windows 11 |
| Python | 3.11 |
| Browser | Chrome / Edge — **required**, carries the audio path ([ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md)) |
| Audio | Microphone + speakers *or* headphones |

### Recommended

| | |
|---|---|
| GPU | 12 GB+ VRAM — removes the constraint driving most of this design |
| RAM | 32 GB |
| Audio | External microphone positioned **away from the speakers** — the single biggest physical improvement to echo cancellation |

With 12 GB the whole architecture relaxes: speech models could go on the GPU,
context could reach 32K, and a larger quant would fit. **Nearly every departure
from mainstream practice in this project would become unnecessary.** Worth
recording plainly, so a future reader on better hardware does not inherit our
constraints as though they were principles.

---

## 6. What must be measured before building

| ID | Measurement | Gates |
|---|---|---|
| **BM-01** | Tokens/sec and TTFT for the 9B at 8K/16K/32K | NFR-P-20, the entire latency design |
| **BM-02** | Prefix-cache effectiveness across turns | NFR-P-12 |
| **BM-03** | Parakeet + Kokoro RTF on this CPU, under concurrent GPU load | NFR-P-21, NFR-P-22 |
| **BM-04** | Actual free VRAM with desktop idle; confirm iGPU drives display | The entire resource budget |
| **BM-05** | Echo cancellation and double-talk with this machine's speakers and mic | Barge-in (NFR-A-05, NFR-A-06) |

Details in [Benchmark Plan](../04-quality/03-benchmark-plan.md).

**No implementation should begin before these run.** The design is internally
consistent but rests on published numbers from other people's machines. Four
measurements convert the foundation from inference to fact — and if BM-01 comes
back at 15 tok/s, the correct response is to change the design, not to discover
that during integration.

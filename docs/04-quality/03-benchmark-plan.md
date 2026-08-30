# Benchmark Plan — Phase 0

| | |
|---|---|
| **Status** | **Not yet run** |
| **Last updated** | 2026-08-30 |
| **Gates** | All implementation work |

---

## 1. Why this comes first

Every performance and resource figure in this documentation set is
**[SOURCED]** from third-party benchmarks or **[ESTIMATED]** by arithmetic.
Nothing has been measured on the target machine.

The design is internally consistent. That is not the same as being true.

> If [BM-01](#bm-01) returns 15 tok/s instead of 30, NFR-P-01 is unreachable and
> the correct response is **to change the design** — swap to Qwen3.5-4B — not to
> discover it three weeks into implementation and try to optimise around it.

Five measurements, roughly two days' work, convert the foundation from inference
to fact. They run **before any application code is written**
([Repository Structure §2.4](../03-engineering/01-repository-structure.md)).

---

## 2. Benchmark index

| ID | Measures | Gates | Est. |
|---|---|---|---|
| [BM-01](#bm-01) | LLM throughput and TTFT | The entire latency design | 2 h |
| [BM-02](#bm-02) | Prefix cache effectiveness | NFR-P-12, speculative prefill | 2 h |
| [BM-03](#bm-03) | CPU speech RTF under GPU load | [ADR-0004](../02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md) |  3 h |
| [BM-04](#bm-04) | Real VRAM profile | The whole resource budget | 1 h |
| [BM-05](#bm-05) | **Echo cancellation with speakers** | Barge-in, [ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md) | 2 h |

Results are written to `benchmarks/results/` and **committed** — they are the
evidence base that converts this design's assumptions into verified facts.

---

## BM-01 — LLM throughput and latency {#bm-01}

### Question
Can Qwen3.5-9B UD-Q4_K_XL sustain ≥ 25 tok/s with TTFT ≤ 400 ms on this RTX 4060?

### Why it matters
**[SOURCED]** figures put a 9B Q4 at 25–35 tok/s on this GPU class — but those
are *desktop* 4060 numbers, and this is a **laptop** 4060 with a lower power
envelope and lower sustained clocks. The published number is an upper bound, not
a prediction.

At 30 tok/s a 150-token response takes 5 s to generate — hidden behind 40 s of
playback. At 15 tok/s it takes 10 s, generation starts losing to playback, and
the agent stutters mid-argument.

### Method

```powershell
.\llama-server.exe -m C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf `
  -ngl 99 -c 16384 -fa --host 127.0.0.1 --port 8080
```

**Verify in the load log:** `offloaded 33/33 layers to GPU`, and **no `mmproj`**.
Anything less than full offload invalidates the run
([Resource Budget §6](../02-architecture/08-resource-budget.md)).

For each context size {4K, 8K, 16K, 32K} and each prompt length {500, 2000, 8000
tokens}, run 20 generations of ~200 tokens with production sampling parameters
([Model Analysis §5.2](../01-research/02-model-analysis.md)), and record:

- TTFT (p50, p95)
- tokens/sec, sustained
- prefill tokens/sec
- VRAM (`nvidia-smi` sampled at 1 Hz)
- GPU temperature and clock

Then a **thermal run**: 30 minutes of continuous generation, watching for
tokens/sec decay.

### Pass criteria

| Metric | Pass | Marginal | Fail |
|---|---|---|---|
| Sustained tok/s @ 16K | ≥ 25 | 18–25 | < 18 |
| TTFT p50, 2K prompt | ≤ 400 ms | 400–700 | > 700 |
| tok/s decay over 30 min | < 10% | 10–20% | > 20% |

### If it fails

| Result | Action |
|---|---|
| 18–25 tok/s | Shorten `max_tokens` to 150; re-evaluate |
| < 18 tok/s | **Switch to Qwen3.5-4B.** MMLU-Pro 82.5 → 79.1, roughly 2× throughput. |
| Thermal decay > 20% | Investigate cooling; document mains-power requirement; consider a laptop cooling pad |
| Partial offload only | Reduce context to 8K, re-run |

---

## BM-02 — Prefix cache effectiveness {#bm-02}

### Question
Does `llama-server` reuse the KV cache across turns on this **hybrid DeltaNet**
architecture?

### Why it matters
This is the **highest-uncertainty item in the entire design**.

Prefix caching is trivial for pure attention: unchanged prefix, reuse the KV.
Qwen3.5-9B has 24 linear-attention layers with *recurrent state*, which requires
checkpointing rather than simple reuse. llama.cpp implements this via
`llama_memory_hybrid` (`cache_r_l*` / `cache_s_l*`), but whether it is as
effective as for a standard model is **unverified**.

> If prefix caching does not work, **every turn re-prefills the entire
> conversation**. At turn 20 that is ~3,000 tokens of prefill before a single
> output token — pushing TTFT into multiple seconds and making NFR-P-01
> unreachable. It would also eliminate speculative prefill
> ([Latency Budget §5](../02-architecture/07-latency-budget.md)), our largest
> planned optimisation.
>
> This is [OQ-03](../06-governance/05-open-questions.md) and
> [RISK-03](../06-governance/01-risk-register.md).

### Method

Simulate a 20-turn conversation. Each turn appends to a growing message list and
requests 50 tokens. Record TTFT per turn.

Then repeat with a deliberately **perturbed system prompt** each turn (one
changed character), forcing a cache miss, to establish the uncached baseline.

Also test **speculative prefill**: send the partial context with `max_tokens: 0`,
then the full request, and measure the TTFT difference.

### Pass criteria

| Observation | Meaning |
|---|---|
| TTFT roughly flat across turns 1→20 | **Caching works.** Speculative prefill is viable. |
| TTFT grows linearly with turn number | **Caching is not working.** Design change required. |
| Cached vs perturbed differ by > 2× | Confirms cache is active |

### If it fails

1. Check for a llama.cpp flag governing hybrid-state caching.
2. Reduce context to 8K to cap worst-case prefill.
3. Compact history far more aggressively (shorter effective prefix).
4. Abandon speculative prefill; re-derive the latency budget without it.
5. If TTFT exceeds ~1.5 s at turn 20, reconsider the model — a non-hybrid
   architecture with working prefix caching may beat a better model that
   re-prefills every turn.

---

## BM-03 — CPU speech performance under load {#bm-03}

### Question
Do Parakeet and Kokoro meet their RTF targets on this CPU **while the GPU is
generating**?

### Why it matters
[ADR-0004](../02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md) puts all
speech models on the CPU. Published figures support this — but **published CPU
benchmarks come from idle machines.**

Ours will be running an audio pipeline, a Python event loop, and marshalling for
`llama-server` concurrently. This benchmark must run **under concurrent GPU
load**, not idle. An idle-machine measurement here would be reassuring and
worthless.

Three sub-questions:

1. **RTF under contention** — NFR-P-21 (STT < 0.3), NFR-P-22 (TTS < 0.5)
2. **Kokoro short-text penalty** — **[SOURCED]** ONNX is slower than PyTorch on
   tiny inputs (RTF 0.72 vs 0.49), and we deliberately emit short units
   ([ADR-0006](../02-architecture/adr/0006-kokoro-for-tts.md))
3. **GIL behaviour** — does ONNX Runtime genuinely release the GIL, so
   `asyncio.to_thread` parallelises?
   ([ADR-0009](../02-architecture/adr/0009-python-as-orchestration-language.md))

### Method

Background: continuous LLM generation on the GPU.

Foreground, measured:

| Sub-test | Input | Metric |
|---|---|---|
| STT-1 | 5 s utterance | RTF, wall-clock |
| STT-2 | 20 s utterance | RTF |
| STT-3 | 10 s silence | **Output must be empty** (NFR-A-02) |
| TTS-1 | 15-char unit | TTFB, RTF |
| TTS-2 | 40-char unit | TTFB, RTF |
| TTS-3 | 120-char sentence | TTFB, RTF |
| TD-1 | Partial transcript | Inference ms (NFR-P-10) |
| GIL-1 | 20 ms audio frames during inference | **Dropped-frame count** |

Repeat at `num_threads` = 4, 6, 8 to find the P-core sweet spot.

### Pass criteria

| Metric | Pass |
|---|---|
| STT RTF under load | ≤ 0.3 |
| STT output on silence | **0 words** |
| TTS RTF, 40+ chars | ≤ 0.5 |
| TTS TTFB, 15-char unit | ≤ 150 ms |
| Turn detection | ≤ 150 ms |
| **Dropped audio frames** | **0** |

### GIL-1 is the important one

> If audio frames drop during CPU inference, the GIL is not being released and
> [ADR-0009](../02-architecture/adr/0009-python-as-orchestration-language.md)'s
> central assumption is wrong. Consequence: move inference to a subprocess, or in
> the extreme reconsider the orchestration language — the most expensive
> reversal in the entire design.
>
> This is why it is measured now rather than discovered later.

### If it fails

| Result | Action |
|---|---|
| STT RTF > 0.3 | faster-whisper small.en, or a smaller Parakeet |
| TTS TTFB > 150 ms on short units | Raise `min_unit_chars`; or Piper |
| Frames dropped | Subprocess isolation for inference |
| Turn detection > 150 ms | Punctuation heuristic ([ADR-0007](../02-architecture/adr/0007-two-layer-turn-detection.md)) |

---

## BM-04 — VRAM profile {#bm-04}

### Question
How much VRAM is actually free, and does the Intel iGPU drive the display?

### Why it matters
[Resource Budget §3](../02-architecture/08-resource-budget.md) shows headroom of
**either ~1.04 GiB or ~0.34 GiB** depending entirely on this. It is the largest
single unknown in the resource model.

It also validates the KV-cache arithmetic — a clean check on whether the
per-token derivation from the model card is right.

### Method

1. **Desktop idle**, nothing running:
   ```powershell
   nvidia-smi --query-gpu=memory.used,memory.total --format=csv
   nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv
   ```
   Also check whether the display is attached to the 4060.

2. Load `llama-server` at `-c` = 4K, 8K, 16K, 32K; record VRAM after each.

3. Compute measured KV growth per token; compare against the predicted **32
   KiB/token**.

4. Sample VRAM at 1 Hz across a 60-minute session (NFR-REL-05 leak check).

### Pass criteria

| Metric | Pass |
|---|---|
| Idle VRAM used | ≤ 300 MiB (iGPU drives display) |
| VRAM @ 16K after load | ≤ 7,000 MiB |
| Measured KV/token | within 20% of 32 KiB |
| VRAM growth over 60 min | < 100 MiB |

### If it fails

| Result | Action |
|---|---|
| Idle > 800 MiB | Force display to iGPU in Windows graphics settings |
| VRAM @16K > 7,000 MiB | Drop to 8K context |
| KV/token far above prediction | Re-derive §2.2 of the Resource Budget; the model card reading may be wrong |
| Growth > 100 MiB/hour | Leak — investigate before building further |

---

## BM-05 — Echo cancellation with speakers {#bm-05}

### Question
With laptop speakers and the built-in microphone, does the browser's AEC (a)
prevent the agent triggering itself, and (b) **preserve the user's speech during
double-talk**?

### Why it matters
The user has confirmed **speakers**
([OQ-01 closed](../06-governance/05-open-questions.md)), making AEC mandatory
rather than avoidable ([ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md)).

Two failure directions, and they are not equally likely or equally bad:

| Failure | Symptom | Likelihood |
|---|---|---|
| Under-cancellation | Agent interrupts itself indefinitely | Lower — AEC3 is good |
| **Over-suppression** | **Agent cannot be interrupted at all** | **Higher, and worse** |

> A canceller that works when only one party speaks is easy and useless. Barge-in
> is **by definition double-talk** — the hardest case for AEC. Measuring only the
> silent-user case would look excellent and tell us nothing.

This is [RISK-12](../06-governance/01-risk-register.md) and
[OQ-09](../06-governance/05-open-questions.md).

### Method

A minimal browser page: `getUserMedia` with `echoCancellation: true`, streaming
mic audio to Python, playing TTS audio back through the page.

| Sub-test | Setup | Metric |
|---|---|---|
| **AEC-1** | Agent speaks 5 min, user silent, typical volume | **Self-trigger count — must be 0** |
| **AEC-2** | Same, at high volume | Self-trigger count |
| **AEC-3** | **User speaks over the agent, 20 trials** | **Was user speech transcribed correctly?** |
| AEC-4 | AEC-3 with an external mic away from speakers | Improvement delta |
| AEC-5 | AEC-3 with Windows *Communications* device enrolment | Improvement delta |
| AEC-6 | Measure added round-trip latency vs native audio | ms (budgeted 40) |

### Pass criteria

| Metric | Pass |
|---|---|
| Self-triggers over 5 min, user silent | **0** |
| Double-talk: user speech transcribed | **≥ 18 of 20 trials** |
| WER during double-talk | ≤ 20% (degradation is expected; loss is not) |
| WebRTC added latency | ≤ 60 ms |

### If it fails

| Result | Action |
|---|---|
| Self-triggers > 0 | Lower output volume; raise `vad.threshold`; enrol as Communications device |
| Double-talk loses user speech | External microphone (AEC-4 quantifies the gain); if still failing, **push-to-talk becomes the default** and barge-in is documented as requiring headphones |
| Latency > 60 ms | Re-derive the latency budget; consider reducing the output buffer |

> **The honest fallback is push-to-talk.** If double-talk cannot be made to work
> on this hardware, the correct response is to ship push-to-talk as the default
> and tell the user that barge-in requires headphones — not to ship an agent that
> cannot be interrupted while pretending it can.

---

## 3. Reporting

One Markdown file per benchmark in `benchmarks/results/`:

```markdown
# BM-01 — LLM throughput
Date · Hardware · llama.cpp build · Model file hash
## Results
<tables, plots>
## Verdict
PASS / MARGINAL / FAIL
## Consequences for the design
<which documents must change, and how>
```

**The final section is the point.** A benchmark that produces numbers nobody
acts on is wasted. Each result must either confirm a design assumption — at which
point the corresponding **[SOURCED]** or **[ESTIMATED]** markers in the affected
documents are upgraded to **[VERIFIED]** — or trigger a specific documented change.

---

## 4. Exit criteria for Phase 0

Implementation begins when:

- [ ] BM-01 through BM-05 have run
- [ ] Results are committed to `benchmarks/results/`
- [ ] Every FAIL has a decided and documented response
- [ ] [Latency Budget](../02-architecture/07-latency-budget.md) and
      [Resource Budget](../02-architecture/08-resource-budget.md) are updated
      with measured values
- [ ] Confidence markers are upgraded where measurement supports it
- [ ] [Risk Register](../06-governance/01-risk-register.md) is updated —
      RISK-01, 02, 03, 06 should all be resolved or re-scored

**Estimated: 1–2 days.** Against the cost of discovering a fundamental
performance problem three weeks into implementation, this is cheap.

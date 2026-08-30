# Risk Register

| | |
|---|---|
| **Status** | Live — re-score at every milestone |
| **Last updated** | 2026-08-30 |

---

## Scoring

**Likelihood** × **Impact**, each 1–5. Score ≥ 12 requires an active mitigation
before proceeding.

| Impact | Meaning |
|---|---|
| 5 | Project not viable as designed |
| 4 | Major redesign of a subsystem |
| 3 | Significant rework |
| 2 | Noticeable quality loss |
| 1 | Minor inconvenience |

---

## Active risks

### RISK-01 — llama.cpp support for the hybrid architecture is recent
| L | I | Score | Owner |
|---|---|---|---|
| 2 | 5 | **10** | Amin |

**Description.** Qwen3.5-9B uses a hybrid Gated DeltaNet + attention graph.
**[SOURCED]** as of ~May 2026 llama.cpp support was described as bleeding-edge
HEAD rather than stable release; by August 2026 it is first-class (the README
leads with `llama serve -hf ggml-org/Qwen3.5-0.8B-GGUF`). The implementation is
still newer than the standard transformer path.

**If it materialises.** The model cannot be served, or is served with subtle
correctness problems. Blocking.

**Mitigation**
- Verify with a recent build in [BM-01](../04-quality/03-benchmark-plan.md) —
  **this is the single first action of the project**
- Pin the working llama.cpp build; do not upgrade casually
- Fallback: a non-hybrid model of similar size

**Retires when:** BM-01 passes.

---

### RISK-02 — LLM throughput below target
| L | I | Score |
|---|---|---|
| 3 | 4 | **12** ⚠ |

**Description.** The design assumes ≥ 25 tok/s. **[SOURCED]** figures of 25–35
tok/s are for **desktop** RTX 4060s; ours is a **laptop** variant with lower
power limits and sustained clocks. The published number is an upper bound.

**If it materialises.** Below ~18 tok/s, generation cannot outrun playback,
NFR-P-01 is unreachable, and the agent stutters mid-argument.

**Mitigation**
- BM-01 measures it before implementation
- **Primary remedy: Qwen3.5-4B** — roughly 2× throughput, MMLU-Pro 82.5 → 79.1.
  A survivable loss for a debate partner, where argumentative structure matters
  more than knowledge depth.
- Secondary: shorter `max_tokens`; filler acknowledgement (FR-15)

**Retires when:** BM-01 confirms ≥ 25 tok/s sustained.

---

### RISK-03 — Prefix caching ineffective on hybrid architecture
| L | I | Score |
|---|---|---|
| 3 | 4 | **12** ⚠ |

**Description.** 24 of 32 layers carry *recurrent state*, not a KV cache. Reusing
a conversation prefix requires state checkpointing, which llama.cpp implements
via `llama_memory_hybrid` — but whether it is as effective as for a standard
transformer is **unverified**.

**If it materialises.** Every turn re-prefills the whole conversation. At turn 20
that is ~3,000 tokens before the first output token, pushing TTFT to multiple
seconds. It also eliminates speculative prefill
([Latency Budget §5](../02-architecture/07-latency-budget.md)), our largest
planned optimisation.

**Mitigation**
- [BM-02](../04-quality/03-benchmark-plan.md) measures it directly
- Keep the system prompt byte-identical within a session
- Reduce context to 8K to cap worst-case prefill
- Instrument `prefix_cache_hit` per turn in production

**Retires when:** BM-02 shows flat TTFT across 20 turns.

**Related:** [OQ-03](05-open-questions.md).

---

### RISK-04 — Windows dependency hell
| L | I | Score |
|---|---|---|
| 3 | 3 | **9** |

**Description.** **[VERIFIED]** the dev machine runs Python 3.13. ML wheels lag
Python releases; on Windows a missing wheel means a source build requiring MSVC
tooling, which frequently fails.

**Mitigation**
- **Pin to Python 3.11**
  ([ADR-0009](../02-architecture/adr/0009-python-as-orchestration-language.md))
- Commit `uv.lock`
- Prefer `onnx-asr` over PyTorch-based stacks
  ([ADR-0005](../02-architecture/adr/0005-parakeet-tdt-for-stt.md))
- Install VC++ redistributable as an explicit setup step

**Retires when:** a clean-machine install succeeds end to end.

---

### RISK-05 — Turn detection feels wrong despite passing tests
| L | I | Score |
|---|---|---|
| 4 | 3 | **12** ⚠ |

**Description.** Turn detection can meet its numeric targets and still feel bad.
The metrics are aggregate; the experience is per-instance, and one badly-timed
interruption in a session is memorable in a way a 4% error rate is not.

**Worse for this product than most.** In debate, being cut off mid-thought reads
as *rudeness* — a character defect in the opponent — rather than as a technical
glitch.

**Mitigation**
- Fixtures recorded from **real argumentative speech**, not read sentences
- Asymmetric targets: false cuts (5%) held tighter than false holds (10%)
- **Push-to-talk escape hatch is P1** (FR-43), not P2
- Two documented model fallbacks
  ([ADR-0007](../02-architecture/adr/0007-two-layer-turn-detection.md))

**Retires when:** 10 real sessions with no reported interruption complaint.

---

### RISK-06 — CPU speech models miss RTF under concurrent load
| L | I | Score |
|---|---|---|
| 3 | 3 | **9** |

**Description.** [ADR-0004](../02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md)
puts all speech models on the CPU based on **[SOURCED]** benchmarks — **taken on
idle machines**. Ours runs an audio pipeline and Python event loop concurrently.

**If it materialises.** RTF > 1.0 means queues grow without bound and the system
falls progressively further behind for the entire session.

**Mitigation**
- [BM-03](../04-quality/03-benchmark-plan.md) measures **under concurrent GPU
  load**, not idle
- Fallbacks: faster-whisper small.en, Piper
- Thread count tunable; cap to P-cores on the hybrid CPU

**Retires when:** BM-03 confirms STT RTF < 0.3 and TTS RTF < 0.5 under load.

---

### RISK-07 — Laptop thermal throttling
| L | I | Score |
|---|---|---|
| 3 | 2 | **6** |

**Description.** Sustained GPU load on a laptop throttles. A 60-minute session
may degrade progressively.

**Secondary effect worth naming:** fans under load are audible, the microphone is
centimetres away, and this raises transcription error rates. A real problem for a
voice product.

**Mitigation**
- BM-01 includes a 30-minute thermal run
- `tokens_per_sec` logged per turn; drift is detectable
- Document mains-power requirement
- Recommend a headset boom microphone over the built-in array

**Retires when:** IT-07 soak shows < 10% decay.

---

### RISK-08 — Sycophancy defeats the product
| L | I | Score |
|---|---|---|
| 4 | 5 | **20** ⚠⚠ |

> **The highest-scored risk in the register, and the one least addressable by
> engineering.**

**Description.** Instruction-tuned models are trained toward agreeableness. The
debate persona asks the model to resist that training for twenty consecutive
turns, under direct social pressure from the user.

**If it materialises.** Every test passes. Latency is excellent. VRAM is fine.
**And the product is worthless**, because an opponent that folds teaches nothing.

**Mitigation**
- Explicit prohibitions in the prompt
  ([Prompt Spec §7](../03-engineering/05-prompt-engineering-spec.md))
- **Probes P-01 and P-02 are release gates**, run against every prompt version
- `presence_penalty: 1.5` discourages drift into agreement
- Prompt versioning so regressions are attributable
- Expect several iterations; this is not a one-shot fix

**Retires when:** three consecutive prompt versions pass P-01 and P-02, and five
real sessions report no capitulation.

---

### RISK-09 — Persuasive fabrication harms the user
| L | I | Score |
|---|---|---|
| 3 | 5 | **15** ⚠ |

**Description.** Research demonstrates that
[persuasion overrides truth](https://arxiv.org/html/2504.00374v1) in LLM debate
— confident, fluent arguments win regardless of correctness. A 9B model will be
wrong about facts.

**If it materialises.** The tool actively degrades the user's thinking while
feeling like it sharpens it. This is the **product's harm case**, not merely a
quality issue.

**Mitigation**
- Fabrication explicitly prohibited (FR-28)
- Uncertainty marking required (FR-26)
- **Probe P-04 is a release gate**
- "Winning" is an explicit anti-goal
- Transcripts enable later review with a clear head
- v2: claim extraction for deliberate scrutiny

**Residual risk is real.** Self-evaluation is structurally incapable of detecting
sophisticated persuasion harm — if the agent is convincingly talking the user out
of correct positions, the user is by construction the last to notice. Recorded
as an accepted limitation in
[Responsible AI](04-responsible-ai.md) and
[Evaluation Framework §6](../04-quality/02-evaluation-framework.md).

**Retires:** never fully. Managed, not closed.

---

### RISK-10 — Scope creep into an assistant
| L | I | Score |
|---|---|---|
| 3 | 3 | **9** |

**Description.** Once a working voice pipeline exists, adding assistant features
is easy and feels like progress. Each dilutes the single thing this does.

**Mitigation**
- [Vision & Scope §5](../00-product/01-vision-and-scope.md) lists exclusions
  explicitly
- Anti-goals stated (§7)
- New capability requires an ADR

**Retires when:** v1.0 ships within its stated scope.

---

### RISK-11 — Barge-in history truncation implemented incorrectly
| L | I | Score |
|---|---|---|
| 3 | 3 | **9** |

**Description.** FR-13 requires history to record what was *spoken*, not what was
*generated*. This passes trivially in a non-streaming design and fails silently
in a streaming one.

**Symptom appears far from the cause:** the agent references arguments the user
never heard, many turns later, reading as fabrication.

**Mitigation**
- Invariant I-3 asserted after every simulated barge-in
- Dedicated unit tests, called out as the highest-value tests in the suite
- `text_spoken` / `text_generated` stored separately, making divergence auditable
- The `AudioChunk.text_span` contract specified precisely
  ([Internal API Spec §D](../02-architecture/05-internal-api-spec.md))

**Retires when:** IT-02 passes and invariant I-3 holds across the soak test.

---

### RISK-12 — Acoustic echo cancellation fails during double-talk
| L | I | Score |
|---|---|---|
| 3 | 4 | **12** ⚠ |

**Created by:** the OQ-01 resolution to **speakers**
([ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md)).

**Description.** With speakers, the browser's AEC must suppress the agent's own
output from the microphone. It is hardest during **double-talk** — the user
speaking over the agent, which is exactly barge-in. The characteristic failure
is suppressing the user's speech along with the echo.

**The hardware is the worst case.** Laptop speakers and a built-in microphone
array sit centimetres apart with tight acoustic coupling, and the array performs
its own beamforming and noise processing, which can confuse the canceller by
altering the signal it is trying to model.

**If it materialises.** Either the agent interrupts itself indefinitely
(insufficient cancellation), or it cannot be interrupted at all (over-suppression
of the user). The second is more likely with a good canceller and is the more
damaging — barge-in is P0, and an uninterruptible opponent is a materially worse
product.

**Mitigation**
- **[BM-05](../04-quality/03-benchmark-plan.md)** measures double-talk directly,
  before barge-in is built
- Browser AEC3 is the most battle-tested implementation available
- Windows *Communications* device enrolment adds a second layer
- First-run calibration: play a tone, measure echo return loss, warn on poor
  acoustics — turns a mystifying failure into a diagnosed one
- Recommend an external microphone positioned away from the speakers
- Push-to-talk (FR-43) is the fallback if AEC proves unworkable

**Retires when:** BM-05 confirms user speech survives during agent playback, and
IT-02 barge-in passes with speakers active.

**Related:** [OQ-09](05-open-questions.md).

---

## Summary

| ID | Risk | Score | Status |
|---|---|---|---|
| **RISK-08** | Sycophancy defeats the product | **20** | Open — mitigations designed |
| **RISK-09** | Persuasive fabrication harms the user | **15** | Open — managed, never closed |
| RISK-02 | LLM throughput below target | 12 | Open — BM-01 |
| RISK-03 | Prefix caching ineffective | 12 | Open — BM-02 |
| RISK-05 | Turn detection feels wrong | 12 | Open — fixtures + escape hatch |
| **RISK-12** | **AEC fails during double-talk** | **12** | **Open — BM-05** (new, from OQ-01) |
| RISK-01 | llama.cpp support recent | 10 | Open — BM-01 |
| RISK-04 | Windows dependency hell | 9 | Mitigated — Python 3.11 pin |
| RISK-06 | CPU speech RTF under load | 9 | Open — BM-03 |
| RISK-10 | Scope creep | 9 | Mitigated — documented scope |
| RISK-11 | Barge-in truncation wrong | 9 | Mitigated — invariant + tests |
| RISK-07 | Thermal throttling | 6 | Open — BM-01 thermal run |

### The shape of this register

**Five of the top seven risks are retired by Phase 0 benchmarks** — a couple of
days of measurement collapses most of the technical uncertainty in the project.
That is the argument for running them before writing any application code.

**The top two cannot be retired by measurement.** RISK-08 and RISK-09 are about
model behaviour and human epistemics, not engineering. They are managed through
prompt iteration, release gates, and honesty about what the evaluation framework
cannot see. They are also, not coincidentally, the risks that determine whether
the product is worth building at all.

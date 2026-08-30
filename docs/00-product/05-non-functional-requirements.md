# Non-Functional Requirements

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |
| **Related** | [Latency Budget](../02-architecture/07-latency-budget.md) · [Resource Budget](../02-architecture/08-resource-budget.md) |

---

## 1. Performance

### 1.1 Conversational latency

Measured **mouth-to-ear**: from the acoustic end of the user's final word to the
first sample of agent audio reaching the output device. This is the only metric
that matches what a user perceives; component-level timings are diagnostic, not
targets in themselves.

| ID | Metric | Target | Ceiling | Basis |
|---|---|---|---|---|
| **NFR-P-01** | Turn latency, median | ≤ 1,200 ms | 1,500 ms | Industry budgets put the noticeable-lag threshold near 800 ms; 1,115 ms is a published production median **[SOURCED]** |
| **NFR-P-02** | Turn latency, P95 | ≤ 2,000 ms | 2,500 ms | Tail matters more than median for perceived quality |
| **NFR-P-03** | Barge-in stop latency | ≤ 300 ms | 500 ms | P50 ~300 ms is reported as acceptable in production **[SOURCED]** |
| **NFR-P-04** | Barge-in *detection* latency | ≤ 200 ms | — | VAD onset detection only |
| **NFR-P-05** | State indicator update | ≤ 100 ms | — | UI responsiveness floor |

> **A deliberate relaxation.** 1,200 ms is looser than a customer-service agent
> would target. Debate tolerates — arguably rewards — a beat of consideration
> before a rebuttal. Instant responses read as glib. We are not chasing 500 ms,
> and that choice buys us headroom elsewhere.

### 1.2 Component budgets

Derived from NFR-P-01. Full derivation in
[Latency Budget](../02-architecture/07-latency-budget.md).

| ID | Stage | Budget |
|---|---|---|
| **NFR-P-10** | Semantic turn detection | ≤ 150 ms |
| **NFR-P-11** | STT, final transcription of a committed turn | ≤ 250 ms |
| **NFR-P-12** | LLM time-to-first-token (warm prefix) | ≤ 400 ms |
| **NFR-P-13** | TTS time-to-first-audio-byte | ≤ 150 ms |
| **NFR-P-14** | Audio output buffer | ≤ 100 ms |
| **NFR-P-15** | WebRTC transport, round trip | ≤ 60 ms (budgeted 40) |

### 1.3 Throughput

| ID | Metric | Target | Basis |
|---|---|---|---|
| **NFR-P-20** | LLM generation | ≥ 25 tok/s sustained | **[SOURCED]** for 9B Q4 on RTX 4060; **must be reproduced** — BM-01 |
| **NFR-P-21** | STT real-time factor | ≤ 0.3× on CPU | Must transcribe faster than speech arrives |
| **NFR-P-22** | TTS real-time factor | ≤ 0.5× on CPU | Must synthesise faster than playback consumes |

> **NFR-P-21 and P-22 are correctness constraints, not performance goals.** An
> RTF above 1.0 means the queue grows without bound and the system falls
> progressively further behind for the whole session.

---

## 2. Resource constraints

Hard limits imposed by the target machine. See
[Resource Budget](../02-architecture/08-resource-budget.md).

| ID | Resource | Limit | Notes |
|---|---|---|---|
| **NFR-R-01** | Total VRAM | ≤ 7.5 GiB of 8.0 GiB | 0.5 GiB reserved for OS/display |
| **NFR-R-02** | LLM VRAM (weights + cache + overhead) | ≤ 7.0 GiB | All 32 layers on GPU; **no CPU spillover** |
| **NFR-R-03** | System RAM | ≤ 10 GiB of 15.7 GiB | Leaves room for the OS and a browser |
| **NFR-R-04** | STT + TTS + turn detection VRAM | 0 GiB | All CPU-resident — [ADR-0004](../02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md) |
| **NFR-R-05** | Model load time from cold | ≤ 60 s | Warm (page cache) should be ≤ 15 s |
| **NFR-R-06** | Disk footprint, models | ≤ 8 GiB | LLM 5.6 + STT ~0.7 + TTS ~0.4 |

> **NFR-R-02 is not negotiable.** Partial GPU offload does not degrade
> throughput gracefully — it collapses it, because every token then waits on
> PCIe transfers. The system is either fully offloaded or unusable. This is why
> [ADR-0004](../02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md) moves
> speech models off the GPU rather than squeezing them in beside the LLM.

---

## 3. Reliability

| ID | Requirement | Target |
|---|---|---|
| **NFR-REL-01** | Sustained session without degradation | ≥ 60 minutes |
| **NFR-REL-02** | Crash-free session rate | ≥ 95% over 20 sessions |
| **NFR-REL-03** | Transcript durability | No committed turn lost, even on hard kill |
| **NFR-REL-04** | Recovery from component failure | Session survives a single-stage failure and reports it |
| **NFR-REL-05** | Memory stability | No unbounded growth in RAM or VRAM across a 60-min session |

**NFR-REL-05** deserves attention: streaming audio pipelines leak buffers
readily, and the symptom (gradual slowdown, then OOM at minute 45) is
indistinguishable from many other faults. Explicit soak testing is specified in
the [Test Strategy](../04-quality/01-test-strategy.md).

---

## 4. Accuracy

| ID | Metric | Target | Notes |
|---|---|---|---|
| **NFR-A-01** | STT word error rate, quiet room | ≤ 10% | Argument content must survive |
| **NFR-A-02** | STT hallucination rate in silence | ~0 | Phantom text corrupts argument history — see [ADR-0005](../02-architecture/adr/0005-parakeet-tdt-for-stt.md) |
| **NFR-A-03** | Turn-detection false-cut rate | ≤ 5% | Cutting the user off mid-thought |
| **NFR-A-04** | Turn-detection false-hold rate | ≤ 10% | Leaving the user waiting after they finished |
| **NFR-A-05** | Agent self-trigger rate (speakers, 5 min) | **0** | AEC must prevent the agent hearing itself — [ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md) |
| **NFR-A-06** | User speech preserved during double-talk | ≥ 90% of interruptions | AEC must not suppress the user along with the echo |

> **NFR-A-06 is the one that decides whether barge-in works with speakers.** An
> echo canceller that only handles one-party speech is easy and useless — barge-in
> is by definition double-talk. Measured in
> [BM-05](../04-quality/03-benchmark-plan.md);
> [RISK-12](../06-governance/01-risk-register.md).

> **A-03 and A-04 trade off directly against each other**, and they are not
> equally bad. Being interrupted mid-thought is far more disruptive than waiting
> an extra 400 ms. The thresholds above reflect that asymmetry deliberately:
> when tuning, bias toward holding.

---

## 5. Privacy & security

| ID | Requirement |
|---|---|
| **NFR-S-01** | No audio, transcript, or derived data leaves the machine. Ever. |
| **NFR-S-02** | Zero outbound network connections during a session. Verifiable with the adapter disabled. |
| **NFR-S-03** | All service ports bind to `127.0.0.1`, never `0.0.0.0`. |
| **NFR-S-04** | Raw audio is not persisted by default. |
| **NFR-S-05** | Transcripts are stored unencrypted in the user profile, and this is documented rather than silently assumed. |
| **NFR-S-06** | Uninstalling removes all user data on request. |

Rationale and threat analysis: [Security & Privacy](../06-governance/02-security-and-privacy.md),
[Threat Model](../06-governance/03-threat-model.md).

**NFR-S-03 is more than hygiene.** `llama-server` has no authentication. Bound to
`0.0.0.0` on a laptop that joins café Wi-Fi, it is an open inference endpoint —
and an open window into whatever is in its context.

---

## 6. Usability

| ID | Requirement |
|---|---|
| **NFR-U-01** | A full session requires zero keyboard input after start. |
| **NFR-U-02** | System state is unambiguous at all times (FR-41). |
| **NFR-U-03** | Errors state what happened and what to do, never only a traceback. |
| **NFR-U-04** | First-run setup completes in ≤ 15 minutes on a clean machine, excluding downloads. |
| **NFR-U-05** | Audio device selection is discoverable without editing config files. |

---

## 7. Maintainability

| ID | Requirement |
|---|---|
| **NFR-M-01** | Each pipeline stage is swappable behind an interface without touching its neighbours. |
| **NFR-M-02** | Prompts are versioned data files, not string literals in code. |
| **NFR-M-03** | All tunable parameters live in configuration. |
| **NFR-M-04** | Every stage is independently testable with recorded fixtures. |
| **NFR-M-05** | No source file exceeds ~400 lines without a documented reason. |

**NFR-M-01 is a hedge against genuine uncertainty.** Several component choices
here — the STT model above all — rest on published benchmarks rather than
measurements on this machine. Some will be wrong. The interface boundary is what
makes discovering that cheap instead of catastrophic.

---

## 8. Portability

| ID | Requirement | Status |
|---|---|---|
| **NFR-PORT-01** | Windows 11 + NVIDIA | Primary target |
| **NFR-PORT-02** | Linux + NVIDIA | Should work; not tested |
| **NFR-PORT-03** | macOS Apple Silicon | Not supported v1 (CUDA assumptions) |
| **NFR-PORT-04** | CPU-only fallback | Not supported — a 9B on CPU is far below NFR-P-20 |
| **NFR-PORT-05** | No hard-coded absolute paths | Enforced by lint |

---

## 9. Verification matrix

| NFR group | How verified | Document |
|---|---|---|
| Performance | Automated instrumented benchmark, 20+ turns | [Benchmark Plan](../04-quality/03-benchmark-plan.md) |
| Resources | `nvidia-smi` sampling during a full session | [Benchmark Plan](../04-quality/03-benchmark-plan.md) |
| Reliability | 60-minute soak test | [Test Strategy](../04-quality/01-test-strategy.md) |
| Accuracy | Recorded-audio fixture suite | [Test Strategy](../04-quality/01-test-strategy.md) |
| Privacy | Network adapter disabled + packet capture | [Test Strategy](../04-quality/01-test-strategy.md) |
| Usability | Manual walkthrough on a clean machine | [Definition of Done](../04-quality/05-definition-of-done.md) |

**No NFR in this document is verified today.** Every target is derived from
published benchmarks or reasoning. Closing that gap is the purpose of Phase 0 in
the [Roadmap](../07-planning/01-roadmap.md), and no implementation should begin
before BM-01 through BM-05 have run.

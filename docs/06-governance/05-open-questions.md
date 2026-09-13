# Open Questions

| | |
|---|---|
| **Status** | Live — close entries as they are answered |
| **Last updated** | 2026-09-13 |
| **Phase 2 execution update** | BM-02 closed OQ-03; BM-03 closed OQ-08 and changed ADR-0009; OQ-09/OQ-10 remain open |

Known unknowns. Each has an owner, a resolution route, and a **default** — what
happens if it is never answered — so that no question blocks progress by
default.

---

## OQ-02 — Structured rounds, or free-flowing argument?

| | |
|---|---|
| **Owner** | Amin (product) |
| **Status** | Open |
| **Affects** | Session state machine, prompt design |

**Question.** Should a debate have formal structure — opening statements, timed
rebuttals, closing — or flow freely?

**Why it matters.** These serve different personas
([Personas §4](../00-product/03-personas-and-journeys.md)):

- The **Sharpener** wants free-flowing conversation
- The **Practitioner** wants rounds, constraints, and consistency to measure
  improvement against

They are arguably different products sharing a pipeline.

**Current default.** Free-flowing, serving the Sharpener (the primary persona).
Structured mode is a Phase 5 candidate.

**Resolution.** Use v1 for a while and see which is missed.

---

## OQ-04 — Should the agent ever be persuadable?

| | |
|---|---|
| **Owner** | Amin (product + safety) |
| **Status** | Open — **may never fully close** |
| **Related** | FR-24, FR-25, [Responsible AI](04-responsible-ai.md) |

**Question.** Under what conditions should the agent change its position?

**Why it matters.** Both extremes fail, in ways that are not symmetric:

| | Result |
|---|---|
| **Never concedes** | A wall. The user learns their arguments have no effect, disengages. |
| **Concedes readily** | A mirror. The user learns their arguments are stronger than they are. **Worse**, because it feels like success. |

FR-24 (never to pressure) and FR-25 (yes to argument) encode the intended shape.
**The calibration between them has no published guidance** — the literature
studies agents debating each other for a correct answer, not agents debating a
human whose thinking is the product.

**Current default.** Concede *specific points* when genuinely defeated; never
concede the *position* under pressure. Tuned empirically via probes P-01, P-02,
P-03.

**Resolution.** Empirical, across many sessions. This is a calibration problem,
not a question with an answer.

---

## OQ-05 — What is the right response length?

| | |
|---|---|
| **Owner** | Amin |
| **Status** | Open |
| **Related** | FR-31, NFR-P-01 |

**Question.** How long should a spoken turn be?

**Why it matters.** Length is simultaneously a comprehension constraint and — at
30 tok/s — the dominant latency lever. Too long: the user cannot follow and
interrupts. Too short: arguments are undeveloped.

**Current default.** `max_tokens: 220` ≈ 45 s. A hard cap, plus prompt
instruction to be brief.

**Resolution.** The `interruption rate` and `unheard ratio` signals
([Evaluation §3](../04-quality/02-evaluation-framework.md)) measure this
directly. A high interruption rate means responses are too long — this is one of
the few subjective questions with a genuine quantitative proxy.

---

## OQ-06 — How are interim transcripts produced?

| | |
|---|---|
| **Owner** | Amin (technical) |
| **Status** | Open |
| **Related** | FR-40, US-403, [ADR-0005](../02-architecture/adr/0005-parakeet-tdt-for-stt.md) |

**Question.** Parakeet TDT is **not a streaming model**. How do we show live text
as the user speaks, and, only in heuristic fallback mode, produce the partial
text that fallback needs? Smart Turn v3.2 consumes raw audio and does not depend
on the answer to this question.

**Options**

| Option | Cost |
|---|---|
| Re-transcribe the buffer every ~500 ms | Wasteful, but the CPU is idle |
| Second tiny streaming model (Moonshine) | Another dependency and ~300 MB |
| Turn-detector-only partials; no live display | Loses US-403 |
| Accept per-turn text rather than per-word | Simplest; less responsive UI |

**Current default.** Do not run periodic partial STT in semantic mode. If live
display or heuristic fallback is enabled later, re-transcribe every 500 ms only
for that explicitly selected feature.

**Resolution.** BM-03 measures the cost. If it competes with final transcription
under load, reconsider.

---

## OQ-07 — Should context compaction be visible?

| | |
|---|---|
| **Owner** | Amin |
| **Status** | Open |
| **Related** | [Data Flow §4](../02-architecture/04-data-flow-and-state.md) |

**Question.** Compaction takes 2–4 s and will blow P95 if it runs mid-turn.
Should the user be told it is happening?

**Options**
- Silent, scheduled between turns while the user speaks (invisible)
- Spoken filler: "Let me think about where we've got to"
- Visible UI indicator only

**Current default.** Schedule between turns, invisibly. If it must run during a
turn, speak filler rather than going silent — a silent 4-second gap is
indistinguishable from a crash.

**Resolution.** Only matters in sessions beyond ~90 exchanges. Low priority.

---

## Closed questions

### ✅ OQ-08 — Does thread-isolated ONNX inference preserve the audio loop? → **NO**

| | |
|---|---|
| **Closed** | 2026-09-13 |
| **Answer** | Do not rely on thread-only ownership; use bounded spawned workers |
| **Evidence** | [BM-03](../../benchmarks/results/BM-03-cpu-speech-rtf.md): corrected thread trial missed service windows; selected spawned/Piper configuration passed |
| **Decision now lives in** | [ADR-0009](../02-architecture/adr/0009-python-as-orchestration-language.md) |

**What it determined.** BM-03 measures the product-relevant outcome rather than
trying to attribute every scheduler stall to the Python GIL. The original large
drop counts came from a drifting Windows timer probe and are invalid. The
corrected trial still does not give threads a bounded way to terminate obsolete
native work, while the selected spawned-worker/Piper configuration met every
BM-03 gate. Spawned model ownership is therefore retained; no GIL claim is made.

---

### ✅ OQ-03 — Does prefix caching work on hybrid DeltaNet? → **YES**

| | |
|---|---|
| **Closed** | 2026-09-12 |
| **Answer** | llama.cpp efficiently reuses Qwen3.5-9B's hybrid prefix state |
| **Evidence** | [BM-02](../../benchmarks/results/BM-02-prefix-cache.md): cached TTFT 320.9 ms versus 1,079.1 ms perturbed; 6.18× post-prefill TTFT speedup |
| **Decision now lives in** | [ADR-0002](../02-architecture/adr/0002-llama-cpp-server-as-llm-runtime.md) and the [Latency Budget](../02-architecture/07-latency-budget.md) |

**What it determined.** Prefix caching works on the target llama.cpp build and
hybrid DeltaNet model. NFR-P-12 is met at turn 20, and speculative prefill is a
viable Phase 3 optimization. Production still records cache behavior per turn
because a model/runtime upgrade can invalidate this result.

---

### ✅ OQ-01 — Headphones or speakers? → **SPEAKERS**

| | |
|---|---|
| **Closed** | 2026-08-30 |
| **Answer** | The user will use **speakers** |
| **Evidence** | Direct statement from the user |
| **Decision now lives in** | [ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md) |
| **Superseded** | [ADR-0008](../02-architecture/adr/0008-headphones-first-audio-transport.md) |

**What it determined.** Acoustic echo cancellation is mandatory, which forces a
browser/WebRTC audio transport — and, less obviously, forces **agent audio to be
played by the browser rather than by Python**, since AEC needs the played signal
as a reference. The browser is therefore no longer an optional transcript viewer
but a required component carrying the audio path in both directions.

**Cost of the reversal.** ~3 days, and the transport moves from a conditional
Phase 4 item to a committed **Phase 1** item — barge-in in Phase 2 cannot be
built or tested without working AEC.

**New risk created.** [RISK-12](01-risk-register.md) — double-talk AEC
performance is unverified, and laptop speakers plus a built-in microphone array
are the worst case for it.

---

When a question closes, record the answer, the date, the evidence, and which ADR
now carries the decision — then move it here rather than deleting it. The
reasoning is worth more than the conclusion.

---

## Summary

| ID | Question | Blocks | Resolves via |
|---|---|---|---|
| ~~OQ-01~~ | ~~Headphones or speakers?~~ | — | ✅ **Closed — speakers** |
| ~~OQ-03~~ | ~~Prefix caching on hybrid?~~ | — | ✅ **Closed — works; BM-02** |
| ~~OQ-08~~ | ~~Thread-isolated ONNX preserves audio loop?~~ | — | ✅ **Closed — no; BM-03** |
| **OQ-09** | Double-talk AEC performance | Barge-in with speakers | BM-05 |
| **OQ-10** | Browser output acknowledgement correctness | Proposed ADR-0014 and FR-13 acceptance | M2 browser/acoustic output tests |
| OQ-06 | Interim transcripts | UI live text | BM-03 |
| OQ-04 | Persuadability calibration | Debate quality | Empirical |
| OQ-05 | Response length | FR-31 tuning | Layer 1 signals |
| OQ-02 | Structured rounds? | Phase 5 scope | Usage |
| OQ-07 | Compaction visibility | P95 tail | Low priority |

**Four of these are answered by Phase 0 benchmarks.** The rest resolve through
use.

None blocks starting work — every entry has a default, which is the point of
writing them down rather than waiting.

---

## OQ-09 — Does AEC survive double-talk on this hardware?

| | |
|---|---|
| **Owner** | Amin (technical) |
| **Status** | **Open** — created by the OQ-01 resolution |
| **Resolves via** | [BM-05](../04-quality/03-benchmark-plan.md) |
| **Related** | [ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md), [RISK-12](01-risk-register.md) |

**Question.** With laptop speakers and the built-in microphone, does the
browser's echo canceller preserve the user's speech *while the agent is
speaking*?

**Why it matters.** An echo canceller that works when only one party speaks is
easy and useless. The entire point is barge-in, which is **by definition
double-talk** — the hardest case for AEC, where the common failure is
suppressing the user's interruption along with the echo.

If it fails, the agent becomes effectively uninterruptible, which is precisely
the failure ADR-0012 exists to prevent.

**Current default.** Assume the browser's AEC3 handles it — it is among the
most-tested implementations in existence. Verify before building on it.

**Resolution.** BM-05: measure self-trigger rate with the user silent, then
measure whether user speech survives during agent playback.

---

## OQ-10 — Can browser output acknowledgements safely bound spoken history?

| | |
|---|---|
| **Owner** | Amin (technical) |
| **Status** | Open — added during Phase 2 planning, 2026-09-06 |
| **Related** | [FR-13](../00-product/02-product-requirements.md), [I-3](../02-architecture/04-data-flow-and-state.md), [Proposed ADR-0014](../02-architecture/adr/0014-browser-acknowledged-playback.md) |
| **Resolves via** | Tasks 7–9 and 17 of the [Phase 2 plan](../superpowers/plans/2026-09-06-phase-2-turn-detection-and-barge-in.md) |

**Question.** Can the supported browser/device produce a conservative source
sample acknowledgement from AudioWorklet rendering and output-device timestamps
without crediting audio that has not been audible, including stop, suspension,
device change, and delayed control messages?

**Evidence so far.** [VERIFIED by source inspection, 2026-09-06] The existing
[`PlaybackQueue.read()`](../../src/contra/audio/webrtc_transport.py) credits
sender consumption before browser rendering. This establishes a missing
verification boundary; it does not establish an observed user-facing failure.

**Current default.** [ASSUMED] The timestamp-and-guard proposal in ADR-0014 can
provide a conservative boundary on the supported device. Keep the ADR Proposed
until its measured acceptance conditions pass. Never use a fixed sender-delay
subtraction or an always-empty assistant history as a substitute.

**Resolution.** Compare acknowledgements with actual recorded audible output
at synthesis-unit boundaries across ≥20 interruptions and output-failure trials.
Record uncertainty, browser/device versions, output guard and context behavior.
Any over-credit invalidates the chosen guard/design. AEC validity for the new
playback and PTT capture graph remains separately tracked by OQ-09/RISK-12.

# Open Questions

| | |
|---|---|
| **Status** | Live — close entries as they are answered |
| **Last updated** | 2026-08-30 |

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

## OQ-03 — Does prefix caching work on hybrid DeltaNet? ⚠ **Highest technical uncertainty**

| | |
|---|---|
| **Owner** | Amin (technical) |
| **Status** | Open |
| **Resolves via** | [BM-02](../04-quality/03-benchmark-plan.md) |
| **Related** | [RISK-03](01-risk-register.md) |

**Question.** Does `llama-server` reuse the conversation prefix efficiently on a
model where 24 of 32 layers carry recurrent state rather than a KV cache?

**Why it matters.** Prefix caching is trivial for pure attention. Hybrid
architectures need state *checkpointing*, which llama.cpp implements via
`llama_memory_hybrid` — but its effectiveness is unverified.

> If it does not work, **every turn re-prefills the whole conversation.** At turn
> 20 that is ~3,000 tokens before the first output token, pushing TTFT to several
> seconds and making NFR-P-01 unreachable. It also removes speculative prefill,
> our largest planned optimisation
> ([Latency Budget §5](../02-architecture/07-latency-budget.md)).

**Current default.** Assume it works; measure before relying on it. Do not build
speculative prefill until BM-02 confirms.

**Resolution.** BM-02, in Phase 0. Also instrumented per turn in production
(`prefix_cache_hit`).

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
as the user speaks, and feed partial transcripts to the turn detector?

**Options**

| Option | Cost |
|---|---|
| Re-transcribe the buffer every ~500 ms | Wasteful, but the CPU is idle |
| Second tiny streaming model (Moonshine) | Another dependency and ~300 MB |
| Turn-detector-only partials; no live display | Loses US-403 |
| Accept per-turn text rather than per-word | Simplest; less responsive UI |

**Current default.** Re-transcribe every 500 ms. The CPU has capacity, and the
waste is acceptable.

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

## OQ-08 — Does the GIL release during ONNX inference?

| | |
|---|---|
| **Owner** | Amin (technical) |
| **Status** | Open |
| **Resolves via** | [BM-03](../04-quality/03-benchmark-plan.md), sub-test GIL-1 |
| **Related** | [ADR-0009](../02-architecture/adr/0009-python-as-orchestration-language.md), [ADR-0004](../02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md) |

**Question.** Does ONNX Runtime genuinely release the GIL, so that
`asyncio.to_thread` parallelises STT and TTS against the audio event loop?

**Why it matters.** If it does not, CPU inference blocks audio capture and
playback — **dropped frames, lost user speech, glitched output.** It would
undermine the CPU-placement decision and, in the worst case, the choice of Python
itself.

> This is the assumption whose failure would be most expensive to correct.
> Rewriting the orchestrator is the "Hard" reversibility case in
> [ADR-0009](../02-architecture/adr/0009-python-as-orchestration-language.md).

**Current default.** Assume it does (it is the documented behaviour). Measure
before building on it.

**Resolution.** BM-03 GIL-1: count dropped 20 ms audio frames during concurrent
inference. Must be **zero**.

---

## Closed questions

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
| **OQ-03** | Prefix caching on hybrid? | Latency design | BM-02 |
| **OQ-08** | GIL release on ONNX? | CPU placement | BM-03 |
| **OQ-09** | Double-talk AEC performance | Barge-in with speakers | BM-05 |
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


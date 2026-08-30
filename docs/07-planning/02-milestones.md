# Milestones

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

Each milestone has explicit **exit criteria**. A milestone is not done because
the work feels finished; it is done when the criteria are met
([Definition of Done §2](../04-quality/05-definition-of-done.md)).

---

## M0 — Measurement ⚠ GATE

**2 days · Phase 0**

### Tasks
| | Est. |
|---|---|
| Set up llama.cpp; verify the model loads with full offload | 2 h |
| BM-01 — throughput, TTFT, thermal run | 3 h |
| BM-02 — prefix cache across 20 turns | 3 h |
| BM-03 — CPU speech RTF under GPU load; GIL frame-drop test | 4 h |
| BM-04 — VRAM profile; confirm iGPU drives display | 2 h |
| **BM-05 — echo cancellation and double-talk with speakers** | 2 h |
| Write results; update budgets; re-score risks | 3 h |

### Exit criteria
- [ ] All five benchmarks run; results committed to `benchmarks/results/`
- [ ] Every FAIL has a decided, written response
- [ ] [Latency Budget](../02-architecture/07-latency-budget.md) and
      [Resource Budget](../02-architecture/08-resource-budget.md) updated with
      measured values
- [ ] Confidence markers upgraded from [SOURCED]/[ESTIMATED] to [VERIFIED]
      wherever measurement supports it
- [ ] RISK-01, 02, 03, 06, 12 resolved or re-scored
- [ ] OQ-03, OQ-08, OQ-09 closed

### Decision points
| BM-01 result | Action |
|---|---|
| ≥ 25 tok/s | Proceed with the 9B |
| 18–25 | Proceed; shorten `max_tokens` to 150 |
| < 18 | **Switch to Qwen3.5-4B before M1** |

| BM-05 result | Action |
|---|---|
| Double-talk ≥ 18/20 | Proceed; barge-in is viable with speakers |
| Double-talk 10–17/20 | Try external mic and volume reduction; re-measure |
| Double-talk < 10/20 | **Push-to-talk becomes the default.** Barge-in documented as requiring headphones. Product change — decide before M2. |

---

## M1 — Walking skeleton

**~1 week · Phase 1**

### Tasks
| | Est. |
|---|---|
| Project scaffold, config loader, logging | 4 h |
| **Browser page: `getUserMedia` with AEC, WebRTC audio both directions** | 10 h |
| **Python WebRTC endpoint; signalling; `AudioInput`/`AudioOutput` over the track** | 8 h |
| Silero VAD integration | 3 h |
| Parakeet STT behind `SttStage` | 5 h |
| `LlmClient` with SSE streaming and cancellation | 5 h |
| `SentenceSegmenter` with the min-unit rule | 3 h |
| Kokoro TTS behind `TtsStage` | 4 h |
| `ConversationState` **with FR-13 structure** | 6 h |
| ~~Pipecat assembly~~; **probe FR-13 expressibility** — probe FAILED, no assembly | 6 h |
| Unit tests for core components | 6 h |

### Exit criteria
- [ ] A spoken utterance produces a spoken reply, end to end, **through the browser**
- [ ] **Agent does not trigger itself over speakers during a 5-minute reply** (NFR-A-05)
- [ ] WebRTC round-trip latency measured (≤ 60 ms, NFR-P-15)
- [ ] Turn latency measured and recorded (may exceed target)
- [ ] Unit suite runs in < 10 s with no models loaded
- [ ] `ruff` import boundaries enforced — `debate/` imports no I/O library
- [ ] `ConversationState` carries `text_spoken` / `text_generated` separately
- [x] **Answered:** Pipecat CANNOT express FR-13 cleanly — ADR-0013

### The two non-obvious priorities

> **Build `ConversationState` with the FR-13 structure now**, before barge-in
> exists. It has no visible effect in M1. Retrofitting it in M2 means reworking
> the component that barge-in depends on most.

> **Probe the Pipecat/FR-13 fit early.** This is the specific integration risk in
> [ADR-0003](../02-architecture/adr/0003-pipecat-as-orchestration-framework.md).
> Discovering it in M1 costs a day; discovering it in M2 costs a rewrite.

---

## M2 — Turn detection and barge-in ⚠ Hardest

**~1 week · Phase 2**

### Tasks
| | Est. |
|---|---|
| **Record fixture suite from real argumentative speech** | 4 h |
| Smart Turn v2 integration | 5 h |
| Decision policy with thresholds and safety valve | 4 h |
| Pre-buffer retaining speech onset | 3 h |
| Barge-in: stop playback, cancel TTS, **abort the LLM request** | 6 h |
| `truncate_to_spoken` + `AudioChunk.text_span` contract | 6 h |
| Invariant I-3 assertions and barge-in unit tests | 4 h |
| Push-to-talk fallback (FR-43) | 3 h |
| Threshold tuning against fixtures | 5 h |
| IT-02 barge-in integration test | 3 h |

### Exit criteria
- [ ] NFR-P-03: barge-in stop ≤ 300 ms
- [ ] NFR-A-03: false-cut rate ≤ 5% on fixtures
- [ ] NFR-A-04: false-hold rate ≤ 10%
- [ ] NFR-A-02: **zero words emitted on `silence.wav`**
- [ ] **NFR-A-06: barge-in works over speakers — user speech survives double-talk**
- [ ] Invariant I-3 holds after every simulated barge-in
- [ ] Interrupting does not slow the following turn (LLM slot freed)
- [ ] Push-to-talk works as a complete bypass

### Notes

> **The fixtures must be real argumentative speech, unscripted.** Pausing while
> *constructing* an argument differs substantially from pausing while *reading*
> one, and a detector tuned on read speech will fail on the actual use case.

> **The "interrupting does not slow the next turn" criterion** catches the
> cancellation bug that otherwise passes every test: abandoning the SSE iterator
> stops the audio but leaves `llama-server` generating, occupying the slot the
> next turn needs.

---

## M3 — Debate quality

**~1.5 weeks · Phase 3**

### Tasks
| | Est. |
|---|---|
| Write `prompts/debate/v1.md`; `PromptBuilder` | 5 h |
| Topic extraction + confirmation flow (FR-02) | 5 h |
| Intensity variants | 3 h |
| Layer 2 probe suite (P-01…P-10) | 6 h |
| **Prompt iteration** — expect v1→v4 | 12 h |
| Context compaction with preservation rules | 5 h |
| Speculative prefill *(only if BM-02 passed)* | 5 h |
| Latency optimisation to NFR-P-01 | 6 h |
| Layer 1 analysis queries | 3 h |

### Exit criteria
- [ ] **Probe P-01 (sycophancy) passes on all intensity settings**
- [ ] **Probe P-04 (fabrication) passes**
- [ ] All other probes pass or have written exceptions
- [ ] NFR-P-01: median ≤ 1,200 ms over 20 turns
- [ ] NFR-P-02: P95 ≤ 2,000 ms
- [ ] ≥ 5 real sessions rated at Layer 3
- [ ] Compaction preserves opening positions and concessions verbatim

### Notes

> **The 12-hour prompt-iteration estimate is the least reliable number in this
> document.** RISK-08 (sycophancy) scores 20 — the highest in the register — and
> it is the one risk with no bounded remedy. It may take four versions or twelve.
>
> Worst case, if prompting cannot suppress it, the remedy is fine-tuning, which
> is a separate project entirely. That contingency is why this milestone has the
> loosest estimate.

---

## M4 — Interface and hardening

**~1 week · Phase 4**

### Tasks
| | Est. |
|---|---|
| SQLite schema, migrations, repository | 5 h |
| Synchronous turn writes; hard-kill durability test | 3 h |
| Markdown transcript export | 2 h |
| FastAPI WebSocket + control endpoints | 5 h |
| UI: transcript, state indicator, metrics panel *(page already exists from M1)* | 6 h |
| First-run audio calibration: tone, echo return loss, warn on poor acoustics | 4 h |
| Error handling across the F-catalogue | 6 h |
| Supervisor script + preflight checks | 4 h |
| IT-06 offline test; dependency telemetry audit | 3 h |
| IT-07 60-minute soak | 2 h |
| Clean-machine install verification | 3 h |

### Exit criteria
- [ ] **GATE 1: IT-06 passes** — full session, network adapter disabled
- [ ] Packet capture shows zero outbound traffic
- [ ] IT-07 soak: no RAM growth, no VRAM growth, < 10% tok/s decay
- [ ] Hard kill loses at most the in-flight turn
- [ ] All ports verified bound to `127.0.0.1`
- [ ] No transcript content in logs above `DEBUG`
- [ ] Install guide verified by following it literally on a clean machine

---

## v1.0 release

### Gates — non-negotiable
- [ ] **GATE 1 — Privacy:** IT-06 passes
- [ ] **GATE 2 — Fabrication:** probe P-04 passes

### Requirements
- [ ] Every P0 requirement passes its acceptance test
- [ ] Every P1 either passes or has a written deferral

### Measured on target hardware
- [ ] NFR-P-01 ≤ 1,200 ms median · NFR-P-02 ≤ 2,000 ms P95
- [ ] NFR-P-03 ≤ 300 ms barge-in · NFR-P-20 ≥ 25 tok/s
- [ ] NFR-R-01 peak VRAM ≤ 7.5 GiB
- [ ] NFR-REL-02 ≥ 95% crash-free over 20 sessions

### Quality
- [ ] Probes P-01, P-02 pass
- [ ] ≥ 5 real sessions rated
- [ ] Version tagged; release notes with the Measured table

---

## Effort summary

| Milestone | Est. | Cumulative |
|---|---|---|
| M0 Measurement | 2 d | 2 d |
| M1 Walking skeleton **(+3 d: browser transport)** | 9 d | 11 d |
| M2 Turn detection + barge-in | 6 d | 17 d |
| M3 Debate quality | 8 d | 25 d |
| M4 Interface + hardening **(−1 d: transport already built)** | 5 d | 30 d |
| **v1.0** | | **~30 focused days** |

> **Net cost of the speakers decision: +2 days.** The browser transport moved
> forward from M4 to M1 (+3 d) but is no longer needed in M4 (−1 d). The
> transcript UI in M4 now attaches to a page that already exists.

### On these estimates

They assume focused days, which side projects rarely get. **Calendar time is
realistically 2–3×.**

Two are notably uncertain:

| Milestone | Why |
|---|---|
| **M3** | Prompt iteration against sycophancy is unbounded. RISK-08 has no guaranteed remedy short of fine-tuning. |
| **M2** | Turn-detection tuning is empirical. It can meet every numeric target and still feel wrong — RISK-05. |

**M0 is the only estimate that is confident**, because it is measurement rather
than construction. It is also the one that most reduces uncertainty everywhere
else — two days that retire four of the top six risks.

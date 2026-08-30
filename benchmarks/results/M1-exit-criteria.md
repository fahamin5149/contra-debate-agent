# M1 — Walking skeleton exit criteria

| | |
|---|---|
| **Date** | 2026-08-31 |
| **Status** | **Partially complete** — automated criteria met; three require a human |
| **Branch** | `feat/phase-1-walking-skeleton` |

## Environment

| | |
|---|---|
| GPU | NVIDIA RTX 4060 Laptop, 8,188 MiB, driver 610.47 |
| CPU | i7-13620H (6P + 4E, 16 threads) |
| Python | 3.11.9 |
| numpy / onnxruntime / aiortc | 2.4.6 / 1.29.0 / 1.15.0 |
| STT | Parakeet TDT 0.6B v3, **int8**, CPU |
| TTS | Kokoro-82M v1.0, CPU |
| VAD | Silero v5 ONNX, CPU |
| llama-server | **NOT INSTALLED** — blocks the end-to-end criteria |
| Mains power | yes |

---

## Automated criteria — met

| Criterion | Target | Measured | Verdict |
|---|---|---|---|
| Unit suite runtime | < 10 s | **0.75 s** (57 tests) | ✅ |
| Full suite incl. real models | passes | **74 passed** (73.8 s) | ✅ |
| `ruff` import boundaries — `debate/` imports no I/O library | clean | clean | ✅ |
| `ruff check` whole tree | clean | clean | ✅ |
| `mypy` (strict on `debate/`) | clean | 28 files, no issues | ✅ |
| `ConversationState` stores spoken/generated separately | yes | yes, invariant I-3 asserted | ✅ |
| STT emits nothing on `silence.wav` (NFR-A-02) | 0 words | **`''`** | ✅ |
| STT RTF, **idle** | < 0.3 | **0.187** | ✅ (see caveat) |
| WebRTC signalling handshake | works | offer→answer OK | ✅ |
| Inbound media path (Opus→16 kHz frames) | works, 0 dropped | 640-byte frames, **0 dropped** | ✅ |
| Outbound media path (chunk→Opus→peer) | works | verified | ✅ |
| `PlaybackPosition` over a live peer connection | advances correctly | `chunks_played=1`, `span_end=33` | ✅ |
| Preflight when llama-server is down (FR-52) | actionable message, no traceback | exit 3 + remediation | ✅ |

> **NFR-A-02 is the headline result.** `silence.wav` transcribes to the empty
> string. That is the single property that decided
> [ADR-0005](../../docs/02-architecture/adr/0005-parakeet-tdt-for-stt.md) — a
> Whisper-family model would be expected to hallucinate here, and phantom text
> entering the argument history is unrecoverable.

---

## Not yet verified — requires a human and llama-server

| Criterion | Blocker |
|---|---|
| Spoken utterance → spoken reply, end to end | llama-server not installed; needs a real voice |
| **NFR-A-05** — agent does not self-trigger over speakers, 5 min | Needs speakers, a mic, and a room. This is **BM-05**. |
| **NFR-A-06** — user speech survives double-talk | Same. The failure that matters most, and untestable without acoustics. |
| **NFR-P-15** — WebRTC round trip ≤ 60 ms | Read from `chrome://webrtc-internals` |
| Turn latency (median/max) with real speech | Needs the above |
| Pipecat FR-13 expressibility spike (Task 14) | `pipecat-ai` install did not complete in session |

---

## Caveats on the numbers above

**STT RTF 0.187 was measured idle, not under GPU load.** BM-03 explicitly
requires measurement *while the GPU is generating*, because published CPU
benchmarks come from idle machines and ours will be running an audio pipeline
concurrently. The idle figure is encouraging, not sufficient.

**No dropped audio frames were observed**, but only over a synthetic loopback
with a tone track. The GIL question ([OQ-08](../../docs/06-governance/05-open-questions.md))
is not settled until STT and TTS run concurrently with real audio under GPU load.

---

## Findings that changed the design

**1. `onnx_asr.load_model()`'s first argument is a model name/type, not a path.**
Passing a directory made it resolve against HuggingFace and issue a network
request — which would have broken the offline guarantee (NFR-S-01) silently.
Fixed to `load_model(model_type, path)`. Caught by execution, not review.

**2. The `numpy<2.2` cap was unnecessary.** onnxruntime 1.29, onnx-asr 0.12 and
kokoro-onnx 0.6.1 all run under numpy 2.4.6. The cap was a defensive guess and
was making every install report a false conflict. Removed.

**3. int8 Parakeet is the right variant for CPU.** 652 MB vs 2.4 GB fp32, and
RTF 0.187. Set as the default.

**4. Silero rejects all synthetic audio.** Measured peak speech probability:
silence 0.0006, synthetic tone 0.0007, white noise 0.0020 — all far below the
0.5 threshold. This is correct behaviour for a neural VAD and precisely why it
was chosen, but it means **no synthetic signal can exercise the positive path**.
Real speech fixtures are required, which is already the Phase 2 plan.

---

## Consequences for the design

No ADR changes. The architecture held: the transport, speech layer, and debate
core all sit behind their interfaces, `debate/` remains free of I/O imports, and
the FR-13 mechanism works over a real peer connection.

**Next actions, in order:**

1. Install llama.cpp (Windows CUDA build) — required for every remaining criterion
2. Run **BM-05** (AEC and double-talk) — gates Phase 2 barge-in, and can change
   the product to push-to-talk-by-default if it fails
3. Run **BM-01** (LLM throughput) and **BM-03** (CPU RTF under GPU load)
4. Complete the Pipecat FR-13 spike — answers ADR-0003's revisit trigger

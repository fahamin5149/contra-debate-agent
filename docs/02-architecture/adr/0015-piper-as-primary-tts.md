# ADR-0015: Piper as primary text-to-speech engine

| Status | Date | Deciders | Confidence | Reversibility |
|---|---|---|---|---|
| Accepted | 2026-09-13 | Project owner / implementation evidence | High — measured on target hardware | Easy |

## Context

[ADR-0006](0006-kokoro-for-tts.md) selected Kokoro subject to an explicit
revisit trigger: BM-03 short-unit latency above 150 ms. On the target i7-13620H,
Kokoro required 420–653 ms for the short unit while Qwen3.5-9B generated on the
GPU **[VERIFIED: BM-03, 2026-09-13]**. Its 40+ character throughput remained
faster than real time, but its first unit cannot satisfy NFR-P-13.

The corrected BM-03 repeat also found that a drifting `asyncio.sleep(0.02)`
ticker falsely counted Windows' normal ~15.6 ms timer granularity as dropped
frames. With fixed deadlines, spawned model ownership, two reserved logical
CPUs, and a process-scoped 1 ms multimedia timer request, Piper 1.8.0 completed
the exact 15-character unit in 57.5 ms and missed zero service windows across
five measured repeats **[VERIFIED: BM-03, 2026-09-13]**.

## Decision

Use Piper 1.8.0 with the `en_US-lessac-medium` voice as the default v1 TTS
engine. Piper runs CPU-only in its own spawned, model-owning process. The
orchestrator reserves logical CPUs 0–1 from inference affinity and requests a
1 ms Windows timer resolution only for the active audio session. Kokoro remains
an optional quality mode and diagnostic comparison, but it is not allowed to
claim NFR-P-13 compliance on this machine.

Pin both the runtime version and voice/config hashes in `models.lock.json`.
Treat Piper's GPL-3.0 runtime and the voice model's separate license as release
inputs; include both in `THIRD_PARTY_NOTICES.md` before distribution.

## Alternatives considered

### Keep Kokoro and weaken NFR-P-13

Rejected. The short-unit benchmark was the deciding gate in ADR-0006. Changing
the requirement after a 2.8–4.4× miss would conceal the performance failure.

### Raise the segmenter's minimum unit length

Rejected as the primary response. Larger units improve throughput but increase
the time before synthesis can begin and reduce barge-in history precision. They
cannot make a 420 ms first synthesis satisfy a 150 ms first-byte requirement.

### Piper low- or high-quality voices

Retained for a later measured comparison. `en_US-lessac-medium` is the tested
baseline; selecting a different voice requires the same short-unit, acoustic,
license, and naturalness evidence.

### Keep all inference in threads

Rejected by the Phase 2 lifecycle requirements. Cancellation of an await does
not stop a native ONNX call, so stale work can contend with capture and a newer
generation. Process ownership provides a bounded termination boundary even
though corrected BM-03 evidence does not prove that the GIL caused prior jitter.

## Consequences

### Positive

- NFR-P-13 and NFR-P-22 pass on the target machine under concurrent LLM load.
- CPU-only placement preserves the GPU's single-tenant invariant.
- A model-owning subprocess gives cancellation and shutdown a process boundary.

### Negative

- The measured voice is less natural than Kokoro **[ASSUMED pending blind
  listening tests]**; this can materially affect debate presence.
- Piper's runtime is GPL-3.0. Packaging and source-distribution obligations must
  be reviewed before a public release.
- A process-scoped high-resolution timer can increase power consumption while
  active; restore the default resolution on every shutdown path.
- The voice outputs 22.05 kHz audio, adding an explicit resampling boundary for
  the 24 kHz transport contract.

### Neutral

- The TTS interface remains swappable. Kokoro can remain available for users
  who explicitly prefer quality over the latency requirement.

## Revisit when

- A Kokoro release produces first audio in ≤150 ms for the BM-03 short unit on
  this target machine while preserving cancellation ownership.
- Blind argumentative-prose tests show Piper's voice quality prevents useful
  sessions; compare another Piper voice before selecting a larger engine.
- Piper's license becomes incompatible with the intended distribution model.
- The target hardware changes, or a CPU-capable TTS engine meets the same
  latency with materially better naturalness.

## Verification

| Evidence | Result |
|---|---|
| [BM-03](../../../benchmarks/results/BM-03-cpu-speech-rtf.md) | Piper 15-character full synthesis 57.5 ms; 40+ character RTF ≤0.052; zero missed service windows |
| Voice model SHA-256 | `5EFE09E69902187827AF646E1A6E9D269DEE769F9877D17B16B1B46EEAAF019F` |
| Voice config SHA-256 | `EFE19C417BED055F2D69908248C6BA650FA135BC868B0E6ABB3DA181DAB690A0` |

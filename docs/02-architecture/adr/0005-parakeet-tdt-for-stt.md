# ADR-0005: Parakeet TDT 0.6B v3 (ONNX) for speech-to-text

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | Medium | Easy |

## Context

We need CPU-resident speech-to-text ([ADR-0004](0004-cpu-placement-for-stt-and-tts.md))
that transcribes committed turns within 250 ms (NFR-P-11) at RTF < 0.3
(NFR-P-21), on Windows, English, offline.

A debate has a property most voice applications do not: **long deliberate
pauses.** Users stop mid-argument to think. This turns out to matter more than
raw accuracy.

## Decision

**NVIDIA Parakeet TDT 0.6B v3, exported to ONNX, run on CPU via
[`onnx-asr`](https://pypi.org/project/onnx-asr/).**

Weights: [`istupakov/parakeet-tdt-0.6b-v3-onnx`](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx).

## Rationale

### The deciding factor is not accuracy

Parakeet is more accurate — **6.32% WER vs Whisper large-v3's 7.44%** — and
dramatically faster (~3,333× realtime vs 68.6×) **[SOURCED]**. Both are welcome.

Neither is why we chose it.

> **Parakeet almost never emits text during silence.** Whisper-family models
> famously hallucinate into dead air — "Thank you for watching!", "Subtitles by
> the Amara.org community" — artifacts of YouTube training data.
>
> In most applications this is a nuisance you filter out. **In ours it is
> corrupting.** A debate contains 2–3 second thinking pauses by design. Phantom
> text entering the argument history means the agent rebuts sentences the user
> never said — and the user cannot distinguish "it misheard me" from "it is
> fabricating my arguments". Either reading destroys trust in the tool.

This is NFR-A-02, and it is the requirement Parakeet satisfies that the
alternatives do not.

### The runtime matters too

`onnx-asr` requires **no PyTorch, no NeMo, no transformers**. On Windows, with
Python and CPU-only inference, avoiding a 2.5 GB PyTorch install and its CUDA
wheel matrix is worth a great deal on its own — fewer dependency conflicts,
faster installs, smaller footprint, and no risk of accidentally allocating VRAM.

## Alternatives considered

### faster-whisper small.en — **retained as fallback**

The safe choice: best-supported STT on Windows + NVIDIA, mature, well documented.
Rejected as primary because it hallucinates in silence and is slower. Kept as the
fallback implementation behind the `SttStage` interface — if Parakeet's ONNX path
proves troublesome on Windows, this is the immediate substitute.

### Whisper large-v3 — rejected

~3 GiB VRAM, or very slow on CPU. Worse WER than Parakeet. Hallucinates. Its one
advantage — 99 languages vs Parakeet's 25 — is irrelevant to an English-only v1.

### Moonshine v2 — rejected, worth watching

245M params, purpose-built for latency-critical edge use, with an "Ergodic
Streaming Encoder" designed for exactly our problem. Genuinely appealing.

Rejected on maturity: less deployment evidence, and its silence-hallucination
behaviour is **unverified**. Given that silence robustness is our deciding
criterion, adopting a model whose behaviour there is unknown would be choosing
on the wrong axis. Revisit if Parakeet disappoints.

### whisper.cpp base.en — rejected

Very light, ~12% WER. Too inaccurate — argument content would not survive
(NFR-A-01).

### Cloud STT (Deepgram, AssemblyAI) — disqualified

NFR-S-01.

## Consequences

### Positive
- Best accuracy among candidates (6.32% WER).
- Enormous speed headroom — RTF budget is comfortable even on CPU.
- **Effectively no silence hallucination** (NFR-A-02).
- Minimal dependencies via `onnx-asr`.
- Zero VRAM.

### Negative
- **Not a true streaming model.** **[SOURCED]** Parakeet TDT is
  [not designed for streaming](https://github.com/k2-fsa/sherpa-onnx/issues/2918);
  pseudo-streaming by repeatedly re-transcribing a growing buffer works but is
  wasteful.

  *Impact:* acceptable for turn-based debate, where we transcribe a committed
  utterance rather than needing live word-by-word output. It does complicate two
  things:
  - **Interim transcripts** for the live UI (FR-40, US-403) —
    [OQ-06](../../06-governance/05-open-questions.md).
  - **Partial transcripts for the turn detector**, which needs *something* to
    evaluate. Mitigation: re-transcribe the buffer every ~500 ms, accepting the
    waste since the CPU is idle.

- 25 European languages, not 99. Fine for English-only v1; a constraint on any
  future multilingual work — and note the constraint sits in the speech layer,
  not the LLM, which covers 201 languages.
- Newer and less battle-tested on Windows than faster-whisper.
- Depends on a community ONNX export rather than an official NVIDIA release.

### Neutral
- CPU-resident, per ADR-0004.

## Revisit when

- **BM-03 shows RTF > 0.3 under concurrent GPU load** → fall back to
  faster-whisper small.en, or a smaller Parakeet variant.
- Pseudo-streaming for partial transcripts proves too costly → evaluate
  Moonshine v2, which is built for streaming.
- Multilingual debate enters scope.
- An official NVIDIA ONNX export appears — prefer it over the community one.

## Verification

| ID | Measures |
|---|---|
| **BM-03** | RTF on this CPU during LLM generation |
| Fixture suite | WER on recorded argument audio (NFR-A-01) |
| Fixture suite | **Output on 10 s of pure silence** — must be empty (NFR-A-02) |

The silence fixture is the important one. It is trivial to write, it is the
reason this model was chosen, and it is exactly the test that would be forgotten.

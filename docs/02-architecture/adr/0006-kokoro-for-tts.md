# ADR-0006: Kokoro-82M (ONNX) for text-to-speech

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | Medium | Easy |

## Context

We need CPU-resident speech synthesis ([ADR-0004](0004-cpu-placement-for-stt-and-tts.md))
delivering first audio within 150 ms (NFR-P-13) at RTF < 0.5 (NFR-P-22),
offline, on Windows.

The pipeline streams **sentence by sentence**, so TTS is invoked repeatedly with
short texts rather than once with a paragraph. This usage pattern turns out to
matter.

## Decision

**Kokoro-82M via [`kokoro-onnx`](https://pypi.org/project/kokoro-onnx/), on CPU.**

## Rationale

Best quality-per-resource in our envelope, by a clear margin. 82M parameters,
~80 MB quantized, **faster than real-time on a plain CPU** **[SOURCED]**, and
consistently described across independent sources as the strongest lightweight
option. `pip install kokoro-onnx`; no GPU.

## Alternatives considered

### Orpheus 3B — rejected, and it is a genuine loss

The best-sounding local TTS available. Inline `<laugh>` and `<sigh>` emotion
tags, ~200 ms latency, zero-shot voice cloning.

**It needs ~8 GiB VRAM** **[SOURCED]** — our entire GPU.

Worth recording *why* this stings: a debate opponent that can audibly convey
scepticism — a dry laugh at a weak argument — would be meaningfully better at the
job. Prosody is part of how humans argue. We cannot have it, and no cleverness
changes that. Recorded so the trade-off stays visible rather than being forgotten
as "we chose Kokoro because it was good".

### Piper — **retained as fallback**

Even lighter, very fast on CPU, king of Raspberry Pi deployments. Noticeably more
robotic. Kept as the fallback if Kokoro misses RTF under load — a robotic voice
that keeps up beats a natural voice that stutters.

### Chatterbox 0.5B — deferred

Voice cloning from 10 seconds of audio. Interesting for this product
specifically — arguing against a familiar voice changes the experience — but
costs ~1 GiB VRAM and adds a misuse surface. Out of scope
([Vision & Scope §5](../../00-product/01-vision-and-scope.md)).

### XTTS v2 — rejected

Broadest multilingual cloning (17 languages), ~2 GiB VRAM. Wrong resource
profile; multilingual is out of scope.

### Qwen3-TTS — rejected for now, worth watching

Newest option, **97 ms streaming latency** **[SOURCED]**, streaming and cloning
support, day-0 vLLM support. Rejected because its CPU viability and VRAM profile
are unverified and it is very new. If it runs well on CPU it would be strictly
better than Kokoro; worth a look during Phase 3.

### Cloud TTS (ElevenLabs, Cartesia) — disqualified

NFR-S-01.

## Consequences

### Positive
- Faster than real-time on CPU; comfortable RTF margin.
- Tiny footprint — ~80 MB quantized, ~0.3 GiB RAM.
- Zero VRAM.
- Good naturalness for the size; multiple voices available (FR-32).
- Simple, well-maintained Python package.

### Negative
- **Higher per-call overhead on short texts.** **[SOURCED]** ONNX Kokoro is
  *slower* than PyTorch on tiny inputs (RTF 0.72 vs 0.49), catching up at medium
  and longer lengths.

  *This directly conflicts with our streaming design*, which deliberately emits
  short units. Mitigation is in the `SentenceSegmenter`
  ([Component Design §5.5](../02-component-design.md)): enforce a **~15-character
  minimum unit**, so we never dispatch "Well," and pay the overhead for three
  words. Measured in BM-03.

- No emotion control. The agent's delivery is flat regardless of rhetorical
  intent — a real limitation for a debate partner, per the Orpheus note above.
- No voice cloning (not wanted in v1).
- Prosody derives from text alone; the LLM cannot mark emphasis it wants spoken.

### Neutral
- English-focused, matching v1 scope.

## Revisit when

- **BM-03 shows RTF > 0.5 under concurrent load**, or first-byte latency > 150 ms
  on short units → Piper.
- Hardware reaches ≥ 12 GB VRAM → **Orpheus becomes possible**, and given the
  prosody argument above it should be seriously reconsidered at that point.
- Qwen3-TTS demonstrates viable CPU inference.
- Emotional delivery proves to be a material product weakness in user testing.

## Verification

| ID | Measures |
|---|---|
| **BM-03** | RTF and time-to-first-byte on **short** (15–40 char) units, under LLM load |
| **BM-03** | RTF on typical sentence lengths (60–120 chars) |
| Manual | Naturalness on argumentative prose specifically — rhetorical questions, emphasis, lists |

**The short-unit measurement is the one that decides this ADR**, because it is
where the known weakness meets our chosen usage pattern. A benchmark on
paragraph-length text would look excellent and tell us nothing.

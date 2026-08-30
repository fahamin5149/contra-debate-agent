# ADR-0001: Cascaded STT→LLM→TTS pipeline, not speech-to-speech

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | High | **Hard** — structural |

## Context

Two architectures exist for voice agents in 2026:

1. **Cascaded** — speech-to-text, then LLM, then text-to-speech. Every mainstream
   framework uses this.
2. **Speech-to-speech** — audio in, audio out, no text intermediate. Qwen3-Omni's
   Thinker-Talker design, Moshi.

Speech-to-speech has genuine theoretical advantages: no accumulated per-stage
latency, and paralinguistic information (tone, hesitation, sarcasm) survives
instead of being flattened into text. For a *debate* agent, hearing that the
user sounds uncertain is real signal.

We must decide before any other component choice, because everything downstream
depends on it.

## Decision

**Cascaded pipeline: Parakeet STT → Qwen3.5-9B → Kokoro TTS.**

## Alternatives considered

### Speech-to-speech (Qwen3-Omni class) — rejected

Two independent disqualifiers:

**Latency.** Published measurement on the Qwen2.5-Omni generation found the
DiT-based Talker running at **~0.5× realtime** — roughly 2 seconds of compute per
1 second of audio — producing **~13 s time-to-first-audio** even with
sentence-level streaming. Our target is 1,200 ms. This is an order of magnitude
out, on hardware larger than ours.

**VRAM.** An omni-modal model with an audio encoder and speech decoder would not
fit in 8 GB alongside anything else. See
[Resource Budget](../08-resource-budget.md).

**And a third reason specific to us:** speech-to-speech produces no intermediate
text. For a debate application that is not a minor loss — transcripts, argument
tracking, post-session review, and the entire
[Evaluation Framework](../../04-quality/02-evaluation-framework.md) depend on
having text. Journey D in
[Personas & Journeys](../../00-product/03-personas-and-journeys.md) would be
impossible.

### Hybrid — speech-to-speech with a text side-channel — rejected

Some architectures expose the Thinker's text while the Talker produces audio,
recovering the transcript. It does not address latency or VRAM, which are the
disqualifiers. Adds complexity for no relief.

### Cascaded, but non-streaming — rejected

The tutorial-standard form: wait for complete transcription, complete
generation, complete synthesis. Simple, and produces **2–4 s response delays**.
Rejected on latency; streaming is mandatory, not an optimisation.

## Consequences

### Positive
- Meets the latency budget — see [Latency Budget](../07-latency-budget.md).
- Fits in 8 GB VRAM.
- **Intermediate text is a first-class artifact** — transcripts, argument
  tracking, evaluation, review.
- Every stage is independently swappable (NFR-M-01) and independently testable.
- Matches mainstream practice, so tooling and documentation apply.

### Negative
- **Paralinguistic information is lost.** The agent cannot hear that the user
  sounds uncertain, sarcastic, or frustrated. For a debate partner this is a real
  loss — a human opponent reads hesitation and presses there. Partial mitigation:
  the transcript records *what* was said and turn timing records *how long* the
  user paused, which is a weak proxy for uncertainty.
- Latency accumulates across five stages, each needing its own budget.
- The agent's own prosody is generated from text alone, so it cannot express
  emphasis the LLM did not explicitly write.
- More components to build, test, and fail.

### Neutral
- Ties us to the industry-standard shape, for better and worse.

## Revisit when

- A speech-to-speech model demonstrates **< 1 s time-to-first-audio in under
  4 GB VRAM**. Both conditions, not either.
- Loss of paralinguistic signal proves to be a material product weakness in user
  testing — i.e. the agent misses obvious emotional cues in a way that damages
  the debate.
- The target hardware changes to ≥ 16 GB VRAM, which would make a hybrid
  architecture affordable enough to prototype.

## References

- [Technology Landscape §3](../../01-research/01-technology-landscape.md)
- [Qwen3-Omni](https://github.com/QwenLM/Qwen3-Omni)

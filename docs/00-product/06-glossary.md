# Glossary

Shared vocabulary for this project. Terms are defined as used *here*, which
occasionally differs from broader industry usage — those cases are flagged.

---

## Voice pipeline

**AEC — Acoustic Echo Cancellation**
Removing the agent's own speaker output from the microphone signal. Without it,
the agent hears itself, triggers barge-in, and interrupts itself indefinitely.
Hardest exactly when it matters most: during *double-talk*, when both parties
speak at once. Browsers provide a production-grade implementation free via
`getUserMedia({echoCancellation: true})`; native audio stacks generally do not.

**Barge-in**
The user speaking over the agent, causing it to stop. Requires coordinated
action across playback, the audio queue, LLM generation, and history — see
[Sequence Diagrams](../02-architecture/03-sequence-diagrams.md).

**Cascaded pipeline**
The STT → LLM → TTS architecture, as opposed to end-to-end speech-to-speech.
Sometimes called "chained". [ADR-0001](../02-architecture/adr/0001-cascaded-pipeline-over-speech-to-speech.md).

**Endpointing**
Deciding when a speaker's turn has ended. Used interchangeably with *turn
detection* in the literature. This project distinguishes them — see below.

**Mouth-to-ear latency**
End of the user's speech to the first agent audio reaching their ear. The metric
that matches perception. Distinct from — and always larger than — LLM
time-to-first-token.

**RTF — Real-Time Factor**
Processing time ÷ audio duration. RTF 0.3 means 3 s of audio takes 0.9 s. **RTF
must be < 1.0** for any streaming stage, or its queue grows without bound.

**Semantic turn detection**
Deciding whether a speaker has finished based on the *linguistic content* of
their partial transcript rather than silence duration. "…and the problem is"
signals incompleteness regardless of how long the pause runs. Distinguished in
this project from VAD, which is purely acoustic.
[ADR-0007](../02-architecture/adr/0007-two-layer-turn-detection.md).

**STT / ASR**
Speech-to-Text / Automatic Speech Recognition. Used interchangeably.

**Streaming (pipeline sense)**
Overlapping stages so downstream work begins before upstream work finishes. The
LLM emits sentence one to TTS while still generating sentence two. This is the
difference between ~1 s and ~3 s perceived latency.

**TTFT / TTFB**
Time To First Token (LLM) / Time To First Byte (TTS audio). Both matter far more
than total generation time, because playback begins at the first byte.

**TTS**
Text-to-Speech.

**Turn**
One party's complete contribution. A *committed* turn has been finalised and
added to history; an *in-progress* turn is still being spoken or generated.

**VAD — Voice Activity Detection**
Frame-level classification of audio as speech or not-speech. Purely acoustic,
sub-millisecond, no language understanding. Answers "is sound happening", never
"is this person finished". Confusing these two is the most common voice-agent
design error.

---

## Model & inference

**Context window**
Maximum tokens the model can attend to at once. Qwen3.5-9B supports 262,144
natively; this project uses 16,384 for VRAM reasons.

**GGUF**
The llama.cpp model container format. Single file, includes weights, tokenizer,
metadata, and chat template.

**Gated DeltaNet**
The linear-attention mechanism in 24 of Qwen3.5-9B's 32 layers. Maintains a
**fixed-size recurrent state** rather than a growing KV cache — the reason this
model's memory cost is far below a conventional 9B. See
[Model Analysis](../01-research/02-model-analysis.md).

**Hybrid attention**
Interleaving linear-attention and full-attention layers. Qwen3.5-9B uses a 3:1
ratio: 24 DeltaNet layers, 8 full-attention layers.

**KV cache**
Cached key/value tensors for previously processed tokens, avoiding recomputation.
Grows linearly with context. In this model **only the 8 full-attention layers
contribute**, which is why 16K context costs ~0.5 GiB instead of ~2 GiB.

**Offload / `-ngl`**
Number of layers placed on the GPU. `-ngl 99` means "all". Partial offload
collapses throughput rather than degrading it gracefully.

**Prefill / prompt processing**
Processing the input context before generating. Distinct from *decode*
(generating tokens one at a time) and far more parallel — hence much faster per
token.

**Prefix caching**
Reusing the KV cache for an unchanged conversation prefix across turns. Turns
per-turn prefill from O(whole conversation) into O(new tokens). Critical to
NFR-P-12. Its behaviour with hybrid recurrent state is a
[known open question](../06-governance/05-open-questions.md).

**Quantization**
Storing weights at reduced precision. `Q4_K_XL` here means ~4 bits per weight
with Unsloth's Dynamic 2.0 scheme, which varies precision per layer rather than
applying one rate uniformly.

**Sampling parameters**
Controls on token selection: `temperature`, `top_p`, `top_k`, `min_p`,
`presence_penalty`, `repeat_penalty`. Values for this project are in
[Model Analysis](../01-research/02-model-analysis.md).

**Thinking mode**
Qwen3.5's optional reasoning trace before the answer. **Disabled by default** on
the 0.8B–9B models, and we keep it disabled — a trace would add 5–15 s of
silence per turn.

**Token**
Sub-word unit. Roughly 0.75 English words. A 45-second spoken response is
approximately 130–170 tokens.

**`mmproj`**
The separate multimodal projector file enabling vision. ~918 MB. **Deliberately
not loaded** — pure cost, zero benefit, in the tightest resource on the machine.

---

## Debate domain

Terms from argumentation theory, used precisely in the
[Prompt Engineering Spec](../03-engineering/05-prompt-engineering-spec.md).

**Claim**
The proposition being asserted.

**Warrant**
The reasoning connecting evidence to claim. Usually the implicit step, and
usually where arguments actually break.

**Evidence / Grounds**
Facts or observations offered in support.

**Rebuttal**
An argument against an opponent's claim. Distinct from mere contradiction:
a rebuttal engages the specific reasoning.

**Counter-rebuttal**
Response to a rebuttal, defending the original claim.

**Steelman**
The strongest version of an opposing argument. The opposite of a strawman, and a
core requirement (FR-23).

**Concession**
Explicitly granting a point. Distinguished sharply from *capitulation* —
abandoning a position under social pressure rather than argument. FR-24 forbids
the latter; FR-25 requires the former.

**Gish gallop**
Overwhelming an opponent with many weak claims faster than any can be answered.
Rhetorically effective, epistemically worthless, explicitly forbidden (FR-28).

**Position**
The side a party defends for the session. The agent's is assigned at start and
held (FR-21).

---

## Project-specific

**Committed turn**
A turn finalised and written to history. Only committed turns enter the LLM
context.

**Intensity**
Configurable aggressiveness: Socratic / standard / aggressive. Affects
questioning style and persistence — never rhetorical honesty.

**Spoken history**
Conversation history reflecting what was *actually played to the user*, which
after a barge-in differs from what was generated. Maintaining this distinction
is FR-13.

**Stage**
One pipeline component (VAD, STT, turn detector, LLM, TTS). Each is
independently swappable (NFR-M-01).

---

## Confidence markers

Used throughout this documentation set:

| Marker | Meaning |
|---|---|
| **[VERIFIED]** | Measured here or read from a primary source |
| **[SOURCED]** | Published by a third party, cited, not reproduced by us |
| **[ESTIMATED]** | Calculated from verified inputs, arithmetic shown |
| **[ASSUMED]** | Judgement call, no evidence yet |

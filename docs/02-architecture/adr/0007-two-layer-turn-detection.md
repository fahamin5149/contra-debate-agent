# ADR-0007: Two-layer turn detection — acoustic VAD plus semantic model

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | High | Moderate |

## Context

The system must decide **when the user has finished speaking**. This is a
different and harder problem than transcribing them, and it is where amateur
voice agents most visibly fail.

The obvious approach is a silence threshold: commit the turn after N ms of
quiet. It does not work, and the reason is worth stating precisely.

| Threshold | Failure |
|---|---|
| 400 ms | Cuts users off whenever they pause to think |
| 1,500 ms | Agent feels sluggish and unresponsive after every turn |

**No single threshold satisfies both**, because the acoustic signal is identical
in the two cases. A person pausing mid-argument and a person who has finished
produce the same silence.

This matters disproportionately here. In a debate, users pause *constantly* —
mid-sentence, while marshalling a point, after "…and the problem with that is".
An agent that interrupts there does not read as a latency bug. **It reads as a
rude opponent**, which in a product whose entire value is the quality of the
interlocutor is a character defect rather than a technical one.

## Decision

**Two layers with strictly separated responsibilities.**

| Layer | Model | Signal | Latency | Answers |
|---|---|---|---|---|
| **Acoustic** | Silero VAD | Audio energy | ~1 ms/frame | "Is sound happening?" |
| **Semantic** | Pipecat Smart Turn v2 | Partial transcript | ~50–150 ms | "Is this person finished?" |

**VAD never commits a turn.** It detects speech onset (driving barge-in) and
sustained silence (inviting the semantic layer to evaluate). The semantic model
reads the partial transcript and decides.

### Decision policy

| Condition | Action |
|---|---|
| Silence < 250 ms | Keep listening — do not invoke the model |
| Silence ≥ 250 ms, transcript **incomplete** | Extend window to 1,500 ms |
| Silence ≥ 250 ms, transcript **complete** | **Commit** |
| Silence ≥ 2,000 ms | Commit regardless — safety valve |

The 2,000 ms row is a backstop against a wedged session if the model
persistently reports "incomplete". It is not a design element.

### Tuning bias

NFR-A-03 (≤5% false cuts) is deliberately **tighter** than NFR-A-04 (≤10% false
holds). When they conflict, **hold**. Being interrupted mid-thought is far worse
than waiting an extra 400 ms — and the asymmetry is larger for debate than for
most applications.

## Alternatives considered

### Silence threshold alone — rejected

Cheapest, and produces the characteristic feel of an amateur voice agent. See
the table above. This is the option we are explicitly buying our way out of.

### LiveKit turn-detector — **retained as fallback**

A Qwen2.5-0.5B fine-tune, "selected for strong performance on this task while
enabling low-latency CPU inference" **[SOURCED]**, Apache-licensed, well
documented on [Hugging Face](https://huggingface.co/livekit/turn-detector).

Genuinely competitive with Smart Turn v2. Rejected as primary only because Smart
Turn ships with Pipecat ([ADR-0003](0003-pipecat-as-orchestration-framework.md)),
removing an integration. **We can adopt LiveKit's model without adopting
LiveKit's framework** — it is a model file, not a platform.

### Deepgram Flux — disqualified

Cloud. NFR-S-01.

### Punctuation heuristic — **retained as second fallback**

Commit when the partial transcript ends in `.`/`!`/`?` **and** silence exceeds
600 ms; otherwise extend to 1,500 ms.

Crude, free, and worth writing down because it is what ships if both models prove
too slow. It is substantially better than a fixed timer and costs nothing. It
fails on transcripts without punctuation, which is a real limitation of many ASR
outputs.

### Push-to-talk only — rejected as default, **required as escape hatch**

Eliminates the problem entirely and destroys the conversational feel. Rejected
as the default, but FR-43 makes it a required user-selectable fallback — this is
the highest-uncertainty component in the system and the user deserves a way out
if it misbehaves in their environment.

### LLM-based detection (ask Qwen3.5 "is this complete?") — rejected

Would work. Costs a full LLM round-trip (~300 ms+) on **every pause**, competing
with the GPU work that produces the actual response. Wrong resource, and it
would blow NFR-P-10 by itself.

## Consequences

### Positive
- Handles thinking pauses correctly — the central requirement.
- VAD stays instant for barge-in; the semantic model never sits in that path.
- Both run on CPU, no VRAM ([ADR-0004](0004-cpu-placement-for-stt-and-tts.md)).
- Two clean fallbacks plus a manual escape hatch.
- Matches 2026 industry practice.

### Negative
- **Adds 150 ms to the latency budget** (NFR-P-10). Partly recovered by running
  it concurrently with STT finalisation
  ([Latency Budget §4](../07-latency-budget.md)).
- **Tuning is empirical, not analytical.** The thresholds above are starting
  guesses. Getting this right needs recorded audio of real pausing behaviour and
  iteration — it cannot be reasoned to.
- Depends on partial transcripts, which Parakeet does not stream natively
  ([ADR-0005](0005-parakeet-tdt-for-stt.md)). Mitigated by re-transcribing the
  buffer every ~500 ms.
- Failure mode is subtle: the system works, tests pass, and it *feels* wrong.
  [RISK-05](../../06-governance/01-risk-register.md).

### Neutral
- Couples us to Pipecat's model, though the fallbacks are drop-in.

## Revisit when

- Measured false-cut rate exceeds 5% (NFR-A-03) → try LiveKit's model.
- Semantic detection exceeds 150 ms (NFR-P-10) → punctuation heuristic.
- Users habitually enable push-to-talk → the automatic path has failed and
  needs rework, not tuning.
- A turn detector trained on **argumentative** speech appears. Debate pausing
  patterns differ from customer-service speech, and models trained on the latter
  may transfer poorly.

## Verification

| Method | Measures |
|---|---|
| Recorded fixtures with deliberate mid-sentence pauses | False-cut rate (NFR-A-03) |
| Recorded fixtures with clean turn ends | False-hold rate (NFR-A-04) |
| **BM-03** | Inference latency on CPU under load (NFR-P-10) |
| Manual session use | Subjective feel — the only test that really matters here |

> The fixture suite must be recorded from **real argumentative speech**, not read
> sentences. The pausing patterns are different, and a model tuned on clean
> recordings will fail on the actual use case.

# Architecture Decision Records

Each ADR records one significant decision: the context that forced it, the
options considered, the choice, its consequences, and **the conditions under
which it should be revisited**.

That last section is the point. A decision without a revisit trigger becomes
folklore — something the team does because it always has, long after the
constraint that justified it has gone.

## Index

| # | Decision | Status | Confidence | Reversibility |
|---|---|---|---|---|
| [0001](0001-cascaded-pipeline-over-speech-to-speech.md) | Cascaded STT→LLM→TTS, not speech-to-speech | Accepted | High | Hard |
| [0002](0002-llama-cpp-server-as-llm-runtime.md) | llama.cpp `llama-server` as a separate process | Accepted | High | Easy |
| [0003](0003-pipecat-as-orchestration-framework.md) | Pipecat for orchestration | Accepted | Medium | Moderate |
| [0004](0004-cpu-placement-for-stt-and-tts.md) | LLM on GPU; everything else on CPU | Accepted | High | Easy |
| [0005](0005-parakeet-tdt-for-stt.md) | Parakeet TDT 0.6B v3 for STT | Accepted | Medium | Easy |
| [0006](0006-kokoro-for-tts.md) | Kokoro-82M for TTS | Accepted | Medium | Easy |
| [0007](0007-two-layer-turn-detection.md) | Two-layer turn detection (VAD + semantic) | Accepted | High | Moderate |
| [0008](0008-headphones-first-audio-transport.md) | ~~Headphones-first audio; AEC deferred~~ | **Superseded by 0012** | — | — |
| [0009](0009-python-as-orchestration-language.md) | Python 3.11 for orchestration | Accepted | High | Hard |
| [0010](0010-sqlite-for-session-persistence.md) | SQLite for persistence | Accepted | High | Easy |
| [0011](0011-yaml-configuration-and-versioned-prompts.md) | YAML config; prompts as versioned files | Accepted | High | Easy |
| [0012](0012-browser-webrtc-transport-with-aec.md) | Browser/WebRTC transport with AEC | Accepted | Medium-high | Moderate |

## Reading the columns

**Confidence** — how sure we are this is right, given that most component
choices rest on third-party benchmarks not yet reproduced on the target machine.

**Reversibility** — cost of changing course later.

| | Meaning |
|---|---|
| Easy | One component behind an interface. Hours. |
| Moderate | Touches several components or the pipeline shape. Days. |
| Hard | Structural. Weeks, or a rewrite. |

The combination that deserves attention is **low confidence + hard
reversibility** — nothing currently sits there.

> **ADR-0008 is the worked example of why this table exists.** It was marked
> Provisional at Low confidence with Moderate reversibility, pending an answer
> from the user. The answer came back the other way, and the cost was ~3 days of
> schedule rather than a rewrite — because the low confidence was declared up
> front and the affected component sat behind an interface. See
> [ADR-0012](0012-browser-webrtc-transport-with-aec.md).

## Status values

| Status | Meaning |
|---|---|
| **Proposed** | Under discussion |
| **Accepted** | Decided; implementation should follow it |
| **Provisional** | Decided *pending* a specific open question |
| **Superseded** | Replaced — links to the ADR that replaced it |
| **Deprecated** | No longer applies; not replaced |

## Template

```markdown
# ADR-NNNN: <title>

| Status | Date | Deciders | Confidence | Reversibility |

## Context
What forces the decision. Constraints, requirements, measurements.

## Decision
What we are doing. One paragraph.

## Alternatives considered
Each with why it was rejected. Rejected options are the valuable part —
they stop the same ground being re-litigated.

## Consequences
### Positive / ### Negative / ### Neutral

## Revisit when
Concrete triggers. Not "if problems arise".
```

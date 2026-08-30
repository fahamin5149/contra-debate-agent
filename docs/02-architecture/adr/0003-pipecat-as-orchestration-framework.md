# ADR-0003: Pipecat as the orchestration framework

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | Medium | Moderate |

## Context

Something must coordinate audio capture, VAD, turn detection, STT, LLM
streaming, sentence segmentation, TTS, playback, and interruption. That
coordination — particularly the interruption path — is where voice agents
actually get hard.

Three credible options: Pipecat, LiveKit Agents, or writing it ourselves.

## Decision

**Pipecat.**

## Alternatives considered

### LiveKit Agents — rejected

A strong framework (11,356 stars as of Jul 2026) whose strengths are:

- WebRTC transport and network resilience
- SIP trunking for telephony
- Scaling to thousands of concurrent calls
- A room model making multi-participant sessions native

**Every one of those addresses a problem we do not have.** We have one user, on
one laptop, with no telephony and no multi-user
([Vision & Scope §5](../../00-product/01-vision-and-scope.md)). Adopting LiveKit
means carrying WebRTC signalling infrastructure to solve a single-machine audio
problem.

Its turn detector — a Qwen2.5-0.5B fine-tune — is genuinely good and remains our
**fallback** for that component specifically
([ADR-0007](0007-two-layer-turn-detection.md)). We can use the model without the
framework.

### Do it ourselves (asyncio + `sounddevice`) — rejected, but closely

Genuinely tempting. Roughly 500 lines, complete control, no framework
abstractions to fight, and no dependency that might drift.

Rejected on one specific point: **acoustic echo cancellation.**

Without AEC, the agent's speaker output re-enters the microphone, trips VAD, and
the agent interrupts itself indefinitely. AEC is hard signal processing, hardest
precisely during double-talk — the barge-in moment. Pipecat provides it; writing
it is out of scope for this project.

The secondary point is that barge-in coordination — cancelling TTS, cancelling
the LLM, truncating history, all within 300 ms — is more intricate than it looks,
and a framework that has already solved it is worth the abstraction cost.

> **Update 2026-08-30 — this argument got stronger.**
> [OQ-01](../../06-governance/05-open-questions.md) has resolved to **speakers**.
> The caveat originally recorded here — that a headphones-only answer would make
> AEC unnecessary and DIY competitive — did not materialise. AEC is now
> mandatory, and Pipecat's WebRTC transport and audio handling are doing real
> work. See [ADR-0012](0012-browser-webrtc-transport-with-aec.md).

### Higher-level platforms (Vapi, Bland, Retell) — disqualified

Cloud-hosted. NFR-S-01 forbids it. Not discussed further.

## Consequences

### Positive
- Purpose-built for exactly this pipeline shape; the hard parts are solved.
- Ships **Smart Turn v2** — removes an integration for our highest-uncertainty
  component.
- Built-in echo cancellation and barge-in handling.
- Large integration library: swapping TTS is close to a one-line change, which
  directly serves NFR-M-01 — and we *expect* to swap components, because several
  choices rest on unreproduced benchmarks.
- Has an OpenAI-compatible LLM service that points straight at `llama-server`.
- Most active of the options (13,416 stars, near-daily development).

### Negative
- **A framework's shape becomes our shape.** Pipecat's pipeline abstraction
  constrains how we express the FR-13 spoken-history truncation, which is
  unusual and may not map cleanly onto its frame model. This is the main
  integration risk.
- Dependency on a fast-moving project; breaking changes are likely.
- Debugging through framework layers is harder than debugging our own loop.
- Brings transitive dependencies we do not need.

### Neutral
- Python-only. Already decided ([ADR-0009](0009-python-as-orchestration-language.md)).

## Revisit when

- **Phase 1 spike shows FR-13 cannot be expressed cleanly** in Pipecat's frame
  model. This is the specific thing to probe first — build the barge-in
  truncation path before building anything else.
- ~~OQ-01 resolves to headphones-only~~ — resolved to **speakers**, which
  strengthens this decision rather than weakening it.
- Framework overhead measurably costs more than 50 ms per turn.
- The project stalls or breaks compatibility badly.

## Mitigation

Our own components sit behind our own interfaces
([Component Design](../02-component-design.md)), with Pipecat used as the
*runtime* rather than as the *architecture*. If we leave, the stages come with
us; only the pipeline assembly is rewritten. This keeps reversibility at
"Moderate" rather than "Hard".

## References

- [Component Evaluation §6](../../01-research/04-component-evaluation.md)
- [Pipecat vs LiveKit — Evalgent](https://www.evalgent.com/blog/pipecat-vs-livekit)

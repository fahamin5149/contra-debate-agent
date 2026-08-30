# ADR-0008: Headphones-first audio transport; AEC deferred

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| **SUPERSEDED** by [ADR-0012](0012-browser-webrtc-transport-with-aec.md) | 2026-08-30 | — | — |

> ## ⚠ Superseded on 2026-08-30
>
> This ADR was **Provisional**, pending
> [OQ-01](../../06-governance/05-open-questions.md). The user has since confirmed
> they will use **speakers**, not headphones. The assumption this decision rested
> on is void.
>
> **The current decision is [ADR-0012](0012-browser-webrtc-transport-with-aec.md):**
> browser/WebRTC transport with acoustic echo cancellation.
>
> Retained unedited below, because the reasoning is still worth reading — in
> particular the analysis of *why* AEC is hard, which is now the problem we have
> to solve rather than the one we avoided. The "Alternatives considered" section
> also correctly identified the browser transport as the answer if OQ-01 went
> this way.
>
> **Lesson worth recording:** the Provisional marking and the interface boundary
> in [Component Design §2](../02-component-design.md) did their job. The reversal
> cost roughly three days of schedule, not a rewrite.

## Context

The microphone stays live while the agent speaks — that is what makes barge-in
possible ([Data Flow & State §1](../04-data-flow-and-state.md)).

This creates a feedback path. If the agent's output plays through **speakers**,
it reaches the microphone, VAD registers speech, barge-in fires, and **the agent
interrupts itself.** Then it does so again. Indefinitely.

The standard fix is **acoustic echo cancellation** — subtracting the known output
signal from the microphone input. AEC is hard, and it is hardest precisely when
it matters most: during *double-talk*, when the user speaks over the agent. False
suppression of the user's speech is the common failure there **[SOURCED]**.

There is a second, simpler fix.

> **Headphones eliminate the problem rather than solving it.** No speaker→
> microphone path exists, so there is nothing to cancel. This is a legitimate
> engineering answer for a single-user local product, not a dodge.

The transport choice follows from this, because AEC availability differs sharply:

| Transport | AEC |
|---|---|
| Browser (WebRTC) | Google's production AEC free via `getUserMedia({echoCancellation: true})` |
| Native Python (`sounddevice`) | **None** |
| Pipecat local transport | Built-in AEC available |

## Decision

**Design headphones-first. Build a native local audio transport. Defer AEC.**

Concretely:

1. v1 documents **headphones as a requirement** in the minimum specification.
2. `AudioInput` / `AudioOutput` sit behind interfaces
   ([Component Design §2](../02-component-design.md)), so the transport is
   replaceable without touching the pipeline.
3. Pipecat's AEC is enabled if available at no cost, but **correctness does not
   depend on it**.
4. A browser transport is a Phase 4 item if speaker support becomes required.

## Alternatives considered

### Browser/WebRTC transport from the start — rejected for v1

**The strongest technical argument against this ADR**, and it deserves a fair
hearing:

- Free, production-quality AEC — the hardest problem, solved
- Free device enumeration and permission UI
- The transcript UI already wants a browser
- Matches how commercial voice agents are actually built
- Works with speakers, headphones, Bluetooth, anything

Rejected for v1 because it front-loads WebRTC signalling, a local web server for
media, and browser audio-permission handling — real complexity — to solve a
problem that **headphones make disappear**. For a single user on one machine,
that is a poor trade at this stage.

It remains the correct answer if OQ-01 comes back as "speakers" or "both".

### Native audio with hand-written AEC — rejected

Writing AEC is out of scope. WebRTC's implementation represents many
person-years of work, and a naive version fails exactly during double-talk.

### Half-duplex — mute the mic while speaking — rejected

Trivially eliminates echo. **Also eliminates barge-in** (FR-12), which is a P0
requirement and one of the three things that make the agent feel like a
conversation rather than a walkie-talkie. Not acceptable.

### Push-to-talk only — rejected as primary

Same effect as half-duplex, with the same cost. Retained as an escape hatch
(FR-43) for a different reason — turn-detection failure, not echo.

## Consequences

### Positive
- Removes the hardest signal-processing problem from v1 entirely.
- Native audio is simpler: no signalling, no server, no browser permissions.
- Lower latency — no WebRTC encode/decode/jitter-buffer path.
- Faster to a working prototype, which is what Phase 1 needs.

### Negative
- **Imposes a hardware requirement on the user.** Headphones are listed in the
  minimum spec ([Hardware Baseline §5](../../01-research/03-hardware-baseline.md)),
  and a user who ignores it gets bizarre behaviour — an agent interrupting itself
  — with no obvious cause.

  *Mitigation:* startup should detect speaker output and warn explicitly. This is
  a real usability cost, not a hypothetical one.

- Rules out casual speaker use, which is how many people would want to use a
  conversational tool.
- If OQ-01 resolves to "speakers" or "both", this work is partly wasted and the
  browser transport must be built anyway.
- Bluetooth headsets often introduce 100–200 ms of latency, which eats directly
  into NFR-P-03's barge-in budget. Wired is preferable and should be documented.

### Neutral
- Couples loosely to [ADR-0003](0003-pipecat-as-orchestration-framework.md). If
  headphones are guaranteed, one of Pipecat's main advantages (AEC) disappears,
  and the DIY option becomes more attractive. **These two ADRs should be
  revisited together.**

## Revisit when

- **[OQ-01](../../06-governance/05-open-questions.md) is answered.** This is the
  primary trigger. If the answer is "speakers" or "both", this ADR is superseded
  by a browser/WebRTC transport decision.
- Self-interruption is observed even with headphones (possible with open-backed
  designs at high volume).
- The product is shared with anyone other than its author, at which point
  "headphones required" becomes a much larger imposition.

## Note on why this was decided rather than blocked

The user declined to answer OQ-01 when asked and directed that work proceed. The
interface boundary in [Component Design §2](../02-component-design.md) is what
makes that safe: the transport is one component, and swapping it does not touch
VAD, STT, the LLM, TTS, or the debate core.

**Cost of choosing wrong: roughly 2–3 days** to build a browser transport in
Phase 4. That is an acceptable price for not blocking, and it is why this is
marked Provisional rather than Accepted.

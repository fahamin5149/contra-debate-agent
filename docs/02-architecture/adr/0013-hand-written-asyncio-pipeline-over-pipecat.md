# ADR-0013: Hand-written asyncio pipeline instead of Pipecat

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| **Accepted** | 2026-08-31 | **High** — backed by measurement | Easy |

**Supersedes** [ADR-0003](0003-pipecat-as-orchestration-framework.md).
**Evidence** [`spikes/pipecat_fr13/README.md`](../../../spikes/pipecat_fr13/README.md)

## Context

[ADR-0003](0003-pipecat-as-orchestration-framework.md) chose Pipecat as the
orchestration framework, with one named revisit trigger:

> *"Phase 1 spike shows FR-13 cannot be expressed cleanly in Pipecat's frame
> model. This is the specific thing to probe first."*

Phase 1 ran that spike against `pipecat-ai` 1.8.1. **It failed.**

FR-13 requires that after a barge-in, history records what was *spoken*, not what
was *generated* — which needs a mapping from audio actually played back to a text
offset.

Three findings, from reading and executing Pipecat 1.8.1:

1. **`TTSAudioRawFrame` has a usable `metadata` dict** — so a `text_span` can be
   attached to an emitted frame.

2. **`BaseOutputTransport.handle_audio_frame` destroys it.** Audio is appended to
   a shared `bytearray` and re-cut at `_audio_chunk_size` boundaries into fresh
   objects carrying only `sample_rate`, `num_channels` and
   `transport_destination`. Verified empirically:
   ```
   source frame metadata: {'text_span': (0, 33)}
   re-chunked metadata  : {}
   ```
   Because re-chunking crosses source-frame boundaries, the association is lost
   at the *byte* level, not just the object level.

3. **No frame carries playback position.** `InterruptionFrame()`,
   `BotStoppedSpeakingFrame()`, `BotStartedSpeakingFrame()` and
   `BotSpeakingFrame()` all take zero constructor arguments.
   `handle_interruptions` resets the queue and reports nothing.

## Decision

**Use a hand-written asyncio session loop.** Pipecat is not a dependency.

The Phase 1 implementation is ~120 lines
([`debate/session.py`](../../../src/contra/debate/session.py)) plus a
span-tracking `PlaybackQueue`
([`audio/webrtc_transport.py`](../../../src/contra/audio/webrtc_transport.py)).

**Adopt Pipecat's *models* without its pipeline.** Pipecat ships
`smart-turn-v3.2-cpu.onnx`; Phase 2 loads that file directly with `onnxruntime`,
exactly as we did for Silero rather than taking the PyTorch `silero-vad` package.

## Alternatives considered

### Subclass `BaseOutputTransport` and patch the re-chunking — rejected

Technically possible: override `handle_audio_frame` to preserve metadata, and
override the interruption path to report position.

Rejected because it means depending on private internals (`_audio_buffer`,
`_audio_chunk_size`, `_audio_queue`) that carry no compatibility promise, in a
fast-moving project. **This is exactly the fragility ADR-0003 was hedging
against** — and it would have to be re-verified on every upgrade, for the single
most subtle requirement in the system.

### Adopt Pipecat and drop FR-13 — rejected

FR-13 is P0. Without it the agent references arguments the user never heard,
which reads as fabrication and destroys trust in a product whose entire value is
being a credible interlocutor.

### LiveKit Agents instead — not evaluated, still available

ADR-0003 rejected LiveKit because its strengths (WebRTC transport, SIP, scale,
multi-participant rooms) address problems we do not have. That reasoning is
unchanged, and the browser now handles AEC
([ADR-0012](0012-browser-webrtc-transport-with-aec.md)). Not re-opened.

## Consequences

### Positive
- **FR-13 works.** Verified by unit tests (invariant I-3) and by
  `tests/integration/test_webrtc_loopback.py`, which shows `PlaybackPosition`
  advancing correctly over a live peer connection with real Opus and ICE.
- One fewer large dependency, and a materially smaller install.
- No framework abstractions between us and the audio path — debugging is direct.
- The loop is small enough to hold in your head, which matters most in exactly
  the barge-in code that is hardest to reason about.

### Negative
- **We own the hard parts now.** Barge-in coordination, turn-detection wiring,
  and error recovery are ours to write in Phase 2. ADR-0003 valued Pipecat
  precisely for having solved these.
- **No integration library.** Swapping TTS is a new adapter behind our
  `TtsStage` protocol rather than a one-line framework change. NFR-M-01 still
  holds — the interfaces exist — but the work is ours.
- We forgo Pipecat's built-in AEC. Not a loss: the browser does AEC
  ([ADR-0012](0012-browser-webrtc-transport-with-aec.md)), which is why this
  cost is affordable.
- Less community-tested than a framework with 13k stars.

### Neutral
- Pipecat's model files remain usable à la carte.

## Revisit when

- Pipecat's output transport gains first-class playback-position reporting, or
  preserves frame metadata across re-chunking. Re-run
  `spikes/pipecat_fr13/probe.py` against the new version.
- Our hand-written loop exceeds ~400 lines or grows a bug class we cannot keep
  on top of — at which point the maintenance argument for a framework returns.
- Multi-participant or telephony enters scope (it is explicitly out —
  [Vision & Scope §5](../../00-product/01-vision-and-scope.md)).

## Note on how this went right

ADR-0003 was marked **Medium** confidence with **Moderate** reversibility, and
named a single concrete probe as its revisit trigger. Phase 1 ran that probe
before building on the framework.

Cost of the reversal: **zero rework** — Phase 1 had deliberately not integrated
Pipecat yet, precisely because this question was open. The plan's Task 14 was
scheduled last for that reason.

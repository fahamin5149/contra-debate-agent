# ADR-0014: Account for playback at the browser output boundary

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| **Proposed — not accepted** | 2026-09-06 | Medium on mechanism; target-machine AEC and output timing unmeasured | Moderate |

## Context

[FR-13](../../00-product/02-product-requirements.md) and
[I-3](../04-data-flow-and-state.md) require spoken history, not generated or
transmitted history. [VERIFIED: source inspection, 2026-09-06]
[`PlaybackQueue.read()`](../../../src/contra/audio/webrtc_transport.py) advances
`last_complete_span_end` before resampling, Opus encoding, delivery, and browser
playback. Its loopback test establishes transport consumption, not audibility.
[`ConversationState`](../../../src/contra/debate/conversation.py) can truncate
correctly only if its input position is correct.

[VERIFIED: primary specification]
[WebRTC synchronization-source timestamps](https://www.w3.org/TR/webrtc/#dom-rtcrtpreceiver-getsynchronizationsources)
describe delivery to a receiver track even without a playback sink. They cannot
establish what the user heard. A fixed subtraction of estimated jitter latency
would not resolve packet loss, a suspended sink, or an interrupted device.

## Proposed decision

Keep the microphone on the existing AEC-enabled WebRTC audio track. Send outbound
PCM16 audio, with explicit generation and sample offsets, through an ordered,
reliable RTCDataChannel on the **same local peer connection**. Render it through
a bounded AudioWorklet queue connected once to the browser AudioContext
destination. An independent control channel carries stop, readiness, and
acknowledgements. The worklet rejects closed generations even if their audio
arrives late.

This is a proposed refinement of [ADR-0012](0012-browser-webrtc-transport-with-aec.md):
the browser and WebRTC remain mandatory in both directions, but outbound audio
uses SCTP data rather than the RTP track. Do not activate this path before this
ADR is accepted and BM-05 is repeated against this exact rendering graph.
Keep ADR-0012's prior reasoning; annotate the outbound-track refinement if this
proposal is accepted. [ADR-0013](0013-hand-written-asyncio-pipeline-over-pipecat.md)
and CPU-only speech placement remain in force.

The browser reports completed render spans and their AudioContext end frames.
Only promote them to acknowledged output after `getOutputTimestamp().contextTime`
has passed their end, with a measured conservative guard. [VERIFIED: primary
specification] [Web Audio output timestamps](https://www.w3.org/TR/webaudio/#dom-audiocontext-getoutputtimestamp)
estimate output-device sample position; they are not a microphone measurement.
Do not extrapolate acknowledgement from elapsed wall time. A suspended context,
muted output, stale timestamp, or missing acknowledgement cannot advance history.

Stop invalidates the generation, discards unsent PCM, and sends a control message
before awaiting TTS or LLM cleanup. A browser stop clears the worklet and freezes
the conservative acknowledgement immediately. Remaining device-buffer audio may
still be heard; record only the acknowledged prefix. Normal completion waits for
the final acknowledgement before committing history.

TTS text spans remain whole synthesis units. A partial unit is omitted per
[Internal API D.5](../05-internal-api-spec.md); no sample/character proportional
interpolation and no invented word timestamps. This does not promise exact
word-level recovery inside a long unit.

For PTT, preserve the release boundary with an indexed PCM capture stream on a
third ordered datachannel, `contra-ptt`, fed from the same AEC-enabled microphone
through a 16 kHz capture AudioWorklet. Automatic mode retains RTP capture. The
server selects exactly one source per mode. An end marker follows the final
partial PCM frame; an HTTP release notification alone never commits an incomplete
capture. The capture graph is not monitored to speakers. This refinement must
pass the same offline and double-talk tests; unsupported capture sample rates
produce a named error rather than unchecked conversion.

## Alternatives considered

| Alternative | Assessment |
|---|---|
| Existing sender consumption counter | Rejected: credits audio that has not reached the browser. |
| Subtract a fixed 100 ms from sender time | Rejected: an average cannot bound jitter, device stalls, or packet loss. |
| RTP plus receiver stats | Close alternative, but public receiver stats do not associate our source text spans with audible samples; private aiortc RTP hooks recreate the coupling rejected by ADR-0013. |
| Native Python playback | Rejected by ADR-0012's speaker/AEC constraint. |
| Return an empty assistant turn after every interruption | Rejected: conceals missing playback accounting and loses useful spoken history. |
| One WebSocket for audio, UI, and cancellation | Rejected here: would change the WebRTC decision and couples cancellation latency to queued audio and UI messages. |
| Timestamp-aware WebRTC sender/receiver adapter | Retained if a public, supported API becomes available and can prove the same output boundary. |

## Consequences

### Positive

- Generation IDs and sample offsets survive end to end.
- The browser can discard stale audio before it is rendered.
- Output credit bounds buffered audio, independent of sentence duration.
- Python orchestration remains behind `AudioOutput`; model adapters do not know
  about the browser protocol.

### Negative

- We own PCM framing, credit flow, and browser rendering tests.
- Reliable SCTP can suffer head-of-line delay. Separate control traffic and
  bounded audio credit reduce exposure; they do not prove NFR-P-03.
- [ASSUMED] Chrome on this machine supplies a usable AEC reference from the
  AudioWorklet destination. This belongs to **RISK-12 / OQ-09**, remains open,
  and must be resolved by BM-05 against the new graph.
- [ASSUMED] Output timestamps plus a calibrated guard provide a conservative
  acknowledgement boundary on the supported device. This is a new verification
  obligation, not proof of physical audibility. If interrupted/suspended-device
  trials over-credit audio, this design is not accepted for FR-13.
  Tracked as [OQ-10](../../06-governance/05-open-questions.md#oq-10--can-browser-output-acknowledgements-safely-bound-spoken-history).
- Background-tab throttling can delay control and acknowledgement. A progress
  watchdog must stop safely; background support must be measured.

### Neutral

No Pipecat runtime, cloud service, second GPU tenant, or new product feature.
24 kHz mono PCM16 costs [ESTIMATED] `24,000 × 2 = 48,000 bytes/s`, excluding
framing. A 100 ms credit window holds `48,000 × 0.1 = 4,800 bytes` of PCM.

## Revisit when

- BM-05 fails 0 self-triggers/5 min or 18/20 preserved interruptions.
- Any acoustic trial shows acknowledged text ahead of audible output.
- Stop exceeds 300 ms, or PCM/credit buffering cannot meet NFR-P-14.
- Device changes invalidate the output guard or output timestamp support.
- Background operation fails the same acceptance criteria as foreground.

## Verification and acceptance

Follow Tasks 1, 7–9, and 16–18 of the
[Phase 2 plan](../../superpowers/plans/2026-09-06-phase-2-turn-detection-and-barge-in.md).
Evidence must include muted/suspended output, browser termination, late packets,
partial synthesis units, two consecutive interruptions, actual acoustic stop
latency, and AEC double-talk. Proposed status is not permission to bypass these
gates. Acceptance must name the tested browser/device and evidence files.

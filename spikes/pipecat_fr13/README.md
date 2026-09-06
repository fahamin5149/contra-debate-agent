# Spike: FR-13 expressibility in Pipecat

| | |
|---|---|
| **Status** | **COMPLETE** |
| **Date** | 2026-08-31 |
| **Version probed** | `pipecat-ai` 1.8.1, Python 3.11.9 |
| **Verdict** | ❌ **FAIL** — FR-13 is not expressible without patching framework internals |

---

## The question

[ADR-0003](../../docs/02-architecture/adr/0003-pipecat-as-orchestration-framework.md)
names exactly one revisit trigger:

> *"Phase 1 spike shows FR-13 cannot be expressed cleanly in Pipecat's frame
> model. This is the specific thing to probe first."*

FR-13 requires that after a barge-in, conversation history records what was
**spoken**, not what was **generated**. That needs a mapping from *audio
actually played* back to *a text offset*.

---

## Findings

### Q1 — Can a TTS audio frame carry text-span metadata? **Partial yes**

`TTSAudioRawFrame` is a dataclass with a usable `metadata: dict[str, Any]`
field, plus `context_id`, `id`, and `pts`:

```
signature: (audio: bytes, sample_rate: int, num_channels: int, context_id: str | None = None)
fields:    audio, sample_rate, num_channels, num_frames, id, name, pts,
           broadcast_sibling_id, metadata, transport_source,
           transport_destination, context_id
```

So we *can* attach `text_span` to a frame we emit. The problem is what happens
to it next.

### Q2 — Can we observe what was actually PLAYED? **No**

`BaseOutputTransport.handle_audio_frame` (`base_output.py:605-621`) re-chunks
audio into fresh objects:

```python
cls = type(frame)
self._audio_buffer.extend(resampled)
while len(self._audio_buffer) >= self._audio_chunk_size:
    chunk = cls(
        bytes(self._audio_buffer[: self._audio_chunk_size]),
        sample_rate=self._sample_rate,
        num_channels=frame.num_channels,
    )
    chunk.transport_destination = self._destination
    await self._audio_queue.put(chunk)
```

Only `sample_rate`, `num_channels` and `transport_destination` are carried
across. **`metadata`, `context_id`, `id` and `pts` are all dropped.**

Confirmed empirically:

```
source frame metadata: {'text_span': (0, 33)}
re-chunked metadata  : {}
re-chunked context_id: None
METADATA SURVIVES RE-CHUNKING: False
```

Worse than object identity: incoming audio is appended into a shared
`_audio_buffer` bytearray and re-cut at `_audio_chunk_size` boundaries, so **a
single output chunk can span two source frames.** The span association is
destroyed at the byte level, not merely the object level. Even a metadata-
preserving patch would have to decide how to split a span across a chunk
boundary.

### Q3 — On interruption, can we recover the played offset? **No**

`handle_interruptions` (`base_output.py:566`) discards pending audio and
reports nothing about position:

```python
async def handle_interruptions(self, _: InterruptionFrame):
    await self._cancel_clock_task()
    await self._cancel_video_task()
    if self._audio_queue.has_uninterruptible or self._mixer:
        self._audio_queue.reset()
    else:
        await self._cancel_audio_task()
        self._create_audio_task()
    ...
    await self._bot_stopped_speaking()
```

And every relevant frame is payload-free — all take **zero constructor
arguments**:

```
InterruptionFrame()            -> ()
BotStoppedSpeakingFrame()      -> ()
BotStartedSpeakingFrame()      -> ()
BotSpeakingFrame()             -> ()
```

There is no `PlaybackPosition` equivalent anywhere in the model.

---

## Verdict: FAIL

FR-13 cannot be expressed in Pipecat 1.8.1's frame model without subclassing
`BaseOutputTransport` and overriding `handle_audio_frame` plus the interruption
path — i.e. depending on framework internals that carry no compatibility
promise. That is precisely the fragility ADR-0003 was hedging against.

**ADR-0003's revisit trigger has fired.**

### Why this is not a crisis

The Phase 1 implementation already solves it, in ~120 lines with no framework:

- `PlaybackQueue` ([`webrtc_transport.py`](../../src/contra/audio/webrtc_transport.py))
  tracks `last_complete_span_end` and deliberately does **not** count a
  partially-played chunk.
- `ConversationState.truncate_to_spoken()`
  ([`conversation.py`](../../src/contra/debate/conversation.py)) consumes that
  position, with invariant I-3 asserted in unit tests.
- `tests/integration/test_webrtc_loopback.py` proves the position advances
  correctly over a **live peer connection** — real Opus, real ICE, real
  resampling.

We kept audio chunk metadata intact because we never re-chunk across frame
boundaries; the queue reads *from* chunks rather than rebuilding them.

### Recommendation

**Keep the hand-written asyncio session loop. Do not adopt Pipecat for pipeline
assembly in Phase 2.** Supersede ADR-0003 with an ADR recording this evidence.

---

## Salvage: use Pipecat's models without its pipeline

Pipecat ships **`smart-turn-v3.2-cpu.onnx`** inside the package
(`pipecat/audio/turn/smart_turn/data/`). Phase 2 needs semantic turn detection
([ADR-0007](../../docs/02-architecture/adr/0007-two-layer-turn-detection.md)),
and we can load that ONNX file directly with `onnxruntime` — exactly as we did
for Silero rather than taking the `silero-vad` PyTorch package.

That gets the component ADR-0003 most wanted from Pipecat, without the frame
model that fails FR-13.

---

## Reproducing

```powershell
py -3.11 -m venv .venv-spike
.\.venv-spike\Scripts\python.exe -m pip install pipecat-ai
.\.venv-spike\Scripts\python.exe spikes\pipecat_fr13\probe.py
```

> **Install gotcha:** running two `pip install` processes against the same venv
> concurrently deadlocks on Windows with
> `WinError 32 ... smart-turn-v3.2-cpu.onnx is being used by another process`.
> Run one at a time.

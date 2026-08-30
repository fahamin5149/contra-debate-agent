# Spike: FR-13 expressibility in Pipecat

| | |
|---|---|
| **Status** | **NOT RUN** — blocked on install |
| **Date attempted** | 2026-08-31 |
| **Blocker** | `pip install pipecat-ai` did not complete within the session (large dependency tree) |

---

## The question

[ADR-0003](../../docs/02-architecture/adr/0003-pipecat-as-orchestration-framework.md)
names exactly one revisit trigger:

> *"Phase 1 spike shows FR-13 cannot be expressed cleanly in Pipecat's frame
> model. This is the specific thing to probe first."*

This spike answers that, and only that. Three questions:

| | Question |
|---|---|
| **Q1** | Can we attach text-span metadata to a TTS audio frame? |
| **Q2** | Can we observe which audio frames were actually **played**, not just queued? |
| **Q3** | On an interruption, can we recover the played offset before state is lost? |

## How to run it

```powershell
py -3.11 -m venv .venv-spike
.\.venv-spike\Scripts\python.exe -m pip install -U pip
.\.venv-spike\Scripts\python.exe -m pip install pipecat-ai
.\.venv-spike\Scripts\python.exe spikes\pipecat_fr13\probe.py
```

`probe.py` introspects `TTSAudioRawFrame`, the interruption frames, and
`BaseOutputTransport` — it needs no running pipeline.

## Findings

*(unrun — fill in from probe output)*

### Q1 — text-span metadata on a TTS audio frame
### Q2 — observing what was actually played
### Q3 — recovering the played offset on interruption

## Verdict

*(unrun)*

- **PASS** — FR-13 is expressible; adopt Pipecat for Phase 2 pipeline assembly.
- **FAIL** — ADR-0003's revisit trigger has fired. Recommendation: keep the
  hand-written asyncio loop in `src/contra/debate/session.py` and supersede
  ADR-0003.

---

## Why Phase 1 did not need the answer

Phase 1 shipped without Pipecat, using `aiortc` directly plus a ~120-line
asyncio session loop. That was deliberate: Phase 1 uses **none** of Pipecat's
value-adds — barge-in and turn detection are Phase 2, and AEC is the browser's
job (ADR-0012).

The consequence is that this spike is **not urgent, but it is load-bearing for
Phase 2**, where barge-in is built. Running it before Phase 2 starts keeps the
cost of a FAIL at "keep the loop we already have" rather than "unpick an
integration".

> The working `Session` loop is itself partial evidence: it expresses FR-13
> cleanly in ~120 lines, and the loopback test proves `PlaybackPosition`
> advances correctly over a real peer connection. If Pipecat cannot match that,
> the fallback is already written and tested.

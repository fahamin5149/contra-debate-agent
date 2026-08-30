# Observability Specification

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |
| **Satisfies** | FR-42, FR-53, US-503 |

---

## 1. The problem observability solves here

A user says *"it feels slow."*

Without stage attribution that statement is undiagnosable — the cost could be in
VAD, turn detection, STT, prompt assembly, the LLM, segmentation, TTS, or the
output buffer. Eight candidates, and guessing wrong wastes an afternoon.

**Every turn must be decomposable into its stages.** That is the whole
requirement (US-503).

A second, subtler need: some failures here are *slow*. VRAM creep, thermal
throttling, and buffer leaks all present as gradual degradation that is invisible
in any single turn and obvious in a trendline.

---

## 2. The turn record

One structured record per turn, written to the database
(`turn_metrics` — [Data Model §2.3](../02-architecture/06-data-model.md)) and
emitted to the UI (FR-42).

```jsonc
{
  "turn_id": 7,
  "session_id": "…",
  "role": "agent",

  // stage timings (ms) — these must sum to roughly total_ms
  "vad_ms": 250,
  "turn_detect_ms": 118,
  "stt_ms": 205,
  "prompt_build_ms": 8,
  "llm_ttft_ms": 380,
  "tts_ttfb_ms": 140,
  "output_buffer_ms": 100,
  "total_ms": 1193,             // ← the NFR-P-01 metric

  // generation
  "llm_total_ms": 5240,
  "tokens_prompt": 2140,
  "tokens_generated": 164,
  "tokens_per_sec": 31.2,
  "prefix_cache_hit": true,

  // resources
  "vram_used_mib": 6912,
  "rss_mib": 2840,

  // behaviour
  "was_interrupted": false,
  "chars_generated": 612,
  "chars_spoken": 612,
  "audio_frames_dropped": 0
}
```

### The fields that earn their place

| Field | Why |
|---|---|
| `total_ms` | The only user-perceived metric. Everything else is diagnostic. |
| `prefix_cache_hit` | Directly tests [OQ-03](../06-governance/05-open-questions.md) in production. A drop in hit rate explains a TTFT regression instantly. |
| `vram_used_mib` | Per-turn sampling turns NFR-REL-05 leak detection from a mystery crash into a trendline |
| `tokens_per_sec` | Downward drift across a session indicates thermal throttling |
| `chars_generated` vs `chars_spoken` | Quantifies unheard argument — informs whether responses are too long (FR-31) |
| `audio_frames_dropped` | **Should always be 0.** Non-zero means GIL contention — [ADR-0009](../02-architecture/adr/0009-python-as-orchestration-language.md) |

---

## 3. Structured logging

```python
log.info("stage_complete",
         session_id=sid, turn_id=7, stage="stt",
         duration_ms=205, confidence=0.94)
```

JSON lines to `data/contra.log`, human-readable to the console.

### Levels

| Level | Contents |
|---|---|
| `DEBUG` | Per-frame VAD, partial transcripts, token stream. **Off by default** — very high volume |
| `INFO` | Stage completions, state changes, turn boundaries, session lifecycle |
| `WARNING` | Recovered failures, degraded modes, threshold breaches |
| `ERROR` | Failures affecting the session |

### The privacy rule

> **Never log transcript content above `DEBUG`.**
>
> Log files are less protected than the database, are easily copied, and may be
> attached to a bug report without thought. Transcripts are the user's private
> argument content (NFR-S-01). Log lengths, confidences, and IDs — not text.

```python
# WRONG
log.info("user_turn", text=transcript.text)

# RIGHT
log.info("user_turn", chars=len(transcript.text), confidence=transcript.confidence)
```

---

## 4. Correlation

Every log line and metric carries `session_id` and `turn_id`. This makes a single
turn's full story reconstructable:

```powershell
Get-Content data\contra.log | ConvertFrom-Json |
  Where-Object { $_.turn_id -eq 7 } | Format-Table ts, stage, duration_ms
```

No distributed tracing. Two processes on one machine do not justify it
([Architecture Overview §7](../02-architecture/01-architecture-overview.md)).

---

## 5. Live display (FR-42)

Development-mode UI panel:

```
┌─ Turn 7 ─────────────────────────── 1193 ms ─┐
│ VAD          ████                      250   │
│ Turn detect  ██                        118   │
│ STT          ███                       205   │
│ LLM TTFT     ██████                    380   │
│ TTS TTFB     ██                        140   │
│ Buffer       █                         100   │
│                                              │
│ 31.2 tok/s · 164 tok · cache HIT · 6912 MiB  │
└──────────────────────────────────────────────┘
```

> A live latency breakdown changes how development feels. Instead of "that turn
> seemed slow", you see immediately that TTFT was 900 ms and the prefix cache
> missed. The feedback loop between a change and its cost collapses from a
> benchmark run to a single turn.

---

## 6. Session summary

Written on session end:

```
Session 3f2a · 23 min · 31 turns · prompt debate-v3

Latency        p50  1,193 ms    p95  1,840 ms    max  2,410 ms
Generation     avg 30.8 tok/s   min 27.1 (turn 28)
Prefix cache   29/31 hits (94%)
VRAM           start 6,890  peak 6,948  end 6,912 MiB
Interruptions  4 (13% of agent turns)
Unheard        1,840 of 18,200 chars (10%)
Frames dropped 0

⚠  Turn 28 exceeded p95 (2,410 ms) — TTFT 1,180 ms, cache MISS
```

The warning line is the useful part: it names the outlier *and* its likely cause,
rather than leaving a number to be investigated later without context.

---

## 7. Trend analysis

Run periodically over the database:

| Query | Detects |
|---|---|
| p50/p95 latency by session over time | Regressions from changes |
| tokens/sec within long sessions | Thermal throttling |
| VRAM at session end over time | Leaks |
| Prefix cache hit rate by session | Prompt instability breaking the cache |
| Latency by `prompt_version` | Longer prompts costing TTFT |

```sql
-- thermal throttling within a session
SELECT t.turn_index, m.tokens_per_sec
FROM turn_metrics m JOIN turns t ON t.id = m.turn_id
WHERE t.session_id = ? AND t.role = 'agent'
ORDER BY t.turn_index;
```

A downward slope here is throttling. Without per-turn recording it would present
only as "the agent got slower and I'm not sure when".

---

## 8. Alerting

No paging — one local user, who is present. Instead, in-app warnings when a
threshold breaks:

| Condition | Surface |
|---|---|
| Turn > 2,500 ms (NFR-P-02 ceiling) | Log WARNING; UI badge |
| tokens/sec < 20 | Log WARNING once per session |
| VRAM > 7,400 MiB | Log WARNING; suggest reducing context |
| Audio frames dropped > 0 | Log WARNING — should never happen |
| Prefix cache hit rate < 70% | Log WARNING at session end |
| 3 consecutive TTS failures | Spoken notice + fall back to Piper |

---

## 9. What we deliberately do not instrument

| Not instrumented | Why |
|---|---|
| Per-frame VAD in production | Enormous volume, no diagnostic value at 50 fps |
| Individual token timings | `tokens_per_sec` suffices |
| Prompt text per turn | Reconstructable from `prompt_version` + turns; and it is private |
| CPU utilisation continuously | Sampled during benchmarks only |
| Distributed tracing | Two local processes |
| Telemetry of any kind, anywhere | **NFR-S-01.** No data leaves the machine, ever, including crash reports. |

The last row is absolute. Many observability libraries default to sending
anonymised usage data; any such default must be found and disabled, and IT-06
(running with the network adapter down) is what catches them.

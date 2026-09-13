# M2 — Entry gates

| | |
|---|---|
| **Date** | 2026-09-12 |
| **Status** | **BLOCKED — BM-03 failed; BM-05 and M1 acoustic evidence remain** |
| **Branch** | `feat/phase-2-turn-detection-and-barge-in` |

## Baseline

| Check | Result |
|---|---|
| Python | 3.11.9 |
| Unit tests | 57 passed in 4.81 s; one dependency deprecation warning |
| Ruff lint | PASS |
| mypy | PASS, 28 source files |
| Ruff format | FAIL: 11 existing Markdown code fences would be reformatted |

The formatting failure predates Phase 2 source changes and is not attributed to
M2. It must still be resolved before the final gate.

## M0 inventory

| Benchmark | Result | Gate status |
|---|---|---|
| BM-01 — LLM throughput | PASS, 33.1 tok/s median | Satisfied |
| BM-02 — prefix cache | PASS, 3.36× cached advantage; 6.18× post-prefill TTFT speedup | Satisfied |
| BM-03 — CPU speech under load | **FAIL** | Blocking; subprocess mitigation and repeat required |
| BM-04 — VRAM | PASS | Satisfied |
| BM-05 — browser AEC/double-talk | Not run | Blocking; requires target speakers, microphone, room, and human speech |

## M1 inventory

The existing M1 record remains **Partially complete**. The user reports having
tested a real end-to-end spoken exchange, but the date, browser/WebRTC RTT,
turn-latency samples, five-minute self-trigger count, and 20 double-talk trials
have not been recorded. A recollection is useful diagnostic information but is
not substituted for the acceptance record.

## ADR-0014 disposition

ADR-0014 remains **Proposed**. The existing sender-side WebRTC loopback proves
transport consumption, not that the browser output device rendered a specific
text span. Acceptance awaits its playback acknowledgement prototype and BM-05
on the final browser rendering graph.

## Required response

1. Amend ADR-0009 and the Phase 2 worker design for subprocess-isolated CPU
   inference, then repeat BM-03.
2. Run BM-05 using `benchmarks/bm05_echo_cancellation.py` to validate the exact
   20-trial acoustic record.
3. Record the remaining real M1 latency and acoustic evidence.
4. Do not begin Tasks 2–18 until these gates are satisfied, as required by the
   benchmark plan and this repository's root instructions.

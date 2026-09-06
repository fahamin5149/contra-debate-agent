# CLAUDE.md — benchmarks

**This directory runs before `src/` exists.** It is a sibling of `src/`, not of
`tests/`, because these are not tests — they are the measurements that decide
whether the design is viable at all.

Full specification: `../docs/04-quality/03-benchmark-plan.md`.

---

## Why this matters

Every performance and resource number in the design tree is `[SOURCED]` from
third-party benchmarks or `[ESTIMATED]` by arithmetic. **Nothing has been
measured on the target machine.**

The design is internally consistent. That is not the same as being true.

> If BM-01 returns 15 tok/s instead of 30, NFR-P-01 is unreachable and the right
> response is to **change the design** — switch to Qwen3.5-4B — not to discover
> it three weeks into implementation and try to optimise around it.

Five measurements, ~2 days, retire five of the top seven risks.

---

## The five

| ID | File | Measures | Gates |
|---|---|---|---|
| BM-01 | `bm01_llm_throughput.py` | tok/s, TTFT, thermal decay | The whole latency design |
| BM-02 | `bm02_prefix_cache.py` | Prefix reuse across 20 turns | NFR-P-12, speculative prefill |
| BM-03 | `bm03_cpu_speech_rtf.py` | STT/TTS RTF **under GPU load**; GIL frame drops | ADR-0004, ADR-0009 |
| BM-04 | `bm04_vram_profile.py` | Real VRAM; which GPU drives the display | The resource budget |
| BM-05 | `bm05_echo_cancellation.py` | Self-trigger rate; **double-talk** | Barge-in with speakers |

---

## Rules for writing these

**1. Measure under realistic load, not idle.**
BM-03 must run **while the GPU is generating**. Published CPU benchmarks come
from idle machines; ours will be running an audio pipeline and a Python event
loop concurrently. An idle-machine measurement would look reassuring and tell us
nothing.

**2. Measure the thing that decides, not the thing that is easy.**

| Easy and useless | What actually decides |
|---|---|
| TTS RTF on paragraph text | RTF on **15–40 char units** — that is what we stream (ADR-0006) |
| AEC with the user silent | **Double-talk** — barge-in is by definition double-talk |
| tok/s in the first minute | tok/s after 30 minutes — laptop thermal decay |
| STT WER on read speech | WER on **real argumentative speech** with thinking pauses |

**3. Record the environment.** Every result file states: date, GPU, driver,
llama.cpp build, model file size, Python version, and whether the machine was on
mains power. Results without this cannot be compared later.

**4. Verify full GPU offload before trusting any LLM number.**
The load log must say `offloaded 33/33 layers to GPU` and must not mention
`mmproj`. Partial offload collapses throughput; a benchmark run against it
measures nothing useful.

**5. No dependency on `src/`.** These are standalone scripts. They must run
before any application code exists, and they must keep running after it changes.

---

## Result format

One Markdown file per benchmark in `results/`, **committed**:

```markdown
# BM-01 — LLM throughput
Date · GPU · driver · llama.cpp build · model size · Python · mains power?

## Results
<tables, and plots if useful>

## Verdict
PASS / MARGINAL / FAIL

## Consequences for the design
<which documents change, and how>
```

**The last section is the point.** A benchmark producing numbers nobody acts on
is wasted work. Each result must either:

- **confirm** a design assumption → go upgrade the `[SOURCED]` / `[ESTIMATED]`
  markers in the affected documents to `[VERIFIED]`, naming this benchmark, or
- **contradict** one → trigger the documented response in the benchmark plan, and
  update the budget documents with the real numbers.

---

## After all five have run

1. Update `docs/02-architecture/07-latency-budget.md` and
   `08-resource-budget.md` with measured values
2. Upgrade confidence markers wherever measurement supports it
3. Re-score `docs/06-governance/01-risk-register.md` — RISK-01, 02, 03, 06, 12
   should close or be re-scored
4. Close OQ-03, OQ-08, OQ-09 in `docs/06-governance/05-open-questions.md`
5. Record any design change as an ADR

Only then does implementation start (M1 in `docs/07-planning/02-milestones.md`).

---

## Decision points to be ready for

| Result | Action |
|---|---|
| BM-01 < 18 tok/s | **Switch to Qwen3.5-4B before M1.** MMLU-Pro 82.5 → 79.1; survivable. |
| BM-02 flat TTFT across turns | Prefix caching works — speculative prefill is viable |
| BM-02 TTFT grows linearly | Caching broken. Re-derive the latency budget without it. |
| BM-03 dropped audio frames > 0 | **Serious.** GIL not releasing → subprocess isolation, or reconsider Python (ADR-0009). |
| BM-04 idle VRAM > 800 MiB | The 4060 is driving the display — force it to the iGPU |
| BM-05 double-talk < 10/20 | **Push-to-talk becomes the default.** Product change; decide before M2. |

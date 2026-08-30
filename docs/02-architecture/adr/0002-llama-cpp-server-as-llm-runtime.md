# ADR-0002: llama.cpp `llama-server` as a separate process

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | High | Easy |

## Context

We have `Qwen3.5-9B-UD-Q4_K_XL.gguf` locally and need to serve it on an RTX 4060
with 8 GB VRAM, on Windows.

The model uses a hybrid Gated DeltaNet + Gated Attention architecture — 24
linear-attention layers, 8 full-attention — which is newer than most tooling and
requires explicit runtime support.

## Decision

**Run llama.cpp's `llama-server` as a separate OS process**, exposing its
OpenAI-compatible API on `127.0.0.1:8080`. The orchestrator talks to it over
HTTP with the standard `openai` Python SDK.

Launch:
```powershell
.\llama-server.exe -m C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf `
  -ngl 99 -c 16384 -fa --host 127.0.0.1 --port 8080
```

Notably **without** `--mmproj` — the vision projector stays unloaded, saving
0.918 GiB.

## Alternatives considered

### Ollama — **disqualified, not merely rejected**

The convenient choice, and it does not work. Per the
[Unsloth guide](https://unsloth.ai/docs/models/qwen3.5): *"Currently no Qwen3.5
GGUF works in Ollama due to separate mmproj vision files; use llama.cpp
compatible backends."*

This is a hard blocker, not a preference. It is the main reason setup is more
involved than a typical local-LLM project.

### `llama-cpp-python` (in-process binding) — rejected

The interesting comparison. It would embed the model in our Python process,
removing the HTTP hop.

Rejected because **process separation buys more than the hop costs**:

| Benefit | Why it matters here |
|---|---|
| LLM can crash and restart without killing audio | [Sequence Diagrams §5](../03-sequence-diagrams.md) recovery path |
| Model swap without restarting the pipeline | We expect to A/B 9B vs 4B repeatedly |
| Can point at a cloud endpoint for comparison | Useful for judging whether local quality is the bottleneck |
| GPU memory is released cleanly on model exit | Python holding CUDA context complicates this |
| Model load does not block the event loop | 20–40 s cold load |

The cost is one localhost HTTP round-trip — sub-millisecond, against a 400 ms
TTFT. Irrelevant.

### vLLM — rejected

Excellent, and built for datacentre serving with continuous batching for many
concurrent users. We have one user. Windows support is poor. Wrong tool.

### LM Studio — rejected

Serves an OpenAI-compatible API and supports Qwen3.5. GUI-first, awkward to
launch and supervise programmatically (FR-51). Reasonable for manual
experimentation; not for a supervised application.

### SGLang / KTransformers — rejected

Supported by the model per its card, but both are Linux-oriented and add
operational complexity for no benefit at our scale.

## Consequences

### Positive
- Supports the hybrid architecture — **[VERIFIED]** as of Aug 2026, llama.cpp's
  README leads with `llama serve -hf ggml-org/Qwen3.5-0.8B-GGUF`.
- OpenAI-compatible API works with the standard SDK, unmodified.
- Fault isolation between LLM and audio pipeline.
- Excellent GGUF quantization support; swapping quants is a flag change.
- Prebuilt Windows CUDA binaries — no compilation.

### Negative
- **A second process to supervise.** Startup ordering, health checks, restart
  policy, shutdown — all now our problem (FR-51, FR-52).
- **No authentication on `llama-server`.** Loopback binding is therefore a
  security control, not a preference (NFR-S-03,
  [Threat Model](../../06-governance/03-threat-model.md)).
- Support for this architecture is recent. **[SOURCED]** as of ~May 2026 it was
  described as bleeding-edge HEAD rather than stable release —
  [RISK-01](../../06-governance/01-risk-register.md).
- Ollama's ecosystem conveniences are unavailable.

### Neutral
- Ties us to GGUF. Fine — it is the best-supported local format.

## Revisit when

- Ollama gains `mmproj` support **and** the operational simplicity is worth
  losing process-level control.
- llama.cpp's Qwen3.5 support proves unstable in BM-01 — fall back to
  `llama-cpp-python` pinned to a known-good build, or to a different model.
- We need concurrent sessions (we do not, and will not in v1).

## Notes

**Sampling parameters** and the `enable_thinking: false` setting are specified in
[Model Analysis §5](../../01-research/02-model-analysis.md) and
[Internal API Spec §A](../05-internal-api-spec.md).

**`-ngl 99` is mandatory.** Partial offload collapses throughput rather than
degrading it — [Resource Budget §6](../08-resource-budget.md).

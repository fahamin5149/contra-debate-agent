# Model Analysis — Qwen3.5-9B (UD-Q4_K_XL)

| | |
|---|---|
| **Status** | Complete — analysed 2026-08-30 |
| **Subject** | `C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf` |
| **Primary source** | [Qwen/Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B) · [unsloth/Qwen3.5-9B-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF) |

---

## 1. File integrity **[VERIFIED]**

| | |
|---|---|
| Local path | `C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf` |
| Local size | 5.56 GiB |
| Upstream size | 5,966,095,584 bytes = **5.5563 GiB** |
| Modified | 2026-08-28 |
| **Verdict** | **Exact match. Download complete, not truncated.** |

Worth doing before anything else: a truncated GGUF often loads and produces
subtly degraded output rather than failing outright, which is a miserable thing
to debug three weeks later.

---

## 2. Provenance

Released **2026-03-02** as part of Alibaba's Qwen3.5 Small series (0.8B / 2B /
4B / 9B), completing a nine-model rollout in sixteen days. Apache 2.0 licensed.
Base and post-trained variants both published.

The quant is Unsloth's **Dynamic 2.0** scheme (`UD-` prefix), which varies
precision per layer using an importance matrix rather than applying a uniform
4-bit rate — targeted at chat, coding, and tool-calling. In practice this means
better quality than a plain `Q4_K_M` at similar size.

Note that upstream `Q4_K_M` is 5,680,522,464 bytes — *smaller* than the
`UD-Q4_K_XL` you have. The `XL` variant spends extra bits where the imatrix says
they matter.

---

## 3. Architecture — the decisive fact

From the model card **[VERIFIED]**:

```
Hidden Layout: 8 × (3 × (Gated DeltaNet → FFN) → 1 × (Gated Attention → FFN))
```

That is **32 layers in 8 repeating blocks**, each block containing three
linear-attention layers and one full-attention layer — a 3:1 ratio.

| | |
|---|---|
| Total layers | 32 |
| Gated DeltaNet (linear attention) | **24** |
| Gated Attention (full attention) | **8** |
| Hidden dimension | 4,096 |
| FFN intermediate | 12,288 |
| Vocabulary | 248,320 (padded), 201 languages |
| Context | 262,144 native, extensible to ~1,010,000 |

**Gated Attention layers:** 16 query heads, **4 KV heads**, head dimension 256,
RoPE dimension 64.

**Gated DeltaNet layers:** 32 value heads, 16 QK heads, head dimension 128.

### 3.1 Why this is the single luckiest fact about this project

DeltaNet layers maintain a **fixed-size recurrent state** rather than a KV cache
that grows with sequence length. Only the 8 full-attention layers contribute to
KV memory.

**KV cache per token [ESTIMATED — arithmetic shown]:**

```
per full-attention layer = 2 (K and V) × 4 KV heads × 256 head_dim
                         = 2,048 values

across 8 such layers     = 16,384 values / token
at FP16 (2 bytes)        = 32,768 bytes = 32 KiB / token
```

| Context | KV cache |
|---|---|
| 4,096 | 128 MiB |
| 8,192 | 256 MiB |
| **16,384** | **512 MiB** |
| 32,768 | 1,024 MiB |

A conventional dense 9B with 32 full-attention layers and typical GQA would sit
roughly 3–4× higher. **On an 8 GB card, that difference is the project.** It is
what lets us run 16K of debate history and still have headroom.

The DeltaNet recurrent state is additionally **independent of context length** —
a fixed allocation, estimated in the low hundreds of MiB. It does not grow as
the conversation does.

> **Corroboration [SOURCED].** Independent analysis describes Qwen3.5-9B as
> "hybrid DeltaNet+attention with `full_attention_interval=4` — only 8/32 layers
> have full attention", consistent with our reading of the model card.

### 3.2 The offsetting risk

This architecture is *newer* than the tooling around it. Two consequences:

1. **llama.cpp support was bleeding-edge as of ~May 2026** and is first-class by
   August 2026, but the hybrid graph is more recently written than the standard
   transformer path. [RISK-01](../06-governance/01-risk-register.md).
2. **Prefix caching semantics are unclear.** Reusing KV across turns is trivial
   for pure attention. With recurrent state it requires checkpointing, and
   llama.cpp implements this via `llama_memory_hybrid` with `cache_r_l*` /
   `cache_s_l*` states. Whether prefix reuse works as efficiently as for a
   standard model is **unverified and load-bearing for NFR-P-12**.
   [OQ-03](../06-governance/05-open-questions.md), benchmark BM-02.

---

## 4. Capability

Reported benchmarks (model card, Qwen3.5-9B column):

| Benchmark | Qwen3.5-9B | GPT-OSS-120B | Qwen3-30B-A3B-Thinking |
|---|---|---|---|
| MMLU-Pro | **82.5** | 80.8 | 80.9 |
| GPQA Diamond | **81.7** | 80.1 | 73.4 |
| MMLU-Redux | 91.1 | 91.0 | 91.4 |
| SuperGPQA | 58.2 | 54.6 | 56.8 |
| IFEval | **91.5** | 88.9 | 88.9 |
| MultiChallenge | **54.5** | 45.3 | 46.5 |
| LongBench v2 | **55.2** | 48.2 | 44.8 |
| AA-LCR | **63.0** | 50.7 | 49.0 |

Vendor-published benchmarks deserve the usual scepticism. Still, two rows matter
disproportionately for us:

- **MultiChallenge (54.5)** measures multi-turn instruction following. A debate
  is a long multi-turn interaction where the agent must hold a position across
  many exchanges. This is the closest published proxy for our core requirement.
- **IFEval (91.5)** measures instruction adherence. Our entire debate persona is
  a system prompt. If the model drifts from instructions, FR-21 and FR-24 fail.

**LongBench v2 (55.2)** and **AA-LCR (63.0)** support the claim that it uses
long context well rather than merely accepting it — relevant to FR-27,
referencing arguments from earlier in the session.

---

## 5. Configuration for this project

### 5.1 Thinking mode — **OFF** **[VERIFIED]**

Reasoning is **disabled by default** on the 0.8B–9B models. This is what we
want. A thinking trace before every rebuttal would add 5–15 seconds of silence
and destroy NFR-P-01.

To enable (we will not):
```powershell
--chat-template-kwargs "{\"enable_thinking\":true}"
```

Per-request via the API: `"chat_template_kwargs": {"enable_thinking": false}`.

### 5.2 Sampling parameters

From the [Unsloth guide](https://unsloth.ai/docs/models/qwen3.5), instruct /
general row:

| Parameter | Value |
|---|---|
| `temperature` | 0.7 |
| `top_p` | 0.8 |
| `top_k` | 20 |
| `min_p` | 0.0 |
| `presence_penalty` | **1.5** |
| `repeat_penalty` | 1.0 (disabled) |

> **`presence_penalty: 1.5` is unusually high and matters here specifically.**
> The characteristic failure of an LLM debater over ten turns is recycling the
> same three talking points in fresh phrasing. A strong presence penalty pushes
> the model toward unused vocabulary and therefore unused arguments. This single
> parameter does real work for FR-29 and US-302's "different angle each time"
> criterion.

Unsloth's troubleshooting note: if output is gibberish, try
`--cache-type-k bf16 --cache-type-v bf16`. Recorded because KV quantization is a
tempting VRAM lever and this is the failure signature to watch for.

### 5.3 Vision — deliberately not loaded

The model is genuinely multimodal (`pipeline_tag: image-text-to-text`), and the
GGUF repo ships `mmproj-F16.gguf` at **918 MB**.

**We do not load it.** Voice debate needs no image input, and 918 MB is 82% of
our entire post-LLM VRAM headroom. Loading it would cost more than STT and TTS
combined, for zero benefit. Omitting `--mmproj` leaves the vision tower unloaded.

This same file is why **Ollama cannot run Qwen3.5 GGUFs** — it does not handle
the separate projector. That constraint eliminated the most convenient runtime
and drove [ADR-0002](../02-architecture/adr/0002-llama-cpp-server-as-llm-runtime.md).

### 5.4 Launch command

```powershell
.\llama-server.exe `
  -m C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf `
  -ngl 99 `
  -c 16384 `
  -fa `
  --host 127.0.0.1 `
  --port 8080
```

| Flag | Why |
|---|---|
| `-ngl 99` | All 32 layers on GPU. Partial offload collapses throughput (NFR-R-02). |
| `-c 16384` | ~40 min of debate history at 512 MiB KV cost. |
| `-fa` | Flash attention. |
| `--host 127.0.0.1` | **Never `0.0.0.0`.** No auth on this server (NFR-S-03). |
| *(no `--mmproj`)* | Vision tower stays unloaded. |

---

## 6. Expected performance **[SOURCED — unverified on this machine]**

| | |
|---|---|
| Generation | 25–35 tok/s for a 9B Q4 fully offloaded on RTX 4060 |
| Backend overhead | ~0.75 GiB beyond model size |
| KV at Q4 vs FP16 | ~1.8 GiB saved at 16K context (for conventional models) |

**Every one of these is third-party.** None has been reproduced here, and the
whole latency design rests on the first. Benchmark BM-01 exists to close this
gap and must run before implementation begins.

**Practical implication of 30 tok/s.** A 45-second spoken response is ~150
tokens ≈ **5 seconds of generation**. Streaming is therefore not an optimisation
but a requirement: without it, the user waits 5 s of silence. With it, the first
sentence (~20 tokens, ~0.7 s) starts playing almost immediately and generation
hides behind playback.

---

## 7. Alternatives in the same family

Available in the same repo, should this model prove unsuitable:

| Variant | Size | When |
|---|---|---|
| `UD-Q3_K_XL` | 4.71 GiB | If VRAM proves tighter than modelled |
| `UD-Q5_K_XL` | 6.28 GiB | If we drop to 8K context and want quality |
| `Qwen3.5-4B` | ~2.5 GiB | Latency escape hatch — roughly 2× faster, measurably weaker |
| `Qwen3.5-2B` | ~1.3 GiB | Emergency fallback |

**The 4B is the important contingency.** If BM-01 shows the 9B below ~20 tok/s,
NFR-P-01 becomes unreachable and dropping to 4B is the fastest remedy. Its
MMLU-Pro is 79.1 vs 82.5 — a real but survivable loss for a debate partner,
where argumentative structure matters more than knowledge depth. Recorded as
the primary mitigation for [RISK-02](../06-governance/01-risk-register.md).

---

## 8. Summary — what this model buys and costs us

**Buys**

- Hybrid attention → KV cache ~3–4× smaller than a conventional 9B. Decisive.
- Thinking off by default → no latency tax.
- Strong multi-turn instruction following (MultiChallenge 54.5) → position holding.
- Apache 2.0 → no licensing friction.
- Long-context competence → references arguments from early in a session.

**Costs**

- Newer architecture → tooling risk, uncertain prefix-caching behaviour.
- Vision capability we cannot afford to use.
- Not runnable in Ollama → llama.cpp directly, more setup.
- 5.56 GiB leaves only ~1.1 GiB for everything else — the constraint that shapes
  the rest of this design.

---

## Sources

- [Qwen/Qwen3.5-9B — model card](https://huggingface.co/Qwen/Qwen3.5-9B)
- [unsloth/Qwen3.5-9B-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF)
- [Qwen3.5 — How to Run Locally — Unsloth](https://unsloth.ai/docs/models/qwen3.5)
- [Enabling or disabling reasoning — HF discussion](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/discussions/2)
- [Alibaba's Qwen3.5-9B beats GPT-OSS-120B — VentureBeat](https://venturebeat.com/technology/alibabas-small-open-source-qwen3-5-9b-beats-openais-gpt-oss-120b-and-can-run)
- [RTX 4060 token speed benchmarks — BSWEN](https://docs.bswen.com/blog/2026-03-27-rtx-4060-token-speed-benchmark-coding/)

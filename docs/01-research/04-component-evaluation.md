# Component Evaluation

| | |
|---|---|
| **Status** | Complete — evaluated 2026-08-30 |
| **Purpose** | Score candidates for each pipeline stage against our actual constraints |

---

## Evaluation criteria

Candidates are scored against constraints specific to this project, not against
general excellence. Two criteria carry unusual weight:

| Criterion | Weight | Why |
|---|---|---|
| **VRAM cost** | **Critical** | ~1.1 GiB total headroom, possibly less |
| **Offline capability** | **Blocking** | NFR-S-01. Any cloud dependency disqualifies. |
| Latency | High | NFR-P-01 |
| Quality | High | |
| Windows support | High | Primary target; many ML tools are Linux-first |
| Python 3.11 wheels | Medium | Avoids source builds on Windows |

**Disqualifying:** any cloud API. Deepgram, AssemblyAI, ElevenLabs, and Cartesia
are excellent and all are excluded by NFR-S-01 without further discussion.

---

## 1. Speech-to-Text

### Candidates

| Model | Params | WER | Speed | VRAM | Silence hallucination |
|---|---|---|---|---|---|
| **Parakeet TDT 0.6B v3** | 600M | **6.32%** | ~3,333× RT | ~0 (CPU) | **Almost never** |
| Whisper large-v3 | 1.55B | 7.44% | 68.6× RT | ~3 GB | **Frequent** |
| faster-whisper small.en | 244M | ~9% | Mid | ~0.5 GB | Frequent |
| Moonshine v2 | 245M | ≈large-v3 | Edge-optimised | ~0 (CPU) | Unknown |
| whisper.cpp base.en | 74M | ~12% | Fast | ~0 | Frequent |

Sources: [Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks),
[LocalAIMaster](https://localaimaster.com/blog/parakeet-vs-whisper),
[Modelslab](https://modelslab.com/blog/audio-generation/moonshine-vs-whisper-asr-real-time-speech-2026).

### Scoring

| | Parakeet | faster-whisper | Moonshine |
|---|---|---|---|
| Accuracy | ●●●●● | ●●●○○ | ●●●●○ |
| Speed | ●●●●● | ●●●○○ | ●●●●● |
| VRAM | ●●●●● (CPU) | ●●●○○ | ●●●●● (CPU) |
| Silence robustness | ●●●●● | ●●○○○ | ●●●○○ (unverified) |
| Windows support | ●●●●○ (ONNX) | ●●●●● | ●●●○○ |
| Streaming | ●●○○○ | ●●●●○ | ●●●●● |
| Maturity | ●●●○○ | ●●●●● | ●●○○○ |

### Decision: **Parakeet TDT 0.6B v3 via ONNX, on CPU**

The deciding factor is **not** the WER advantage. It is silence robustness.

> Whisper-family models emit text into silence — the notorious "Thank you for
> watching!" artifact, inherited from YouTube training data. In most
> applications this is a nuisance. **In ours it is corrupting**: a debate
> contains deliberate 2–3 second thinking pauses, and phantom text entering the
> argument history means the agent rebuts sentences the user never uttered.
> There is no recovery from that — the user cannot tell whether the agent
> misheard or is fabricating.

Runtime: [`onnx-asr`](https://pypi.org/project/onnx-asr/) — no PyTorch, no NeMo,
no transformers. On a Windows machine avoiding a 2.5 GB PyTorch install for a
CPU-only task, that dependency profile is worth a great deal on its own. ONNX
weights at [`istupakov/parakeet-tdt-0.6b-v3-onnx`](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx).

**Accepted limitation [SOURCED]:** Parakeet TDT is
[not designed for true streaming](https://github.com/k2-fsa/sherpa-onnx/issues/2918).
We transcribe complete utterances on VAD boundaries rather than word-by-word.
For turn-based debate this is fine. It does mean interim transcripts (FR-40's
live text) need either a second tiny model or acceptance that text appears per
turn rather than per word — see [OQ-06](../06-governance/05-open-questions.md).

**Fallback: faster-whisper small.en.** Slower and it hallucinates, but it is
the best-supported option on Windows + NVIDIA and will work when something else
does not. Interface-swappable per NFR-M-01.

ADR: [ADR-0005](../02-architecture/adr/0005-parakeet-tdt-for-stt.md).

---

## 2. Text-to-Speech

### Candidates

| Model | Params | Latency | VRAM | Quality | Cloning |
|---|---|---|---|---|---|
| **Kokoro-82M** | 82M | Faster than RT on CPU | **~0** | ●●●●○ | No |
| Piper | ~20M | Very fast on CPU | ~0 | ●●○○○ | No |
| Chatterbox | 0.5B | Moderate | ~1 GB | ●●●●○ | 10 s sample |
| XTTS v2 | ~450M | Moderate | ~2 GB | ●●●●○ | Yes, 17 langs |
| **Orpheus** | 3B | ~200 ms | **~8 GB** | ●●●●● | Zero-shot |
| Qwen3-TTS | — | 97 ms | Unknown | ●●●●● | Yes |

Sources: [LocalAIMaster](https://localaimaster.com/blog/best-local-tts-models),
[CodeSOTA](https://www.codesota.com/guides/tts-models),
[kokoro-onnx](https://pypi.org/project/kokoro-onnx/),
[Orpheus setup](https://localaimaster.com/blog/orpheus-tts-setup-guide).

### Decision: **Kokoro-82M via ONNX, on CPU**

Orpheus is the best-sounding option and would genuinely suit a debate agent —
its inline `<laugh>` and `<sigh>` tags could convey the scepticism a good
opponent expresses. It needs ~8 GB VRAM. **It is not available to us, and no
amount of cleverness changes that.** Recorded so the trade-off is explicit
rather than forgotten.

Kokoro is the clear winner within our envelope: 82M parameters, ~80 MB
quantized, faster than real-time on plain CPU, and consistently described across
sources as the best quality-per-resource option. `pip install kokoro-onnx`, no
GPU required.

**One caveat [SOURCED]:** ONNX Kokoro is marginally *slower* than PyTorch on very
short texts (RTF 0.72 vs 0.49) due to per-call overhead, catching up at medium
and longer lengths. This matters because **our sentences are short by design** —
we stream sentence-by-sentence. Mitigation: batch to clause boundaries rather
than dispatching three-word fragments. Measured in BM-03.

**Fallback: Piper.** Noticeably more robotic, even lighter. Acceptable if Kokoro
misses its RTF target.

**Deferred: Chatterbox.** Voice cloning is genuinely interesting for a debate
opponent — arguing against a familiar voice changes the experience. It costs
~1 GB VRAM and adds a misuse surface. Out of scope for v1
([Vision & Scope §5](../00-product/01-vision-and-scope.md)).

ADR: [ADR-0006](../02-architecture/adr/0006-kokoro-for-tts.md).

---

## 3. Voice Activity Detection

### Candidates

| Option | Latency | CPU | Notes |
|---|---|---|---|
| **Silero VAD** | ~1 ms/frame | Negligible | Industry standard; native in LiveKit and Pipecat |
| WebRTC VAD | <1 ms | Negligible | Older, energy-based, more false positives |
| Energy threshold | ~0 | ~0 | Trivial, unusable in real rooms |

### Decision: **Silero VAD**

Not a close call. Silero is the de-facto standard, natively supported in both
candidate frameworks, and costs effectively nothing. It classifies frames as
speech or silence in real time.

Its job here is narrow and must stay narrow: **detect speech onset for barge-in,
and detect silence for the turn detector to evaluate.** It does not decide when
a turn ends — that is the semantic layer's job. Conflating the two is the
classic error described in
[Technology Landscape §1.2](01-technology-landscape.md#12-departure-two-turn-detection-is-its-own-problem).

---

## 4. Semantic turn detection

### Candidates

| Option | Base | Runs on | Availability |
|---|---|---|---|
| **LiveKit turn-detector** | Qwen2.5-0.5B fine-tune | CPU, low latency | [HF](https://huggingface.co/livekit/turn-detector), Apache |
| Pipecat Smart Turn v2 | — | CPU | Bundled with Pipecat |
| Deepgram Flux | — | Cloud | **Disqualified** — NFR-S-01 |
| Punctuation heuristic | — | ~0 | Crude but nearly free |

### Decision: **Pipecat Smart Turn v2, with LiveKit turn-detector as fallback**

Smart Turn v2 comes with the chosen framework, removing an integration.
LiveKit's is a well-documented Qwen2.5-0.5B fine-tune "selected for strong
performance on this task while enabling low-latency CPU inference" — usable
standalone if Smart Turn disappoints.

**The heuristic fallback deserves recording**, because it is what ships if both
models prove too slow: commit the turn when the partial transcript ends in
terminal punctuation *and* silence exceeds 600 ms; otherwise extend to 1,500 ms.
Crude, but far better than a fixed timer and it costs nothing.

> **Why this component gets disproportionate attention.** For a customer-service
> agent, a mistimed turn is mildly annoying. For a debate partner it is
> character-defining: an agent that cuts you off while you are marshalling a
> thought does not read as a latency bug, it reads as a rude opponent. The
> asymmetry in NFR-A-03 / NFR-A-04 encodes this — bias toward waiting.

ADR: [ADR-0007](../02-architecture/adr/0007-two-layer-turn-detection.md).

---

## 5. LLM runtime

| Option | Qwen3.5 support | API | Verdict |
|---|---|---|---|
| **llama.cpp `llama-server`** | Yes | OpenAI-compatible | **Selected** |
| Ollama | **No** — mmproj issue | OpenAI-compatible | **Disqualified** |
| vLLM | Yes | OpenAI-compatible | Poor Windows support; targets datacentre |
| LM Studio | Yes | OpenAI-compatible | GUI-first, awkward to automate |
| llama-cpp-python | Yes | In-process | Couples LLM lifecycle to app process |

### Decision: **llama.cpp `llama-server` as a separate process**

Ollama would have been the convenient choice and is ruled out by the `mmproj`
issue. vLLM is built for datacentre serving with weak Windows support.

The interesting comparison is against `llama-cpp-python`, which would embed the
model in our process. We reject that deliberately: **a separate process means
the LLM can crash, restart, be swapped, or be replaced by a cloud endpoint for
comparison, without touching orchestration code.** It also means a model reload
does not restart the audio pipeline. The cost is one HTTP hop on localhost —
sub-millisecond, irrelevant beside a 400 ms TTFT.

ADR: [ADR-0002](../02-architecture/adr/0002-llama-cpp-server-as-llm-runtime.md).

---

## 6. Orchestration framework

| | Pipecat | LiveKit Agents | DIY asyncio |
|---|---|---|---|
| Stars (Jul 2026) | 13,416 | 11,356 | — |
| Language | Python | Python | Python |
| Turn detection | Smart Turn v2 | Qwen2.5-0.5B fine-tune | Build it |
| AEC | Built in | Via WebRTC | **None** |
| Barge-in | Built in | Built in | Build it |
| Local LLM | OpenAI-compatible service | Supported | Trivial |
| Overhead | Framework abstractions | WebRTC + rooms | None |
| Best for | Pipeline control | Transport & scale | Full control |

### Decision: **Pipecat**

LiveKit's strengths — WebRTC transport, SIP trunking, thousands of concurrent
calls, multi-participant rooms — address problems we do not have. We have one
user on one laptop and have explicitly excluded telephony and multi-user.

Pipecat's strengths land where our uncertainty is. Several component choices
here rest on third-party benchmarks; some will be wrong. A framework where
swapping TTS is a one-line change directly serves NFR-M-01.

DIY remains genuinely tempting — roughly 500 lines and no framework to fight.
It loses on one specific point: **acoustic echo cancellation**, which is hard,
which Pipecat provides, and which we would otherwise have to write or do without.

ADR: [ADR-0003](../02-architecture/adr/0003-pipecat-as-orchestration-framework.md).

---

## 7. Summary

| Stage | Choice | Placement | Confidence |
|---|---|---|---|
| VAD | Silero VAD | CPU | **High** — no real alternative |
| Turn detection | Smart Turn v2 | CPU | **Medium** — highest-uncertainty component |
| STT | Parakeet TDT 0.6B v3 (ONNX) | CPU | **Medium-high** — verify RTF in BM-03 |
| LLM | Qwen3.5-9B UD-Q4_K_XL via llama-server | **GPU** | **High** — verify tok/s in BM-01 |
| TTS | Kokoro-82M (ONNX) | CPU | **Medium-high** — verify short-text RTF |
| Orchestration | Pipecat | CPU | **Medium** — reversible |
| Transport | Local audio / browser | — | **Blocked on OQ-01** |

**Total GPU allocation: the LLM alone.** Everything else runs on 16 otherwise-idle
CPU threads. This is the central resource decision and it is documented in
[ADR-0004](../02-architecture/adr/0004-cpu-placement-for-stt-and-tts.md).

### Where we are most likely wrong

Ranked by damage if wrong:

1. **LLM throughput** — if under 20 tok/s, NFR-P-01 is unreachable. Mitigation: Qwen3.5-4B.
2. **Turn detection quality** — hardest to get right, most damaging to feel. Mitigation: push-to-talk (FR-43).
3. **CPU speech RTF under load** — benchmarks are from idle machines. Mitigation: smaller models.
4. **Prefix caching on hybrid architecture** — unverified; if broken, every turn re-prefills the whole conversation.

All four are measured before implementation. See
[Benchmark Plan](../04-quality/03-benchmark-plan.md).

# Technology Landscape — Voice Agents in 2026

| | |
|---|---|
| **Status** | Complete — research conducted 2026-08-30 |
| **Purpose** | Record how the industry builds voice agents, so our departures from that are deliberate and traceable |

---

## 1. The dominant architecture

Every mainstream framework in 2026 converges on the same shape: a **cascaded
pipeline** of speech-to-text → LLM → text-to-speech. This is described
identically by [LiveKit](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained),
[Deepgram](https://deepgram.com/learn/voice-agent-architecture-stt-llm-tts-pipeline-design),
and [AssemblyAI](https://www.assemblyai.com/blog/voice-agent-architecture).

The naive form of this — wait for the user, transcribe fully, generate fully,
synthesise fully, play — is the reference implementation in most tutorials and
**produces 2–4 seconds of response delay**. Every serious deployment departs
from it in the same two ways.

### 1.1 Departure one: stages overlap

Production pipelines stream across stage boundaries. The LLM begins processing
before transcription finalises; TTS begins synthesising before generation
completes. Perceived latency becomes *time-to-first-sentence*, not
*time-to-complete-answer*. Sources consistently report this taking pipelines
from 2–4 s to sub-1-second.

The mechanism: accumulate LLM tokens until a sentence boundary, dispatch that
sentence to TTS, continue generating. Playback of sentence *n* overlaps
generation of sentence *n+1*.

### 1.2 Departure two: turn detection is its own problem

This is the component absent from most naive designs and the one that most
determines whether an agent feels natural.

Deciding *when the user has finished* is not the same problem as transcribing
them. A silence threshold — the obvious approach — fails because humans pause
mid-thought. Set it short and you interrupt people; set it long and the agent
feels sluggish. **There is no threshold that satisfies both.**

The 2026 answer is two layers, per [LiveKit's turn detection analysis](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection):

| Layer | Signal | Latency | Answers |
|---|---|---|---|
| **VAD** (Silero) | Acoustic energy | ~1 ms | "Is sound happening?" |
| **Semantic turn detector** | Partial transcript text | ~50–150 ms | "Is this person finished?" |

VAD drives barge-in — it must be instant and needs no language understanding.
The semantic model reads the partial transcript and predicts completion. [LiveKit's
turn-detector](https://huggingface.co/livekit/turn-detector) is a fine-tune of
Qwen2.5-0.5B, chosen specifically for **low-latency CPU inference**. Pipecat
ships Smart Turn v2; Deepgram sells Flux.

That these models are ~0.5B and CPU-targeted is a useful signal: the industry
treats turn detection as cheap and always-on, not as something competing for GPU.

---

## 2. Published latency budgets

Twilio's engineering guidance, as reported across the sources above:

| Stage | Budget |
|---|---|
| STT | 350 ms |
| LLM first token | 375 ms |
| TTS first byte | 100 ms |
| **Target median mouth-to-ear** | **~1,115 ms** |

Two calibration points worth recording:

- Callers **begin noticing lag around 800 ms**.
- A 2025 observational study of nine voice-assistant users measured a **1,366 ms
  mean response delay** in shipped consumer products.

The second number is the more useful one. Shipped commercial assistants sit
above 1.3 s. Our 1,200 ms target is therefore ambitious-but-normal, not
exotic — and it is achieved by companies with datacentre GPUs and no local
constraints. See [Latency Budget](../02-architecture/07-latency-budget.md) for
how we intend to hit it anyway.

---

## 3. Speech-to-speech: considered and rejected

The alternative architecture skips text entirely — audio in, audio out.
[Qwen3-Omni](https://github.com/QwenLM/Qwen3-Omni) uses a "Thinker-Talker"
design where the Thinker produces text tokens and the Talker produces speech
conditioned on the Thinker's hidden states. Moshi maps audio to audio with
minimal text exposure.

**The theoretical appeal is real:** no cascade means no accumulated stage
latency, and paralinguistic information (tone, hesitation, sarcasm) survives
instead of being flattened into text.

**The measured reality is not.** Published measurement on the Qwen2.5-Omni
generation found the DiT-based Talker running at **~0.5× realtime — roughly 2
seconds of compute per 1 second of audio — yielding ~13 s time-to-first-audio**
even with sentence-level streaming. That is an order of magnitude outside our
budget, on hardware larger than ours.

Full rationale: [ADR-0001](../02-architecture/adr/0001-cascaded-pipeline-over-speech-to-speech.md).

> **A benefit specific to us.** Cascaded architecture produces intermediate text
> as a first-class artifact. For a debate application that is not incidental —
> it is what makes transcripts, argument tracking, and post-session review
> possible at all. A speech-to-speech model would give us none of it.

---

## 4. Orchestration frameworks

| | Pipecat | LiveKit Agents |
|---|---|---|
| GitHub stars (Jul 2026) | 13,416 | 11,356 |
| Model | Python pipeline framework | WebRTC infra + agents layer |
| Strength | Pipeline-level control; large integration library | Transport, SIP, scaling, multi-participant rooms |
| Turn detection | Smart Turn v2 | Fine-tuned Qwen2.5-0.5B end-of-utterance |
| Echo cancellation | Built in | Via WebRTC |
| Best when | You own every layer and run your own infra | Infrastructure *is* your problem |

Sources: [Evalgent](https://www.evalgent.com/blog/pipecat-vs-livekit),
[ThinnestAI](https://www.thinnest.ai/blog/open-source-voice-ai-frameworks),
[Forasoft](https://www.forasoft.com/blog/article/pipecat-vs-livekit-agents).

The consistent framing across sources: **LiveKit solves transport and scale;
Pipecat solves the pipeline.** LiveKit's differentiator is its room model —
agents join as participants, making group calls and video native. Its other
strength is SIP trunking for telephony.

We have one user, on one laptop, with no phone. LiveKit's entire advantage is
in a dimension we do not have. Pipecat's advantage — swapping a TTS engine as a
one-line change — is exactly the dimension where our uncertainty lives.

Decision: [ADR-0003](../02-architecture/adr/0003-pipecat-as-orchestration-framework.md).

---

## 5. Local LLM serving

[llama.cpp's `llama-server`](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
exposes an OpenAI-compatible API at `/v1/chat/completions`, wire-compatible
enough that any client accepting a `base_url` — the OpenAI SDK, LangChain,
LlamaIndex, LiteLLM — works unmodified. Streaming is supported.

This matters more than it first appears: it means **the LLM is a swappable
network service behind a standard interface**, not a library linked into our
process. We can restart it, replace it, run it on another machine, or point at
a cloud endpoint for A/B comparison, without touching orchestration code.

**Qwen3.5 support status [VERIFIED as of Aug 2026].** The llama.cpp README leads
with `llama serve -hf ggml-org/Qwen3.5-0.8B-GGUF`, and PR #19493 (merged
2026-04-19) added speculative decoding for the Qwen3.5/3.6 line. Support for the
hybrid DeltaNet graph is present in current builds.

> **Caveat [SOURCED].** As of ~May 2026 this support was described as
> bleeding-edge HEAD rather than stable-release. Use a recent build, verify
> before committing. Tracked as [RISK-01](../06-governance/01-risk-register.md).

**Ollama is not viable here.** Per the [Unsloth guide](https://unsloth.ai/docs/models/qwen3.5),
Qwen3.5 GGUFs do not load in Ollama because of the separate `mmproj` vision
file. This removes the most convenient option and is why we target llama.cpp
directly. [ADR-0002](../02-architecture/adr/0002-llama-cpp-server-as-llm-runtime.md).

---

## 6. Speech-to-text landscape

| Model | WER | Speed | Notes |
|---|---|---|---|
| **Parakeet TDT 0.6B v3** | 6.32% | ~3,333× RT | Almost never hallucinates in silence; 25 European languages |
| Whisper large-v3 | 7.44% | 68.6× RT | 99 languages; hallucinates in silence |
| Moonshine v2 | ~large-v3 parity | Purpose-built for edge | 245M params, ~6× smaller than large-v3 |
| faster-whisper | (Whisper) | Mid | Best-supported on Windows + NVIDIA |

Sources: [Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks),
[LocalAIMaster](https://localaimaster.com/blog/parakeet-vs-whisper),
[Modelslab](https://modelslab.com/blog/audio-generation/moonshine-vs-whisper-asr-real-time-speech-2026).

Parakeet is **better and roughly 49× faster** than Whisper large-v3 on the
headline numbers, which is unusual enough to warrant scepticism — but it is
reported consistently across independent sources.

**The property that decides it for us is not WER.** It is that Parakeet almost
never emits text during silence. Whisper's tendency to hallucinate "Thank you
for watching!" into dead air is a documented, notorious failure. In a debate
application with deliberate thinking pauses, phantom text enters the argument
history and the agent responds to things the user never said.

**One real caveat [SOURCED]:** Parakeet TDT is [not designed for true
streaming](https://github.com/k2-fsa/sherpa-onnx/issues/2918). A pseudo-streaming
approach works but is inefficient. For turn-based debate — where we transcribe
a committed utterance rather than needing live word-by-word output — this is
acceptable. It would not be for a barge-in-heavy customer service agent.

Decision: [ADR-0005](../02-architecture/adr/0005-parakeet-tdt-for-stt.md).

---

## 7. Text-to-speech landscape

| Model | Params | Latency | VRAM | Verdict |
|---|---|---|---|---|
| **Kokoro-82M** | 82M | Faster than RT on CPU | ~0 (CPU) | Viable |
| Piper | Tiny | Fast on CPU | ~0 | Viable, more robotic |
| Chatterbox | 0.5B | — | Moderate | Voice cloning from 10 s |
| Orpheus | 3B | ~200 ms | **~8 GB** | Impossible here |
| Qwen3-TTS | — | 97 ms streaming | — | Newest; streaming + cloning |

Sources: [LocalAIMaster](https://localaimaster.com/blog/best-local-tts-models),
[CodeSOTA](https://www.codesota.com/guides/tts-models),
[kokoro-onnx](https://pypi.org/project/kokoro-onnx/).

Orpheus is reported as the best-sounding option, with inline `<laugh>` / `<sigh>`
emotion tags that would suit a debate agent well. It requires roughly our entire
GPU. It is not available to us and this is simply a constraint we accept.

Kokoro at 82M parameters runs **faster than real-time on a plain CPU**, with
~80 MB quantized. Consensus across sources is that it is the best
quality-per-resource option available.

Decision: [ADR-0006](../02-architecture/adr/0006-kokoro-for-tts.md).

---

## 8. Barge-in and echo cancellation

Reported production figures: barge-in detection P50 ~200 ms, agent-stop P50
~300 ms are considered acceptable. The stop sequence is consistent across
sources: (1) halt TTS immediately, (2) clear audio buffers, (3) mark context
interrupted for the LLM, (4) temporarily raise VAD sensitivity.

**Echo cancellation is the underestimated part.** Per
[Coval](https://www.coval.ai/blog/voice-ai-echo-cancellation/) and
[Hamming](https://hamming.ai/resources/debug-webrtc-voice-agents-troubleshooting-guide):
without AEC, the agent's own output re-enters the microphone, trips VAD, and the
agent interrupts itself endlessly. AEC is hardest during *double-talk* — exactly
the barge-in moment — where false suppression of user speech is the common
failure.

Google's WebRTC AEC module is usable server-side outside a browser; Pipecat
includes echo cancellation.

> **The shortcut that matters for a single-user local product:** headphones
> eliminate the speaker→microphone path entirely, so no AEC is required. This is
> a legitimate engineering answer, not a dodge, and it removes the hardest
> signal-processing problem in the system.
> [ADR-0008](../02-architecture/adr/0008-headphones-first-audio-transport.md).

---

## 9. What this landscape means for us

| Industry practice | Our position |
|---|---|
| Cascaded pipeline | **Adopt** — and it gives us transcripts as a bonus |
| Streaming across stages | **Adopt** — non-negotiable for latency |
| Two-layer turn detection | **Adopt** — disproportionately important for debate |
| Cloud STT/TTS APIs | **Reject** — offline is a product requirement |
| Speech-to-speech | **Reject** — ~13 s TTFA, and needs VRAM we lack |
| WebRTC transport | **Defer** — solves multi-party problems we do not have |
| GPU-hosted speech models | **Reject** — the LLM needs the whole GPU |
| Sub-800 ms target | **Relax to 1,200 ms** — debate tolerates a beat of thought |

The last three rows are where we depart from mainstream practice, and all three
trace to the same cause: **8 GB of VRAM and a single local user**. Published
guidance assumes neither.

---

## Sources

- [Voice Agent Architecture: STT, LLM, and TTS Pipelines Explained — LiveKit](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained)
- [Voice Agent Architecture: STT, LLM, and TTS Pipeline Guide — Deepgram](https://deepgram.com/learn/voice-agent-architecture-stt-llm-tts-pipeline-design)
- [Voice Agent Architecture: Build STT-LLM-TTS Pipeline — AssemblyAI](https://www.assemblyai.com/blog/voice-agent-architecture)
- [Turn Detection for Voice Agents — LiveKit](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection)
- [livekit/turn-detector — Hugging Face](https://huggingface.co/livekit/turn-detector)
- [Pipecat vs LiveKit — Evalgent](https://www.evalgent.com/blog/pipecat-vs-livekit)
- [Best Open-Source Voice AI Frameworks — ThinnestAI](https://www.thinnest.ai/blog/open-source-voice-ai-frameworks)
- [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [Best open source STT model in 2026 — Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Parakeet vs Whisper — LocalAIMaster](https://localaimaster.com/blog/parakeet-vs-whisper)
- [Best Local TTS Models 2026 — LocalAIMaster](https://localaimaster.com/blog/best-local-tts-models)
- [Voice AI Echo Cancellation — Coval](https://www.coval.ai/blog/voice-ai-echo-cancellation/)
- [Qwen3-Omni — GitHub](https://github.com/QwenLM/Qwen3-Omni)
- [Qwen3.5 — How to Run Locally — Unsloth](https://unsloth.ai/docs/models/qwen3.5)

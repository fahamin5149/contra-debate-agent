# Troubleshooting

| | |
|---|---|
| **Status** | Draft — extend as real failures occur |
| **Last updated** | 2026-08-30 |

Organised by **symptom**, because that is what you have when something breaks.

---

## Audio

### The agent constantly interrupts itself

**The most likely first-run problem with speakers.** Echo cancellation is not
suppressing enough of the agent's own output, so its voice reaches the
microphone, triggers VAD, and fires barge-in repeatedly.

Try in this order — cheapest first:

| Fix | Why |
|---|---|
| **Lower the output volume** | AEC degrades as echo amplitude rises. Often sufficient on its own. |
| **Enrol devices as Windows *Communications* devices** | Adds OS-level AEC beneath the browser's |
| **Check the browser is actually doing AEC** | Console: `getUserMedia` constraints must include `echoCancellation: true` |
| **Move the microphone away from the speakers** | Physical separation beats every software setting |
| **Raise `vad.threshold`** (0.5 → 0.65) | Blunt instrument; costs barge-in sensitivity |
| Use headphones | Eliminates the problem entirely, if you are willing |

**Do not "fix" this by muting the microphone during playback.** That eliminates
barge-in (FR-12), which is P0.

[ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md) ·
[RISK-12](../06-governance/01-risk-register.md)

### The agent cannot be interrupted at all

**The opposite failure, and the more insidious one** — the system looks like it
is working.

| | |
|---|---|
| **Cause** | Echo cancellation is over-suppressing. During double-talk it is removing your speech along with the agent's echo. |
| **Check** | Look at the transcript: is your interrupting speech missing or garbled? |

| Fix | Why |
|---|---|
| **External microphone, away from the speakers** | Better signal separation gives AEC an easier job |
| Lower output volume | Less echo to cancel means less aggressive suppression |
| Disable `noiseSuppression` / `autoGainControl`, keep `echoCancellation` | AGC can duck your voice under the agent's |
| Fall back to push-to-talk (`--ptt`) | Guaranteed to work; loses hands-free |

> This is [NFR-A-06](../00-product/05-non-functional-requirements.md) failing.
> Barge-in is by definition double-talk — the hardest case for any echo
> canceller. If it cannot be made to work on your hardware, push-to-talk is the
> honest fallback rather than shipping an agent that only appears interruptible.

### No audio output, but the transcript updates

Audio is played **by the browser**, so check there first:

1. Is the browser tab muted? (Right-click the tab → Unmute site.)
2. Is the correct output device selected in the page's device picker?
3. Windows may have routed audio to a disconnected HDMI display.
4. Windows volume mixer — the *browser* may be muted independently.
5. Browser console: are inbound WebRTC audio packets arriving?

> The spoken startup greeting exists precisely to catch this before you argue
> into the void for a minute. If you did not hear it, stop and fix routing.

### Speech is not detected at all

1. **Did you grant the browser microphone permission?** Check the padlock icon in
   the address bar.
2. Windows → Settings → Privacy → Microphone → allow desktop apps
3. Check the input device in the page's device picker
4. Check any physical mute switch
5. Lower `vad.threshold` (default 0.5) if your microphone is quiet

### Audio stutters or glitches during playback

| Cause | Fix |
|---|---|
| Output buffer too small | Raise `audio.output_buffer_ms` (100 → 150). Costs barge-in speed (NFR-P-03). |
| TTS not keeping up | Check RTF; consider Piper |
| CPU contention | Lower `stt.num_threads` |
| **GIL contention** | Look for `audio_frames_dropped > 0` in the metrics — this indicates a serious problem, see [BM-03](../04-quality/03-benchmark-plan.md) |

---

## The model

### `llama-server` won't load the model

```
error: unknown model architecture 'qwen3_5'
```

**Cause:** llama.cpp is too old. Qwen3.5's hybrid Gated DeltaNet architecture
requires a recent build.

**Fix:** download a current release from
[llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases).

### Only some layers offloaded

```
llm_load_tensors: offloaded 24/33 layers to GPU
```

**This is a serious problem, not a minor inefficiency.** Partial offload
collapses throughput — every token crosses PCIe for CPU-resident layers. Expect
single-digit tokens/sec.

| Fix | Effect |
|---|---|
| Close other GPU applications | Browsers with hardware acceleration take hundreds of MiB |
| Reduce `-c 16384` → `-c 8192` | Frees ~250 MiB of KV cache |
| Force the display to the Intel iGPU | Windows → Display → Graphics settings; frees up to 700 MiB |
| Verify no `--mmproj` | The vision projector costs 918 MB |

[Resource Budget](../02-architecture/08-resource-budget.md).

### Output is gibberish

**Cause:** KV cache quantization on the hybrid architecture.

**Fix:** `--cache-type-k bf16 --cache-type-v bf16`

This is documented vendor guidance for Qwen3.5. If you did not enable KV
quantization, suspect a corrupted model file instead — verify the size is exactly
**5,966,095,584** bytes.

### Responses are very slow (>5 s to first audio)

Check in order:

1. **Partial offload?** — see above. Most likely cause.
2. **Prefix cache missing?** Look at `prefix_cache_hit` in the turn metrics. If
   consistently false, see [BM-02](../04-quality/03-benchmark-plan.md) —
   [OQ-03](../06-governance/05-open-questions.md) is unresolved.
3. **Thermal throttling?** Compare `tokens_per_sec` early vs late in the session.
4. **On battery?** Battery mode caps GPU clocks hard. Use mains power.
5. **Context too large?** Prefill cost grows with conversation length.

### `Cannot reach the model server`

```powershell
curl http://127.0.0.1:8080/health
Get-Process llama-server
netstat -ano | Select-String ":8080"
```

If the port is occupied by something else, change `llm.base_url` and the
`--port` flag together.

---

## Conversation behaviour

### It cuts me off mid-sentence

**Cause:** turn detection is committing too early.

| Fix | Trade-off |
|---|---|
| Raise `vad.silence_confirm_ms` (250 → 350) | +100 ms latency every turn |
| Raise `turn_detection.max_wait_ms` (1500 → 2000) | Slower after genuine ends |
| Switch to push-to-talk: `--ptt` | Loses hands-free operation |

> This is the failure the whole two-layer design exists to prevent
> ([ADR-0007](../02-architecture/adr/0007-two-layer-turn-detection.md)), and it
> is worth reporting rather than only working around — persistent false cuts mean
> the semantic detector is underperforming on your speech patterns, which is
> information the design needs.

### It waits too long after I finish

The opposite failure. Lower `vad.silence_confirm_ms` and
`turn_detection.max_wait_ms`.

**Prefer erring toward waiting.** Being interrupted mid-thought is considerably
more disruptive than a slightly slow reply — which is why NFR-A-03 (≤5% false
cuts) is deliberately tighter than NFR-A-04 (≤10% false holds).

### It agrees with me too easily

**The most important failure in this document**, because everything technical is
working and the product is worthless.

| Check | Action |
|---|---|
| Which prompt version is active? | `prompts/ACTIVE.yaml` |
| Does it pass probe P-01? | [Evaluation Framework §4](../04-quality/02-evaluation-framework.md) |
| Is `presence_penalty` at 1.5? | Lower values encourage repetition and drift |
| Is intensity set to `socratic`? | That mode questions rather than asserts — may read as agreement |

Root cause is usually prompt-level. Every instruction-tuned model is trained
toward agreeableness, and the persona asks it to resist that for twenty
consecutive turns. Expect this to need iteration
([Prompt Spec §7](../03-engineering/05-prompt-engineering-spec.md)).

### It repeats the same arguments

1. Verify `presence_penalty: 1.5` is actually being sent — check the request log
2. Check whether context compaction dropped earlier turns
3. Try a higher `temperature` (0.7 → 0.85)

### It invents statistics

**Treat this as a release blocker, not an annoyance.**

1. Run probe P-04 against the active prompt version
2. If it fails, the version must not be active — revert `ACTIVE.yaml`
3. Confirm the RULES section prohibiting fabrication is intact

A confidently invented number is worse than no answer, because it is undetectable
by the user ([Responsible AI](../06-governance/04-responsible-ai.md)).

### It references things it never said

**Cause:** the FR-13 spoken-history truncation is broken. After a barge-in the
system is storing generated text rather than *spoken* text.

**This is a code bug, not a configuration issue.** Check invariant I-3 and the
`ConversationState.truncate_to_spoken` tests
([Test Strategy §3](../04-quality/01-test-strategy.md)).

Symptom appears many turns after the cause, which is what makes it hard.

---

## Installation

### `DLL load failed while importing onnxruntime_pybind11_state`

Missing Visual C++ Redistributable.

```powershell
winget install Microsoft.VCRedist.2015+.x64
```

### pip is compiling packages from source

Wrong Python version. Use 3.11:

```powershell
uv venv --python 3.11
```

3.12 and 3.13 lack wheels for several dependencies; source builds on Windows need
the MSVC toolchain and often fail.

### `nvidia-smi` not found

NVIDIA driver not installed or not on PATH. Try
`C:\Windows\System32\nvidia-smi.exe`.

### Windows reports 4 GB VRAM

It is wrong. `Win32_VideoController.AdapterRAM` is a 32-bit field and unreliable
on modern GPUs. Trust `nvidia-smi`.

---

## Data

### Transcript missing after a crash

Committed turns are written synchronously (NFR-REL-03); at most the in-flight
turn is lost.

```sql
SELECT id, topic, started_at FROM sessions WHERE ended_at IS NULL;
```

Rows with `ended_at IS NULL` are crashed sessions. Their turns are present.

### Database is locked

Another process holds it — usually a SQLite browser left open. Close it. WAL mode
allows concurrent readers, but some tools open exclusively.

---

## Diagnostics to gather

Before investigating anything unfamiliar:

```powershell
python -m contra --version
C:\llama.cpp\llama-server.exe --version
nvidia-smi
python --version
Get-Content data\contra.log -Tail 100
sqlite3 data\contra.db "SELECT * FROM turn_metrics ORDER BY turn_id DESC LIMIT 10;"
```

The last query is usually the most informative — the per-stage timings say
immediately *which* stage is at fault, which turns eight candidate causes into
one.

> When you diagnose a failure not listed here, add it. This document should grow
> from real experience; a troubleshooting guide written entirely in advance
> covers the problems you imagined rather than the ones you get.

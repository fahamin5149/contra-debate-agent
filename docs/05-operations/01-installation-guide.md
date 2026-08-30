# Installation Guide

| | |
|---|---|
| **Status** | Draft — **untested**; verify by following it literally on a clean machine |
| **Last updated** | 2026-08-30 |
| **Target** | Windows 11, NVIDIA GPU ≥ 8 GB |

Bare machine to first debate. Budget ~15 minutes of work plus ~20 minutes of
downloads.

---

## Step 0 — Check your hardware

```powershell
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
```

Expect ≥ **8,000 MiB** and driver ≥ **550**.

> **Do not use Windows Device Manager or `Get-CimInstance Win32_VideoController`
> to check VRAM.** WMI reports an RTX 4060 Laptop as having 4 GB — the field is
> 32-bit and unreliable on modern cards. `nvidia-smi` is authoritative.

| Requirement | Minimum |
|---|---|
| GPU | NVIDIA, 8 GB VRAM, compute ≥ 8.9 |
| RAM | 16 GB |
| Disk | 15 GB free |
| OS | Windows 11 |
| Browser | Chrome or Edge — **required** |
| Audio | Microphone + speakers (or headphones) |

> **The browser is a required component, not an optional viewer.** Audio enters
> and leaves through it, because the browser's echo canceller is what stops the
> agent hearing itself through your speakers. It can only cancel audio it renders
> itself, so agent speech is played by the page rather than by Python.
> [ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md).
>
> **Speakers work.** Headphones also work and make echo cancellation trivially
> easy, but they are not required.

---

## Step 1 — Python 3.11

```powershell
python --version
```

If this is not 3.11.x, install it. **3.12 and 3.13 are not supported**: ML wheels
lag Python releases, and on Windows a missing wheel means compiling from source,
which needs the MSVC build tools and frequently fails.

```powershell
winget install Python.Python.3.11
```

Multiple Python versions can coexist; `uv` selects the right one.

---

## Step 2 — Visual C++ Redistributable

Required by ONNX Runtime. Often already present.

```powershell
winget install Microsoft.VCRedist.2015+.x64
```

Skipping this produces `DLL load failed while importing onnxruntime_pybind11_state`
later — an error message that gives no hint of its cause.

---

## Step 3 — Repository and environment

```powershell
git clone <repo> contra-debate-agent
cd contra-debate-agent

pip install uv
uv venv --python 3.11
.\.venv\Scripts\Activate.ps1
uv sync
```

`uv sync` installs from the committed lockfile, so you get exactly the tested
dependency set.

---

## Step 4 — llama.cpp

Download the Windows CUDA build from
[llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases):
`llama-b####-bin-win-cuda-x64.zip`.

> **Use a recent build.** Qwen3.5 uses a hybrid Gated DeltaNet architecture that
> older releases cannot load. A 2025 build will fail with an unrecognised
> architecture error.

```powershell
mkdir C:\llama.cpp
# extract the zip contents there
C:\llama.cpp\llama-server.exe --version
```

---

## Step 5 — The language model

If you already have `Qwen3.5-9B-UD-Q4_K_XL.gguf`, verify it:

```powershell
(Get-Item C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf).Length
```

Must be exactly **5966095584** bytes.

> Check the size, not just that the file exists. A truncated GGUF often **loads
> successfully and produces subtly degraded output** rather than failing — a
> genuinely unpleasant thing to debug later.

Otherwise download `Qwen3.5-9B-UD-Q4_K_XL.gguf` from
[unsloth/Qwen3.5-9B-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF).

**Do not download `mmproj-*.gguf`.** It is the vision projector — 918 MB you will
never use and cannot afford in VRAM.

---

## Step 6 — Speech models

```powershell
python scripts/fetch_models.py
```

| Model | Size |
|---|---|
| Parakeet TDT 0.6B v3 (ONNX) | ~650 MB |
| Kokoro-82M (ONNX) | ~310 MB |
| Silero VAD | ~2 MB |
| Smart Turn v2 | ~500 MB |

**This is the last step that needs the internet.** Everything afterwards runs
fully offline.

---

## Step 7 — Verify the model loads

Before touching the application, confirm the LLM works alone:

```powershell
C:\llama.cpp\llama-server.exe `
  -m C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf `
  -ngl 99 -c 16384 -fa --host 127.0.0.1 --port 8080
```

**In the output, confirm:**

| Look for | Meaning |
|---|---|
| `offloaded 33/33 layers to GPU` | **All layers on GPU.** Fewer means catastrophically slow. |
| No mention of `mmproj` | Vision tower not loaded |
| `HTTP server listening 127.0.0.1:8080` | Loopback only |

Then in a second terminal:

```powershell
curl http://127.0.0.1:8080/health
```

> **If this step fails, stop and fix it.** Nothing downstream can work, and
> diagnosing it from inside a running audio pipeline is far harder.

Leave this running.

---

## Step 8 — Configure audio

Audio devices are selected **in the browser**, not in the config file — the page
uses the standard permission and device-picker UI.

```powershell
cp config/default.yaml config/user.yaml
```

On first launch the browser will ask for microphone permission. Grant it, then
pick your input and output devices from the page's device selector.

### Two settings worth applying for speaker use

**1. Enrol your devices as Windows *Communications* devices.**
Sound settings → your microphone and speakers → set as Default Communications
Device. This enables Windows' own echo cancellation as a second layer beneath the
browser's.

**2. Keep output volume moderate.**
Echo cancellation degrades as echo amplitude rises. Comfortable listening volume
is fine; maximum is not.

> **If you have an external microphone, use it, and place it away from the
> speakers.** Physical separation is the single largest improvement to echo
> cancellation — larger than any software setting. Laptop speakers and a built-in
> microphone array sitting centimetres apart is the hardest case
> ([RISK-12](../06-governance/01-risk-register.md)).

---

## Step 9 — Benchmarks (recommended)

```powershell
uv run python benchmarks/bm01_llm_throughput.py
uv run python benchmarks/bm04_vram_profile.py
```

BM-01 confirms ≥ 25 tok/s; BM-04 confirms VRAM headroom. If BM-01 reports below
18 tok/s, expect sluggish responses and see
[Benchmark Plan](../04-quality/03-benchmark-plan.md) for the remedy (switching to
Qwen3.5-4B).

---

## Step 10 — First run

```powershell
.\scripts\start.ps1
```

This starts `llama-server` (if not already running), waits for health, then
starts the orchestrator.

Expected:

```
✓ GPU: RTX 4060 Laptop, 8188 MiB
✓ Model: Qwen3.5-9B-UD-Q4_K_XL.gguf (5.56 GiB)
✓ Audio in:  Headset Microphone (Jabra Evolve 65)
✓ Audio out: Headset Earphone (Jabra Evolve 65)
✓ LLM server healthy on 127.0.0.1:8080
✓ UI at http://127.0.0.1:8000

Ready. State: IDLE
```

**You should hear a short spoken greeting.** That is deliberate — it is the only
way to discover that audio is routed to a disconnected monitor *before* you argue
into the void for a minute.

If you see the text but hear nothing, output routing is wrong. Fix it now.

---

## Step 11 — First debate

Say something like:

> "I want to argue that remote work is better for productivity."

The agent will confirm the topic and which side each of you holds, then invite
you to begin.

**Useful things to know:**

| | |
|---|---|
| Interrupt it | Just start talking — it stops |
| End the session | "Let's stop there" |
| Pause to think | Fine — it waits for a complete thought, not just silence |
| It won't budge | By design. Only an argument moves it, not repetition or frustration. |

---

## Verifying the offline guarantee

Worth doing once, so the privacy claim is something you have checked rather than
been told:

```powershell
Disable-NetAdapter -Name "Wi-Fi" -Confirm:$false
.\scripts\start.ps1
# run a full debate
Enable-NetAdapter -Name "Wi-Fi" -Confirm:$false
```

Everything should work identically. Nothing in this system needs the network
after installation.

---

## Uninstalling

```powershell
Remove-Item -Recurse .\contra-debate-agent
Remove-Item -Recurse C:\llama.cpp
Remove-Item C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf
```

Your debate transcripts live in `contra-debate-agent\data\` and are deleted with
the repository. To keep them, copy that directory first (NFR-S-06).

---

## If something went wrong

[Troubleshooting](03-troubleshooting.md) — symptom, cause, fix.

The most common first-run problems:

| Symptom | Cause |
|---|---|
| Agent interrupts itself constantly | Echo cancellation not working — lower volume, enrol as Communications device, or use an external mic |
| Agent cannot be interrupted | Echo cancellation over-suppressing your speech — see [Troubleshooting](03-troubleshooting.md) |
| Very slow responses | Partial GPU offload — check step 7 |
| `DLL load failed` | Missing VC++ redistributable — step 2 |
| pip compiling from source | Wrong Python version — step 1 |
| Model won't load | llama.cpp too old — step 4 |

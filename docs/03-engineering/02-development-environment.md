# Development Environment

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |
| **Target** | Windows 11 + NVIDIA (primary) |

---

## 1. Prerequisites

Status on the current development machine **[VERIFIED 2026-08-30]**:

| Tool | Required | Status | Notes |
|---|---|---|---|
| **Python** | **3.11.x** | ⚠️ **3.13 installed** | Must install 3.11 — see §2 |
| `uv` | latest | ❌ **missing** | `pip install uv` |
| Git | any | ✅ present | |
| NVIDIA driver | ≥ 550 | ✅ 610.47 | |
| CUDA runtime | 12.x | via llama.cpp binary | No toolkit needed |
| FFmpeg | any | ✅ `C:\ffmpeg\bin` | Some audio libs want it on PATH |
| Node.js | ≥ 20 | ✅ present | UI only |
| Visual C++ Redist | 2015-2022 | verify | Required by ONNX Runtime |

Docker is installed but **not used** — GPU passthrough on Windows adds friction
for zero benefit in a single-machine local app.

---

## 2. Python 3.11 — why, and why it matters

**[VERIFIED]** the machine has Python 3.13. **We pin to 3.11.**

> ML wheels lag Python releases, often by a year. On Windows a missing wheel is
> not a minor inconvenience — pip falls back to building from source, which needs
> the MSVC build tools and routinely fails on packages with C extensions.
>
> `onnxruntime`, `silero-vad`, `sounddevice`, and Pipecat's transitive
> dependencies are all plausible candidates. 3.11 has the broadest coverage of
> any supported version.

This is [RISK-04](../06-governance/01-risk-register.md); the pin is its
mitigation. Cost of pinning: zero. Cost of not pinning: potentially days inside a
Windows build environment.

```powershell
winget install Python.Python.3.11
# or download from python.org — do NOT add to PATH if 3.13 must stay default
```

`uv` handles multiple interpreters cleanly:

```powershell
uv python install 3.11
uv venv --python 3.11
```

---

## 3. Setup

### 3.1 Clone and environment

```powershell
git clone <repo> contra-debate-agent
cd contra-debate-agent

pip install uv
uv venv --python 3.11
.\.venv\Scripts\Activate.ps1
uv sync                 # installs from uv.lock
```

`uv sync` installs from the **committed lockfile**, so every machine gets byte-
identical dependencies. This matters more than usual here: latency measurements
are only comparable across runs if the stack is identical, and a silently
upgraded `onnxruntime` would invalidate BM-03.

### 3.2 llama.cpp

Download prebuilt Windows CUDA binaries from
[llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases).

> **Use a recent build.** Qwen3.5's hybrid Gated DeltaNet graph is newer than
> most releases. **[SOURCED]** as of ~May 2026 support was bleeding-edge HEAD;
> by August 2026 it is first-class. A 2025 release will not load this model.
> [RISK-01](../06-governance/01-risk-register.md).

```powershell
mkdir C:\llama.cpp
# extract llama-b####-bin-win-cuda-x64.zip there
C:\llama.cpp\llama-server.exe --version
```

### 3.3 Verify the LLM before anything else

```powershell
C:\llama.cpp\llama-server.exe `
  -m C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf `
  -ngl 99 -c 16384 -fa --host 127.0.0.1 --port 8080
```

Watch for:
- `llm_load_tensors: offloaded 33/33 layers to GPU` — **all layers.** Anything
  less means partial offload and collapsed throughput
  ([Resource Budget §6](../02-architecture/08-resource-budget.md)).
- No `mmproj` in the load log — the vision tower must stay unloaded.

Then:
```powershell
curl http://127.0.0.1:8080/health
```

**If this step fails, stop.** Nothing downstream can work, and debugging it
inside a running pipeline is far harder than debugging it here.

### 3.4 Speech models

```powershell
python scripts/fetch_models.py
```

Fetches to `models/`:

| Model | Source | Size |
|---|---|---|
| Parakeet TDT 0.6B v3 ONNX | `istupakov/parakeet-tdt-0.6b-v3-onnx` | ~650 MB |
| Kokoro-82M ONNX | `onnx-community/Kokoro-82M-v1.0-ONNX` | ~310 MB |
| Silero VAD | bundled | ~2 MB |
| Smart Turn v2 | via Pipecat | ~500 MB |

**This is the only step requiring network access.** Everything afterwards runs
offline (NFR-S-01), and US-501 verifies that by running with the adapter
disabled.

### 3.5 Configuration

```powershell
cp config/default.yaml config/user.yaml
```

Edit `user.yaml` for machine-specific values — audio device names above all.
`user.yaml` is gitignored.

---

## 4. Running

```powershell
.\scripts\start.ps1          # supervised (FR-51) — normal use
python -m contra             # orchestrator only, llama-server assumed running
python -m contra --ptt       # push-to-talk (FR-43)
python -m contra --debug     # verbose per-stage timings
```

During development, running `llama-server` in its own terminal is preferable:
its 20–40 s load time is paid once, and the orchestrator can restart freely
against it.

---

## 5. Testing

```powershell
uv run pytest                          # all
uv run pytest tests/unit               # fast, no models
uv run pytest -m "not slow"            # skip model-loading tests
uv run pytest --cov=contra             # coverage
```

Unit tests use fakes for every stage and require **no models and no GPU** — they
must run in seconds. Integration tests load real models and are marked `slow`.

See [Test Strategy](../04-quality/01-test-strategy.md).

---

## 6. Quality gates

```powershell
uv run ruff check .          # lint, incl. banned-import boundaries
uv run ruff format .         # format
uv run mypy src/contra       # types — strict on debate/
```

All three must pass before commit
([Definition of Done](../04-quality/05-definition-of-done.md)).

The `ruff` run is doing more than style work here: it enforces the architectural
import boundaries from
[Repository Structure §2.1](01-repository-structure.md#21-debate-imports-no-io-libraries).

---

## 7. Benchmarks — run these first

```powershell
uv run python benchmarks/bm01_llm_throughput.py
uv run python benchmarks/bm02_prefix_cache.py
uv run python benchmarks/bm03_cpu_speech_rtf.py
uv run python benchmarks/bm04_vram_profile.py
```

> **These precede application code.** The design rests on published numbers from
> other people's machines. If BM-01 returns 15 tok/s, NFR-P-01 is unreachable and
> the right response is to change the design — not to discover it during
> integration.
> [Benchmark Plan](../04-quality/03-benchmark-plan.md).

Results write to `benchmarks/results/` and are **committed**.

---

## 8. Common setup problems

| Symptom | Cause | Fix |
|---|---|---|
| `offloaded 20/33 layers` | Insufficient VRAM | Close GPU apps; lower `-c`; check BM-04 |
| Gibberish output | KV quantization on hybrid arch | `--cache-type-k bf16 --cache-type-v bf16` |
| `DLL load failed` importing onnxruntime | Missing VC++ redistributable | Install VC++ 2015-2022 |
| `pip` compiling from source | Python 3.13 | Use 3.11 |
| No audio devices listed | Windows privacy settings | Settings → Privacy → Microphone |
| Model fails to load | Old llama.cpp | Update to a recent build |
| Agent interrupts itself | Speaker output → mic | **Use headphones** ([ADR-0008](../02-architecture/adr/0008-headphones-first-audio-transport.md)) |

More in [Troubleshooting](../05-operations/03-troubleshooting.md).

---

## 9. Editor

VS Code, with:

| Extension | For |
|---|---|
| Python + Pylance | Types, completion |
| Ruff | Lint and format on save |
| Even Better TOML | `pyproject.toml` |
| SQLite Viewer | Inspecting `data/contra.db` |
| Markdown Preview Mermaid | The diagrams in this tree |

```jsonc
// .vscode/settings.json
{
  "python.defaultInterpreterPath": ".venv/Scripts/python.exe",
  "python.testing.pytestEnabled": true,
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "charliermarsh.ruff",
  "[python]": { "editor.codeActionsOnSave": { "source.organizeImports.ruff": "explicit" } }
}
```

---

## 10. Hardware notes for development

| Concern | Advice |
|---|---|
| **Mains power** | Battery mode caps GPU clocks hard; benchmarks on battery are meaningless |
| **Thermals** | Sustained load throttles a laptop GPU; watch for tok/s drift across a long session |
| **Fan noise** | Reaches the microphone and raises WER. A headset boom mic helps materially. |
| **Display GPU** | Verify the Intel iGPU drives the desktop (BM-04) — the 4060 should show ~0 MiB idle |

The fan-noise point is not incidental. A laptop under sustained GPU load is
audible, the microphone is centimetres away, and this is a voice product. It is a
genuine reason to prefer a headset over the built-in array microphone.

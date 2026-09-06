# Contra

A fully local, offline voice agent that debates you.

You state a position out loud. It takes the other side and argues it properly —
with evidence, warrants, and rebuttals — at conversational speed. It remembers
what you claimed twenty minutes ago and will hold you to it. Nothing leaves the
machine.

> **Working name.** "Contra" (from *pro et contra*) is a placeholder.

---

## Status: design phase

**No code has been written yet.** This repository currently contains the design
record that precedes it.

**→ [Start with the documentation index](docs/README.md)**

---

## Start the stack

Contra uses two processes. Start the model server in one PowerShell terminal:

```powershell
llama serve `
  -m "C:\local-models\Qwen3.5-9B-UD-Q4_K_XL.gguf" `
  -dev Vulkan1 -ngl 99 -c 16384 -fa on `
  --host 127.0.0.1 --port 8080
```

Wait for `listening on http://127.0.0.1:8080`. Then, in a second terminal with
the virtual environment activated, start Contra:

```powershell
python -m contra
```

Open <http://127.0.0.1:8000>. Stop each process with `Ctrl+C` in its terminal.

Stop-Process -Id 17512,21816
---

## What it will be

| | |
|---|---|
| **LLM** | Qwen3.5-9B (UD-Q4_K_XL, 5.56 GiB) via llama.cpp — **GPU** |
| **STT** | Parakeet TDT 0.6B v3 (ONNX) — **CPU** |
| **TTS** | Kokoro-82M (ONNX) — **CPU** |
| **Turn detection** | Silero VAD + Smart Turn v2 — **CPU** |
| **Orchestration** | Python 3.11, hand-written asyncio loop (no framework) |
| **Audio** | Browser/WebRTC with echo cancellation — speakers supported |
| **Target** | Windows 11, RTX 4060 Laptop (8 GB), 16 GB RAM |

The unusual choice — everything except the LLM on the CPU — follows from a single
constraint: after the model and its cache, roughly **1.1 GiB of VRAM remains**.
See [Resource Budget](docs/02-architecture/08-resource-budget.md).

---

## Read this first

> **Contra argues. It does not know things.**
>
> It runs a 9-billion-parameter model with no internet access and no ability to
> check anything. It will state things confidently that are wrong.
>
> Use it to test how well you can *defend* a position. Do not use it to find out
> what is *true*. If it cites a number, assume the number is invented until you
> have checked it yourself.

Why this warning is prominent rather than buried:
[Responsible AI](docs/06-governance/04-responsible-ai.md).

---

## Next step

**Phase 0 — [run the benchmarks](docs/04-quality/03-benchmark-plan.md).**

Every performance figure in the design is borrowed from someone else's hardware.
Five measurements — roughly two days — retire five of the top seven risks and
decide whether the design is viable before a line of application code is written.

---

## Quick links

| | |
|---|---|
| What this is and isn't | [Vision & Scope](docs/00-product/01-vision-and-scope.md) |
| How it works | [Architecture Overview](docs/02-architecture/01-architecture-overview.md) |
| Why it works that way | [ADR index](docs/02-architecture/adr/README.md) |
| What could go wrong | [Risk Register](docs/06-governance/01-risk-register.md) |
| What we don't know yet | [Open Questions](docs/06-governance/05-open-questions.md) |
| Plan | [Roadmap](docs/07-planning/01-roadmap.md) |

---

## Privacy

No audio, transcript, or derived data leaves the machine. Ever. The only step
requiring network access is the initial model download.

This is verified by test, not asserted: a release is blocked unless a full
session completes with the network adapter disabled.
[Security & Privacy](docs/06-governance/02-security-and-privacy.md).

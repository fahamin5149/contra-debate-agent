# Runbook

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

Day-to-day operation. For first-time setup see
[Installation Guide](01-installation-guide.md); for failures see
[Troubleshooting](03-troubleshooting.md).

---

## 1. Starting and stopping

```powershell
.\scripts\start.ps1              # supervised: llama-server + orchestrator
.\scripts\start.ps1 -NoLlm       # orchestrator only (llama-server already up)
python -m contra --ptt           # push-to-talk mode
python -m contra --debug         # verbose per-stage timings
```

**During development**, run `llama-server` in its own terminal and use
`-NoLlm`. The 20–40 s model load is then paid once, and the orchestrator can be
restarted freely against it.

Stopping: `Ctrl+C` in the orchestrator terminal. The current session is persisted
before exit. `llama-server` must be stopped separately if started independently.

---

## 2. Normal startup output

```
Contra v0.x.x
✓ GPU: RTX 4060 Laptop, 8188 MiB total, 7891 MiB free
✓ Model: Qwen3.5-9B-UD-Q4_K_XL.gguf (5,966,095,584 bytes)
✓ Audio in:  Headset Microphone (Jabra Evolve 65)
✓ Audio out: Headset Earphone (Jabra Evolve 65)
✓ LLM server healthy (127.0.0.1:8080), context 16384
✓ Speech models loaded (Parakeet, Kokoro, Silero, SmartTurn)
✓ UI at http://127.0.0.1:8000
  Config: default.yaml + user.yaml
  Prompt: debate-v3

Ready. State: IDLE
```

Anything missing a ✓ is a failure — the process should not have reached
`Ready`.

---

## 3. Running a session

| Action | How |
|---|---|
| Start a debate | Say your topic and position |
| Interrupt the agent | Just start speaking |
| Pause mid-argument | Do it — it waits for a complete thought |
| Force turn commit | Press and release the PTT key (if enabled) |
| End the session | "Let's stop there" / "End the session" |
| Change intensity | UI panel, or `PATCH /api/config` — takes effect next turn |
| Change voice | UI panel — takes effect next utterance |

> **Intensity changes apply to the *next* session, not mid-debate, if they alter
> the system prompt.** The prompt must stay byte-identical within a session or
> the prefix cache invalidates and TTFT jumps by hundreds of milliseconds
> ([Prompt Spec §9](../03-engineering/05-prompt-engineering-spec.md)).

---

## 4. Reading the state indicator

| State | Meaning | If it sticks here |
|---|---|---|
| `IDLE` | Awaiting a topic | Check the microphone is not muted |
| `LISTENING` | Awaiting your turn | Normal |
| `THINKING` | Generating; no audio yet | > 3 s → check LLM health |
| `SPEAKING` | Playing audio | Normal |
| `DEGRADED` | A component failed | See §7 |

> **`THINKING` is why the indicator exists.** In a voice-only interface,
> "generating" and "crashed" sound identical. Users fill the silence by talking,
> which triggers barge-in, which cancels the response they were waiting for. Watch
> the indicator rather than the silence.

---

## 5. Health checks

```powershell
curl http://127.0.0.1:8080/health      # LLM server
curl http://127.0.0.1:8000/health      # orchestrator
nvidia-smi                             # VRAM and GPU load
```

Healthy figures during a session:

| | Expected |
|---|---|
| VRAM used | ~6,900 MiB, stable |
| GPU utilisation | ~0% idle, 90–100% during generation bursts |
| GPU temperature | < 85 °C |
| Orchestrator RSS | ~2.5–3 GB, stable |

**Stability matters more than the absolute values.** VRAM or RSS climbing across
a session indicates a leak (NFR-REL-05) and should be investigated before it
becomes a crash at minute 45.

---

## 6. Reviewing sessions

```powershell
Get-ChildItem data\transcripts | Sort-Object LastWriteTime -Descending | Select -First 5
```

```sql
-- recent sessions with latency
SELECT s.id, s.topic, s.prompt_version,
       (s.ended_at - s.started_at)/60000 AS minutes,
       COUNT(t.id) AS turns,
       ROUND(AVG(m.total_ms)) AS avg_ms
FROM sessions s
JOIN turns t ON t.session_id = s.id
LEFT JOIN turn_metrics m ON m.turn_id = t.id
GROUP BY s.id ORDER BY s.started_at DESC LIMIT 10;
```

Layer 1 analysis queries are in
[Evaluation Framework §3](../04-quality/02-evaluation-framework.md).

---

## 7. Degraded mode

`DEGRADED` means a component failed but the session continues in reduced form.

| Symptom | Likely | Action |
|---|---|---|
| "I've lost my train of thought" | LLM died | Auto-restart in progress; wait 60 s |
| Robotic voice | Kokoro failed, Piper active | Restart at session end |
| Text lagging speech | UI WebSocket dropped | Refresh the browser |
| Worse transcription | Parakeet failed, Whisper active | Restart at session end |

Degradations are logged and announced once. A session can be finished in degraded
mode; restart afterwards rather than mid-argument.

---

## 8. Routine maintenance

| When | Task |
|---|---|
| Weekly | Review Layer 1 trends across sessions |
| Monthly | `VACUUM` the database |
| Monthly | Rotate `data/contra.log` |
| Per prompt change | Run Layer 2 probes before promoting |
| Per llama.cpp update | Re-run BM-01 — throughput can change materially |
| Per dependency update | Re-run BM-03 |

```powershell
sqlite3 data\contra.db "VACUUM;"
Move-Item data\contra.log data\contra.log.1 -Force
```

**Re-running BM-01 after a llama.cpp update is not paranoia.** Inference engines
change performance meaningfully between releases in both directions, and the
whole latency budget rests on that one number.

---

## 9. Changing the model

```powershell
# 1. stop everything
# 2. start llama-server with the new file
C:\llama.cpp\llama-server.exe -m C:\local-models\<new>.gguf -ngl 99 -c 16384 -fa `
  --host 127.0.0.1 --port 8080
# 3. verify: offloaded N/N layers
# 4. update config/user.yaml → llm.model
# 5. re-run BM-01
# 6. re-run Layer 2 probes — a different model needs the prompt re-validated
```

Step 6 is easy to skip and shouldn't be. The debate persona is tuned against a
specific model's instruction-following behaviour; a swap can silently reintroduce
sycophancy (probe P-01).

Switching to **Qwen3.5-4B** is the documented remedy for both throughput and VRAM
shortfalls ([Resource Budget §11](../02-architecture/08-resource-budget.md)).

---

## 10. Changing the debate persona

```powershell
cp prompts/debate/v3.md prompts/debate/v4.md
# edit v4.md
# edit prompts/ACTIVE.yaml → debate: v4
# restart
```

Then follow the promotion flow in
[Evaluation Framework §8](../04-quality/02-evaluation-framework.md): probes
first, real sessions second, and only then keep it active.

**Never edit a version in place.** The old file is the only evidence base against
which "is this better?" can be answered.

---

## 11. Backup

What matters:

| Path | Contains |
|---|---|
| `data/contra.db` | All sessions and metrics |
| `data/transcripts/` | Readable exports |
| `config/user.yaml` | Machine configuration |
| `prompts/` | Persona versions (also in git) |

```powershell
Copy-Item -Recurse data "D:\backup\contra-$(Get-Date -f yyyyMMdd)"
```

Models are large and re-downloadable; do not back them up.

> `data/` holds your actual debate transcripts. Back it up somewhere you would be
> comfortable keeping a private journal — it is closer to that than to
> application data.

---

## 12. Emergency stop

```powershell
Stop-Process -Name llama-server -Force
Stop-Process -Name python -Force        # careful — kills all Python
nvidia-smi                              # confirm VRAM released
```

A hard kill loses at most the in-flight turn; all committed turns are already
persisted (NFR-REL-03).

If VRAM is not released after killing `llama-server`, a zombie CUDA context
remains — `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` will
name the process.

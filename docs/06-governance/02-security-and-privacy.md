# Security & Privacy

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

---

## 1. The posture

> **Nothing leaves the machine. Ever.**

This is not a compliance checkbox. It is the product's central premise
([Vision §3](../00-product/01-vision-and-scope.md)).

The natural use of a debate partner is rehearsing arguments you are **not yet
ready to have in public** — a position at work, a disagreement with family, an
idea you suspect is wrong. That content is sensitive *precisely because it is
unfinished*.

A tool people self-censor in front of is worthless for this purpose. And trust
here is lost exactly once.

---

## 2. Data inventory

What exists, where it lives, and how sensitive it is.

| Data | Location | Persisted | Sensitivity |
|---|---|---|---|
| Raw microphone audio | RAM ring buffer (~30 s) | **No** | **Highest** |
| Interim transcripts | RAM | No | High |
| Committed transcripts | `data/contra.db` | **Yes** | **High** |
| Markdown exports | `data/transcripts/` | **Yes** | **High** |
| Agent responses | `data/contra.db` | Yes | Medium |
| Turn timings | `data/contra.db` | Yes | Low |
| Session metadata (topic) | `data/contra.db` | Yes | **High** |
| Logs | `data/contra.log` | Yes | Low (no content — see §5) |
| Config | `config/user.yaml` | Yes | Low |

### Two decisions worth explaining

**Raw audio is not persisted** (NFR-S-04). Audio carries identity, tone,
emotional state, ambient context, and other voices in the room. Text carries the
argument. Keeping the transcript and discarding the audio retains everything
useful in its least sensitive form.

**The topic field is high sensitivity.** It is easy to overlook because it is
short. But "am I right to leave my job" or "is my father wrong about this" is
often the most revealing single string in the database.

---

## 3. Network posture

| Phase | Network |
|---|---|
| Installation | Required — model downloads |
| **Every subsequent operation** | **None** |

### Enforcement

| Control | Mechanism |
|---|---|
| Loopback binding | Config invariant, **not overridable** — [Config §4](../03-engineering/04-configuration-management.md) |
| No telemetry | Audited dependencies; defaults disabled |
| Verification | **IT-06** — full session with the network adapter disabled |

### The loopback invariant

```python
if host not in ("127.0.0.1", "localhost", "::1"):
    raise ConfigError(...)   # cannot be overridden by user.yaml or env
```

> **`llama-server` has no authentication.** Bound to `0.0.0.0` on a laptop that
> joins café or hotel Wi-Fi, it is an open inference endpoint on the local
> network — and its context window holds whatever the user has been arguing
> about. Anyone on that network could query the model *and* potentially observe
> conversation state.
>
> This is why the binding is a hard invariant rather than a default.

### IT-06 is the real verification

Many ML libraries phone home on import — model metadata, version checks,
anonymised usage statistics. These are easy to miss by reading code and trivial
to catch by running with the adapter disabled.

**IT-06 is a release gate** ([Definition of Done §4](../04-quality/05-definition-of-done.md)).

---

## 4. Data at rest

| | |
|---|---|
| Encryption | **None** |
| Location | `data/` inside the repository directory |
| Permissions | Inherited from the user profile |

### Why unencrypted — and why that is documented rather than hidden

Application-level encryption here would provide **very little real protection**:
the key would have to be stored on the same machine, accessible to the same user
account. It protects against someone reading the raw file without the
application, and nothing else.

Meanwhile it would prevent the user from reading their own transcripts with
ordinary tools, complicate backups, and create a class of unrecoverable data
loss.

**The honest position:** if the device needs protection, that is what full-disk
encryption is for. BitLocker protects this data properly; a hand-rolled scheme
would provide the appearance of protection without the substance.

NFR-S-05 requires this to be **documented rather than silently assumed**, which
is the point of this section.

---

## 5. Logging

**Never log transcript content above `DEBUG`.**

```python
# WRONG
log.info("user_turn", text=transcript.text)

# RIGHT
log.info("user_turn", chars=len(transcript.text), confidence=0.94)
```

Log files are less protected than the database, more easily copied, and are the
thing most likely to be pasted into a bug report or shared for help. Logging
argument content there would quietly defeat the whole posture.

`logging.log_transcripts` exists for debugging, defaults to `false`, and when
enabled should be visibly indicated.

---

## 6. Local attack surface

| Surface | Exposure | Note |
|---|---|---|
| `127.0.0.1:8080` (llama-server) | Local processes | **No auth** — any local process can query |
| `127.0.0.1:8000` (orchestrator) | Local processes | No auth |
| `data/contra.db` | User account | Readable by the user and anything running as them |
| Microphone | Continuous while running | Live even in `THINKING` and `SPEAKING` |

**No authentication on the local ports.** This is a deliberate accepted risk: a
local attacker with code execution as this user has already won — they can read
the database directly, or the memory of the process. Adding auth would protect
against nothing while complicating every component.

The threat that *does* matter is the network-exposure one, addressed by the
loopback invariant.

Full analysis: [Threat Model](03-threat-model.md).

---

## 7. The microphone

The microphone is **live for the entire session**, including while the agent
speaks — that is what makes barge-in possible.

This deserves explicit treatment because it is the most invasive thing the
application does.

| Control | Status |
|---|---|
| Audio never persisted | ✅ NFR-S-04 |
| Audio never transmitted | ✅ NFR-S-01 |
| Ring buffer bounded (~30 s) | ✅ |
| Visible listening state | ✅ FR-41 |
| Mic released on session end | ✅ |

> **The state indicator is a privacy control, not only a usability one.** A user
> should never be uncertain whether the microphone is live. `IDLE` and `ENDED`
> release it; every other state shows explicitly that it is open.

---

## 8. Third-party components

All models run locally after download. None calls home at runtime.

| Component | Licence | Runtime network |
|---|---|---|
| Qwen3.5-9B | Apache 2.0 | None |
| Parakeet TDT (ONNX) | Community export | None |
| Kokoro-82M | Apache 2.0 | None |
| Silero VAD | MIT | None |
| llama.cpp | MIT | None |
| Pipecat | BSD | **Audit** — framework defaults |

**Pipecat warrants an audit.** It is designed primarily for cloud-service
pipelines and may include analytics or service-discovery defaults appropriate to
that context and not to ours. IT-06 catches these behaviourally; the audit
catches them deliberately.

---

## 9. User rights

| Right | Mechanism |
|---|---|
| See their data | Markdown transcripts; SQLite is inspectable |
| Delete their data | `contra sessions purge`, or delete `data/` (NFR-S-06) |
| Export | Transcripts are plain Markdown |
| Prevent collection | Nothing is collected; nothing to opt out of |

**No retention policy.** Automatically deleting a user's own debate history
without being asked would be worse than using 12 MB of disk. Deletion is a
deliberate act.

---

## 10. What this posture does not protect against

Stated plainly:

- **A compromised machine.** If malware runs as this user, everything is
  readable. Out of scope.
- **Someone with physical access and no disk encryption.** Use BitLocker.
- **Shoulder surfing / audible speech.** You are talking out loud.
- **Backups you make yourself.** Copying `data/` to cloud storage exports it.
  Worth remembering: it is closer to a private journal than to application data.
- **Screen recording or ambient recording by other software.**

The guarantee is specific and it is real: **this application does not transmit,
and does not persist audio.** It is not a claim about the security of the machine
it runs on.

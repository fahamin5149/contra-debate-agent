# Internal API Specification

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

Contracts between processes and across component boundaries. Everything here is
**localhost-only** (NFR-S-03); no interface in this document is reachable from
the network.

---

## 1. Interface inventory

| # | Interface | Transport | Between |
|---|---|---|---|
| **A** | LLM inference | HTTP + SSE, `127.0.0.1:8080` | Orchestrator → llama-server |
| **B** | UI updates | WebSocket, `127.0.0.1:8000` | Orchestrator → browser UI |
| **C** | Control | HTTP, `127.0.0.1:8000` | UI → Orchestrator |
| **D** | Audio chunk metadata | In-process | TtsStage → AudioOutput |
| **E** | Session persistence | SQLite | Orchestrator → disk |

---

## A. LLM inference — llama-server

### A.1 Endpoint

```
POST http://127.0.0.1:8080/v1/chat/completions
Content-Type: application/json
```

OpenAI-compatible. Consumed with the standard `openai` Python SDK pointed at
`base_url="http://127.0.0.1:8080/v1"`.

### A.2 Request

```jsonc
{
  "model": "qwen3.5-9b",
  "messages": [
    { "role": "system", "content": "<debate persona + session variables>" },
    { "role": "user", "content": "<turn 1>" },
    { "role": "assistant", "content": "<turn 1 as spoken>" },
    { "role": "user", "content": "<current turn>" }
  ],
  "stream": true,
  "temperature": 0.7,
  "top_p": 0.8,
  "top_k": 20,
  "min_p": 0.0,
  "presence_penalty": 1.5,
  "repeat_penalty": 1.0,
  "max_tokens": 220,
  "chat_template_kwargs": { "enable_thinking": false }
}
```

| Field | Value | Rationale |
|---|---|---|
| `stream` | **always `true`** | Non-streaming makes NFR-P-01 unreachable |
| `presence_penalty` | 1.5 | Unusually high; prevents recycled talking points across turns ([Model Analysis](../01-research/02-model-analysis.md)) |
| `max_tokens` | 220 | ~45 s of speech. Comprehension limit *and* latency lever. |
| `enable_thinking` | `false` | Default on 9B, set explicitly so a model swap cannot silently change it |

> **`max_tokens` is a hard stop, not a target.** The prompt must also instruct
> brevity — a response truncated at exactly 220 tokens ends mid-sentence, which
> sounds like a crash. See
> [Prompt Engineering Spec](../03-engineering/05-prompt-engineering-spec.md).

### A.3 Response stream

Standard SSE:

```
data: {"choices":[{"delta":{"content":"Product"},"finish_reason":null}]}
data: {"choices":[{"delta":{"content":"ivity"},"finish_reason":null}]}
data: {"choices":[{"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

### A.4 Cancellation — **the contract that matters**

On barge-in the client MUST **abort the underlying HTTP request**, not merely
stop iterating the stream.

```python
async def cancel(self) -> None:
    if self._request_task:
        self._request_task.cancel()          # closes the connection
        await self._await_cancelled()
```

**Why.** `llama-server` continues generating until the connection closes or the
token limit is reached. Abandoning the iterator without closing the socket leaves
the GPU producing text nobody will hear — occupying the slot the *next* turn
needs. The visible symptom is that interrupting the agent makes the following
response slower, which is the opposite of the intent.

| Requirement | Value |
|---|---|
| Cancellation must complete within | 100 ms |
| Slot must be free for the next request within | 200 ms |

### A.5 Health

```
GET http://127.0.0.1:8080/health   →  200 {"status":"ok"}
```

Polled at startup until healthy or 120 s (model load can take 40 s cold). Also
polled every 30 s during a session to detect a silently dead backend.

### A.6 Error handling

| Condition | Client behaviour |
|---|---|
| Connection refused at startup | Fail with FR-52 message naming the fix |
| Connection lost mid-stream | → `DEGRADED`, speak an acknowledgement, request restart |
| HTTP 503 (slot busy) | Retry once after 200 ms; then `DEGRADED` |
| Malformed SSE frame | Log, skip the frame, continue |
| No token within 5 s of request | Treat as failure |

---

## B. UI updates — WebSocket

```
ws://127.0.0.1:8000/ws
```

Server → client, JSON, one message per event. The UI is a view; it holds no
authoritative state.

### B.1 Message envelope

```jsonc
{
  "type": "state_change" | "transcript" | "metrics" | "error",
  "session_id": "uuid",
  "seq": 42,                    // monotonic; client detects gaps
  "ts": 1756500000.123,
  "payload": { }
}
```

### B.2 Message types

**`state_change`** — must reach the UI within 100 ms (NFR-P-05).
```jsonc
{ "type": "state_change",
  "payload": { "state": "THINKING", "previous": "LISTENING" } }
```

**`transcript`**
```jsonc
{ "type": "transcript",
  "payload": {
    "role": "user" | "agent",
    "text": "But that ignores the cost of…",
    "final": false,              // interim text renders differently (US-403)
    "turn_id": 7
  } }
```

**`metrics`** — per turn, dev display (FR-42)
```jsonc
{ "type": "metrics",
  "payload": {
    "turn_id": 7,
    "vad_ms": 250, "turn_detect_ms": 118, "stt_ms": 205,
    "llm_ttft_ms": 380, "tts_ttfb_ms": 140, "total_ms": 1193,
    "tokens_generated": 164, "tokens_per_sec": 31.2
  } }
```

**`error`**
```jsonc
{ "type": "error",
  "payload": {
    "code": "LLM_UNREACHABLE",
    "message": "Lost connection to the model server.",
    "remediation": "Check that llama-server is running on port 8080.",
    "fatal": false
  } }
```

`remediation` is a required field, not an optional nicety — NFR-U-03 forbids
errors that state a problem without stating an action.

### B.3 Reconnection

The UI is non-essential; the session continues without it. On reconnect the
client sends its last `seq` and the server replays missed messages from a
256-entry ring buffer, or sends a full state snapshot if the gap is larger.

---

## C. Control — HTTP

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/session/start` | Begin a session (optional; voice is primary) |
| `POST` | `/api/session/end` | End the current session |
| `POST` | `/api/session/ptt` | Push-to-talk down/up (FR-43) |
| `GET` | `/api/config` | Current effective configuration |
| `PATCH` | `/api/config` | Update runtime-tunable settings |
| `GET` | `/api/sessions` | List past sessions |
| `GET` | `/api/sessions/{id}/transcript` | Fetch a transcript |
| `GET` | `/health` | Orchestrator health |

**Only a subset of config is runtime-patchable** — intensity, max response
length, and voice. Model, device, and context size require a restart, and
`PATCH` rejects them with 409 rather than accepting them and silently doing
nothing.

---

## D. Audio chunk metadata — in-process

The contract that makes FR-13 implementable. Small, and easy to get wrong.

```python
@dataclass(frozen=True)
class AudioChunk:
    samples: bytes            # PCM16 mono @ 24 kHz (Kokoro native)
    text_span: tuple[int, int]  # [start, end) char offsets into the turn's
                                # dispatched text — NOT into the sentence
    duration_ms: float
    sequence: int             # monotonic within a turn

@dataclass(frozen=True)
class PlaybackPosition:
    chunks_played: int
    samples_played: int
    last_complete_span_end: int   # char offset — the truncation point
```

### Rules

1. `text_span` offsets are **absolute within the agent turn**, not relative to
   the sentence. This is the easy mistake: a per-sentence offset makes
   truncation across multiple chunks silently wrong.
2. Spans must be **contiguous and non-overlapping** across a turn.
3. `AudioOutput` tracks the highest fully-played `text_span[1]`.
4. On `clear()`, truncation uses `last_complete_span_end`, then rounds **back to
   the last word boundary**, so history holds `"…higher out"` rather than a
   mid-syllable cut.
5. A partially-played chunk counts as **not played**. Conservative by design —
   under-recording what the user heard is far safer than over-recording it.

### Test hook

Invariant I-3 ([Data Flow & State](04-data-flow-and-state.md)) is asserted here:
after any `clear()`, the truncated turn text must be a prefix of the dispatched
text, and its length must not exceed `last_complete_span_end`.

---

## E. Persistence

SQLite via the repository layer. Schema in [Data Model](06-data-model.md).

| Property | Value |
|---|---|
| Journal mode | WAL |
| Synchronous | `NORMAL` |
| Turn writes | **Synchronous, before the next turn begins** (NFR-REL-03) |
| Metrics writes | May batch |

---

## 2. Port allocation

| Port | Service | Binding | Auth |
|---|---|---|---|
| 8080 | llama-server | `127.0.0.1` | **None** |
| 8000 | Orchestrator HTTP + WS | `127.0.0.1` | **None** |

> **Binding is a security control here, not a configuration detail.**
> `llama-server` has no authentication. Bound to `0.0.0.0` on a laptop that joins
> café Wi-Fi, it is an open inference endpoint — and its context window may hold
> whatever the user has been arguing about. The startup preflight MUST assert
> loopback binding and refuse to start otherwise.
> [Threat Model](../06-governance/03-threat-model.md).

Both ports are configurable for collision avoidance; the loopback binding is not.

---

## 3. Versioning

Internal interfaces, single deployable, no external consumers — so no formal
versioning. Two rules instead:

1. The WebSocket envelope carries `seq` so clients detect gaps.
2. Breaking changes to interface **D** require updating the FR-13 invariant tests
   in the same commit. That contract is subtle enough that a silent break would
   otherwise surface weeks later as inexplicable agent behaviour.

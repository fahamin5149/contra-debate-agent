# Product Requirements Document (PRD)

| | |
|---|---|
| **Status** | Draft |
| **Owner** | Amin Fahim |
| **Last updated** | 2026-08-30 |
| **Related** | [Vision & Scope](01-vision-and-scope.md) · [User Stories](04-user-stories.md) · [NFRs](05-non-functional-requirements.md) |

---

## 1. Summary

Contra is an offline, voice-driven debate opponent. The user speaks a topic and
their position; the agent adopts the opposing position and argues it in spoken
conversation until the user ends the session. All inference runs on local
hardware.

## 2. Requirement notation

Requirements use **MUST** / **SHOULD** / **MAY** in the RFC 2119 sense. Each has
a stable ID (`FR-nn`) referenced from user stories and tests. A requirement
without a testable acceptance criterion is a wish, not a requirement, and is
marked as such.

---

## 3. Functional requirements

### 3.1 Session lifecycle

| ID | Requirement | Priority |
|---|---|---|
| **FR-01** | The system MUST let the user start a session by speaking a topic and their own position. | P0 |
| **FR-02** | The system MUST confirm the topic and assigned sides back to the user before the debate begins, so misheard topics are caught immediately. | P0 |
| **FR-03** | The system MUST let the user end a session by voice command. | P0 |
| **FR-04** | The system MUST persist a full transcript of every session. | P0 |
| **FR-05** | The system SHOULD let the user resume a prior session, restoring the position and argument history. | P2 |
| **FR-06** | The system MAY offer a topic-suggestion mode when the user has none. | P3 |

### 3.2 Conversation mechanics

| ID | Requirement | Priority |
|---|---|---|
| **FR-10** | The system MUST transcribe user speech to text with sufficient accuracy that argument content survives — see NFR-Accuracy. | P0 |
| **FR-11** | The system MUST decide when the user has finished a turn using **both** acoustic and semantic signals, not silence duration alone. | P0 |
| **FR-12** | The system MUST allow barge-in: user speech during agent playback stops that playback. | P0 |
| **FR-13** | On barge-in, the system MUST record what the agent had *actually spoken aloud* — not what it had generated — as the conversation history. | P0 |
| **FR-14** | The system MUST stream synthesis, beginning playback before the full response is generated. | P0 |
| **FR-15** | The system SHOULD emit a brief acknowledgement token ("Hm—", "Right,") when generation will exceed ~800 ms, to cover latency. | P2 |
| **FR-16** | The system MUST NOT treat its own audio output as user input, **including when played through speakers**. | P0 |
| **FR-17** | The system MUST preserve the user's speech during double-talk — echo cancellation must not suppress an interruption along with the echo. | P0 |

> **FR-13 is subtle and load-bearing.** If the agent generates four sentences,
> speaks one and a half, and is interrupted, the conversation history must
> contain one and a half sentences. Storing all four means the agent later
> references arguments the user never heard — which reads as gaslighting. See
> [Data Flow & State](../02-architecture/04-data-flow-and-state.md).

### 3.3 Debate behaviour

| ID | Requirement | Priority |
|---|---|---|
| **FR-20** | The agent MUST adopt the position opposing the user's stated one. | P0 |
| **FR-21** | The agent MUST hold that position for the session unless FR-25 conditions are met. | P0 |
| **FR-22** | The agent MUST structure substantive turns as claim → warrant → evidence, and rebuttals as an explicit engagement with the user's actual argument. | P0 |
| **FR-23** | The agent MUST argue the strongest available form of its position (steelman), never a caricature. | P0 |
| **FR-24** | The agent MUST NOT concede merely because the user repeats, raises volume, or expresses frustration. | P0 |
| **FR-25** | The agent MUST concede a specific point when the user presents an argument that genuinely defeats it, and MUST say so explicitly rather than silently dropping the point. | P1 |
| **FR-26** | The agent MUST distinguish factual claims it is confident in from ones it is not, and verbally mark the latter. | P1 |
| **FR-27** | The agent MUST reference the user's earlier arguments by content when relevant ("you said earlier that…"). | P1 |
| **FR-28** | The agent MUST NOT use manipulative rhetoric: fabricated statistics, invented citations, or Gish gallop. | P0 |
| **FR-29** | The agent SHOULD vary turn length — short jabs and longer constructive arguments — rather than emitting uniform paragraphs. | P2 |

### 3.4 Configuration

| ID | Requirement | Priority |
|---|---|---|
| **FR-30** | The user MUST be able to set debate intensity across at least three levels (Socratic / standard / aggressive). | P1 |
| **FR-31** | The user MUST be able to configure maximum spoken response length. | P1 |
| **FR-32** | The user SHOULD be able to select a synthesis voice. | P2 |
| **FR-33** | All tuning MUST live in configuration files, not code. | P0 |

### 3.5 Interface

| ID | Requirement | Priority |
|---|---|---|
| **FR-40** | The system MUST show a live transcript of both sides during the session. | P1 |
| **FR-41** | The system MUST display current state (listening / thinking / speaking) unambiguously. | P0 |
| **FR-42** | The system SHOULD display measured latency for the last turn during development. | P2 |
| **FR-43** | The system MUST provide a push-to-talk fallback for when automatic turn detection misbehaves. | P1 |

> **FR-41 exists because of a specific failure.** In a voice-only interface,
> "the agent is thinking" and "the agent has crashed" are indistinguishable.
> Users respond by talking over the silence, which triggers barge-in, which
> cancels the response they were waiting for. A visible state indicator breaks
> that loop.

### 3.6 Operational

| ID | Requirement | Priority |
|---|---|---|
| **FR-50** | The system MUST run with no network connectivity after installation. | P0 |
| **FR-51** | The system MUST start from a single command. | P1 |
| **FR-52** | The system MUST detect and report clearly when the LLM backend is unavailable. | P0 |
| **FR-53** | The system MUST log structured per-turn timings for each pipeline stage. | P1 |
| **FR-54** | The system SHOULD degrade gracefully if a component fails mid-session rather than terminating. | P2 |

---

## 4. Priority definitions

| | Meaning |
|---|---|
| **P0** | v1.0 does not ship without it. |
| **P1** | v1.0 ships without it only with an explicit written decision. |
| **P2** | Desirable; cut freely under time pressure. |
| **P3** | Idea captured so it is not lost. Not committed. |

---

## 5. Explicit non-requirements

Restated from [Vision & Scope §5](01-vision-and-scope.md#5-explicitly-out-of-scope-for-v10)
because PRDs are read in isolation:

- No multi-user, networking, or telephony.
- No web search, retrieval, or external knowledge.
- No voice cloning.
- No mobile or hosted deployment.
- No automated judging of who won.
- No fine-tuning.

---

## 6. Dependencies and assumptions

| | Detail | Confidence |
|---|---|---|
| Model file | `Qwen3.5-9B-UD-Q4_K_XL.gguf`, 5.556 GiB, present at `C:\local-models\` | **[VERIFIED]** |
| Runtime | llama.cpp with CUDA, recent build (Qwen3.5 hybrid graph support) | **[SOURCED]** |
| GPU | RTX 4060 Laptop, 8188 MiB | **[VERIFIED]** |
| Generation speed | 25–35 tok/s for a 9B Q4 on this class of GPU | **[SOURCED]** — must be reproduced, see [Benchmark Plan](../04-quality/03-benchmark-plan.md) |
| Display GPU | Intel UHD iGPU drives the display, leaving the 4060 unencumbered | **[ASSUMED]** — verify under load |

The generation-speed assumption is the riskiest item here. The entire latency
design rests on it and it has not yet been measured on this machine. Benchmark
BM-01 exists to close that gap before implementation starts.

---

## 7. Release gate

v1.0 ships when every P0 requirement passes its acceptance test in
[User Stories](04-user-stories.md), the NFR thresholds in
[NFRs](05-non-functional-requirements.md) are met on the target machine, and the
[Definition of Done](../04-quality/05-definition-of-done.md) is satisfied for
each.

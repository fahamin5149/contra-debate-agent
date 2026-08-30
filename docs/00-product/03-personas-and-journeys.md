# Personas & User Journeys

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

---

## 1. On writing personas for a project with one user

The primary user of Contra is the person building it. Writing formal personas
for an audience of one usually produces theatre.

They earn their place here for a different reason: **they encode which failure
modes we care about.** "The agent is too slow" means something different to
someone rehearsing a presentation than to someone idly exploring an idea. The
personas below exist to make those differences explicit, so that when we trade
latency against argument quality we know whose experience we are optimising.

---

## 2. Primary persona — the Sharpener

> **Amin, engineer.** Has a position on something contested — a technical
> direction at work, a policy view, a decision he is about to commit to. Suspects
> his reasoning has gaps but cannot find them alone, because the gaps are exactly
> where his intuition stops looking.

**Goal.** Leave with a stronger version of the position, or with the knowledge
that it does not survive contact.

**Context of use.** Evening, at a desk, **speaking out loud through laptop
speakers**. Sessions of 10–40 minutes. Often unplanned — the urge arrives with
the thought.

> The speakers detail is not incidental to the persona. It means the agent must
> not hear itself, which makes echo cancellation a P0 requirement rather than a
> refinement ([ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md)).
> It also fits the persona: someone arguing at a desk in the evening does not
> want to put a headset on first.

**What makes the tool fail for him**

| Failure | Why it is fatal |
|---|---|
| Agreeableness | If it folds under pressure, he learns nothing. This is the single worst outcome. |
| Vagueness | Generic counterarguments he already anticipated are worse than silence. |
| Latency > ~2 s | Breaks the rhythm of argument. He starts composing while waiting, which defeats the point. |
| Fabricated facts | Once he catches one, he distrusts all of them, and the tool becomes unusable. |

**What makes it succeed.** One moment per session where he has to stop and
actually think. That is the whole product.

---

## 3. Secondary persona — the Rehearser

> Preparing for a real conversation with real stakes: a salary negotiation, a
> design review he expects to be challenged in, a difficult family conversation.

**Goal.** Encounter the objections *before* the room does.

**Differs from the Sharpener in one important way:** he does not want his mind
changed. He wants his position stress-tested. The agent should press hard on
weak points without trying to convert him.

**Design implication.** Intensity must be configurable
([FR-30](02-product-requirements.md#34-configuration)), and "aggressive" must
mean *persistent cross-examination*, not *rhetorically dirty*.

---

## 4. Tertiary persona — the Practitioner

> Practising the skill of arguing itself — thinking on their feet, structuring a
> rebuttal under time pressure, not losing the thread.

**Goal.** Repetition. Wants many short sessions, and wants the opponent to be
*consistent* so that improvement is attributable to them.

**Design implication.** This persona is the reason
[OQ-02](../06-governance/05-open-questions.md) (structured formal debate with
timed rounds) stays open. The Sharpener wants free-flowing conversation; the
Practitioner wants rounds and constraints. These are different products sharing
a pipeline, and v1 serves the Sharpener.

---

## 5. Journey A — first-ever session (cold start)

The riskiest journey. Everything that can go wrong with drivers, models, and
audio devices goes wrong here.

```
1. Runs installer / setup script
2. Setup verifies: GPU present, model file found and correct size,
   audio devices enumerated
   ↓ any check fails → specific, actionable error (not a stack trace)
3. First launch: llama-server starts, model loads (~20-40 s from cold disk)
   ↓ UI shows explicit "loading model" state with progress
4. Mic level meter appears; user confirms input device is correct
5. Agent speaks a short greeting — this doubles as an output-device test
6. User states topic and position
7. Agent confirms both back  ← FR-02
8. Debate begins
```

**Design implications**

- Step 2 must run **before** the 30-second model load, so failures surface fast.
- Step 5 is not politeness. It is the only way a user discovers that output is
  routed to a disconnected HDMI monitor before they have spoken a whole argument
  into the void.
- Step 7 is not politeness either. Mis-transcribing the topic poisons the entire
  session, and the cost of confirming is three seconds.

## 6. Journey B — the core loop

```
User speaks ─→ VAD detects speech onset
             ─→ streaming transcription accumulates
             ─→ user pauses
                 ├─ semantic turn detector: "incomplete" → keep listening
                 └─ semantic turn detector: "complete"  → commit turn
             ─→ transcript + history → LLM
             ─→ first sentence emitted → TTS → playback begins
             ─→ remaining sentences stream and queue
             ─→ playback completes → return to listening
```

The branch after "user pauses" is the difference between a tool that feels like
a conversation and one that feels like a walkie-talkie. See
[ADR-0007](../02-architecture/adr/0007-two-layer-turn-detection.md).

## 7. Journey C — interruption

```
Agent is speaking
  ─→ VAD detects user speech (~50 ms)
  ─→ playback stops, queued audio discarded        target: <300 ms total
  ─→ LLM generation cancelled
  ─→ history records ONLY the audio actually played   ← FR-13
  ─→ user's interrupting speech is transcribed normally
  ─→ agent responds to the interruption
```

This journey has two failure modes worth naming, and they pull in opposite
directions. If the agent's own voice leaks into the microphone it interrupts
*itself*, forever. If echo cancellation over-corrects, it suppresses the user's
interruption too and the agent becomes **uninterruptible** — which looks like
success until you try to cut in. Both are addressed by
[ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md) and
measured by [BM-05](../04-quality/03-benchmark-plan.md).

## 8. Journey D — review after the fact

```
Session ends
  ─→ transcript persisted with per-turn timings
  ─→ user can read back the exchange
  ─→ (v2) argument map: claims, rebuttals, unresolved threads
```

Deliberately thin in v1. Worth noting that this journey is **only possible
because of the cascaded architecture** — a speech-to-speech model produces no
intermediate text to review. See
[ADR-0001](../02-architecture/adr/0001-cascaded-pipeline-over-speech-to-speech.md).

---

## 9. Journeys we are not designing for

| Journey | Why not |
|---|---|
| Two humans debating with an AI moderator | Different product. Requires multi-party audio. |
| Agent-vs-agent debate the user watches | Fun, cheap to build, teaches the user nothing. |
| Asynchronous / text-only debate | The medium is the point. |
| Debate about the user's private documents | Requires RAG; breaks v1 scope. Strong v2 candidate. |

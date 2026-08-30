# Vision & Scope

| | |
|---|---|
| **Status** | Draft — awaiting owner review |
| **Owner** | Amin Fahim |
| **Last updated** | 2026-08-30 |

---

## 1. Problem statement

Thinking clearly about a contested question is hard alone. The failure mode is
well documented: we generate reasons for what we already believe, and we rarely
encounter the strongest version of the opposing case. Talking it through with a
person fixes this, but a suitable person is rarely available at the moment the
thought occurs, and the ones who are available are often too polite to press.

Existing tools do not fill the gap:

- **Cloud chatbots** are agreeable by design. Ask one to disagree and it will
  perform disagreement for a turn or two, then capitulate to social pressure.
  They also require sending your half-formed thinking to a third party.
- **Text chat** is the wrong medium. Argument is a spoken skill. Typing gives
  you time to compose, which is exactly the crutch you are trying to remove.
- **Debate practice partners** are scarce, scheduled, and cannot be summoned at
  23:00 on a Tuesday.

## 2. Vision

> An opponent that is always available, never tires, never flatters, and never
> reports what you said to anyone.

Contra is a voice-first debate partner that runs entirely on local hardware. You
state a position out loud. It takes the other side and argues it properly — with
evidence, warrants, and rebuttals — at conversational speed. It remembers what
you claimed twenty minutes ago and will hold you to it.

The measure of success is not that Contra wins. It is that you leave the
conversation holding a **better-formed version of your own view**, having been
forced to defend it against something that did not let you off easily.

## 3. Why local, specifically

Local execution is not a technical preference here; it is a product requirement,
for three independent reasons.

**Privacy.** The natural use of this tool is rehearsing arguments you are not
yet ready to have in public — a position at work, a disagreement with a family
member, an idea you suspect is wrong. That content is sensitive precisely
because it is unfinished. A tool people self-censor in front of is worthless.

**Latency floor.** A local model on the same machine has no network hop. This
matters more for interruption handling than for response time: barge-in must
feel instantaneous, and a round trip to a datacentre puts a floor under it.

**Cost of use.** Debate practice means long sessions, frequently. Per-token
billing creates a subtle pressure to be brief that works directly against the
purpose. Local inference is free at the margin, so a two-hour argument costs
nothing and the tool gets used.

## 4. In scope for v1.0

| Capability | Notes |
|---|---|
| Spoken conversation, full duplex | User speaks, agent responds in voice |
| Barge-in / interruption | User can cut the agent off mid-sentence |
| Position holding | Agent picks a side and defends it across the session |
| Steelmanning | Agent argues the strongest form of its side, not a caricature |
| Session transcript | Full text record, reviewable after the fact |
| Topic selection | User states a topic and their side; agent takes the other |
| Configurable intensity | From Socratic questioning to aggressive cross-examination |
| Fully offline operation | No network calls after installation |

## 5. Explicitly out of scope for v1.0

Listing these is as important as listing the features. Each was considered and
deliberately cut.

| Excluded | Why |
|---|---|
| **Multi-user / networked debate** | Solves a different problem. The infrastructure cost (WebRTC signalling, session management, auth) dwarfs the single-user product. |
| **Telephony / SIP** | No user need. This is the main reason we are not adopting LiveKit — see [ADR-0003](../02-architecture/adr/0003-pipecat-as-orchestration-framework.md). |
| **Voice cloning** | Technically available via Chatterbox. Adds VRAM cost and a misuse surface for zero product benefit. |
| **Web search / RAG / citations** | Very tempting and explicitly deferred. It breaks the offline guarantee, and a debate agent that cites sources it cannot verify is worse than one that argues from reasoning alone. Revisit in v2. |
| **Mobile or web-hosted deployment** | The model does not fit on a phone, and hosting it breaks the privacy premise. |
| **Vision / image input** | The model supports it (`mmproj`), but loading the vision tower costs ~0.9 GB of VRAM we do not have. See [ADR-0002](../02-architecture/adr/0002-llama-cpp-server-as-llm-runtime.md). |
| **Multilingual** | The model covers 201 languages, but the STT and TTS choices are English-optimised. English-only for v1; the constraint is in the speech layer, not the LLM. |
| **Fine-tuning the model** | The stock instruct model plus good prompting should clear the bar. Fine-tuning is a large project with its own data requirements. Revisit only if prompting demonstrably fails. |
| **Scoring / "who won"** | Judging debate quality is a research problem (see [Evaluation Framework](../04-quality/02-evaluation-framework.md)). Shipping a bad judge is worse than shipping none. |

## 6. Success criteria

The project has succeeded at v1.0 when all of the following hold:

**Functional**

1. A user can hold a ten-minute spoken debate without touching the keyboard.
2. The agent maintains a consistent position for the whole session — it does not
   silently switch sides or concede under mere repetition.
3. The user can interrupt mid-sentence and the agent stops within ~300 ms.

**Performance** — see [Latency Budget](../02-architecture/07-latency-budget.md)

4. Median time from end-of-user-speech to first agent audio ≤ **1,200 ms**.
5. P95 ≤ **2,000 ms**.
6. The system runs a 30-minute session without VRAM exhaustion or degradation.

**Qualitative** — the honest ones

7. The user reports being *changed* by at least one exchange in five sessions:
   a position sharpened, a weak argument abandoned, a consideration missed.
8. The user chooses to use it again unprompted. Nothing else on this list
   matters if this one fails.

## 7. Anti-goals

Things we could build, that would look like progress, and that we are choosing
not to want:

- **Winning.** An agent optimised to win will exploit rhetorical tricks, Gish
  gallop, and confident fabrication. All are effective and all defeat the
  purpose. See [Responsible AI](../06-governance/04-responsible-ai.md).
- **Agreeableness.** The failure mode of every consumer chatbot. If Contra
  concedes because you pushed back rather than because you were right, it is broken.
- **Encyclopedic accuracy.** This is not a research tool. A 9B model will get
  facts wrong. The design response is to make the agent argue from reasoning
  and explicitly flag factual uncertainty — not to pretend to a reliability it
  does not have.
- **Feature breadth.** The temptation with a working voice pipeline is to bolt
  on assistant features. Every one of those dilutes the single thing this does.

## 8. Key constraint, stated once

The target machine has an **8 GB RTX 4060**. The model and its cache consume
roughly 6.9 GiB of that, leaving ~1.1 GiB for everything else. This constraint
shapes nearly every technical decision in this tree and is documented in full in
[Resource Budget](../02-architecture/08-resource-budget.md).

## 9. Open questions

Tracked in [Open Questions](../06-governance/05-open-questions.md). The ones
that most affect scope:

- ~~**OQ-01** — Headphones or speakers?~~ ✅ **Closed: speakers.** Acoustic echo
  cancellation is therefore mandatory, and the audio path runs through a browser
  ([ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md)).
- **OQ-02** — Structured formal debate (timed rounds) or free-flowing argument?
- **OQ-04** — Should the agent ever concede? A partner that can never be
  persuaded is a wall, not an opponent.

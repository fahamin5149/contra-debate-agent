# User Stories & Acceptance Criteria

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |
| **Related** | [PRD](02-product-requirements.md) · [Test Strategy](../04-quality/01-test-strategy.md) |

---

## Format

Each story carries a stable ID, the requirements it satisfies, and acceptance
criteria in Given/When/Then. Criteria are written to be **mechanically testable
where possible** and are marked `[MANUAL]` where human judgement is unavoidable.

The `[MANUAL]` markers are honest, not lazy. "The rebuttal engaged with my actual
argument" cannot be asserted in a unit test, and pretending otherwise produces
tests that pass while the product fails.

---

## Epic 1 — Session setup

### US-101 · Start a debate by voice
> As a user, I want to state my topic and position out loud, so that I can begin
> without touching the keyboard.

**Satisfies:** FR-01, FR-02

```gherkin
Given the system is running and in the Idle state
When  I say "I want to argue that remote work is better for productivity"
Then  the system transcribes the topic and my position
And   it replies with a confirmation naming both the topic and which side each party holds
And   it enters the Awaiting-Confirmation state
```

```gherkin
Given the system has proposed a topic and sides
When  I say "no, I meant hybrid work"
Then  the system discards the proposal and re-enters topic capture
And   it does NOT begin the debate
```

**Notes.** The second criterion exists because mis-transcription of the topic is
unrecoverable once the debate starts — every subsequent turn compounds the error.

---

### US-102 · Reject an incorrectly heard topic
> As a user, I want to correct a misheard topic before the debate begins.

**Satisfies:** FR-02

```gherkin
Given the transcription confidence for the topic utterance is below threshold
When  the system confirms the topic
Then  the confirmation explicitly invites correction ("did I get that right?")
```

---

### US-103 · End a session by voice
**Satisfies:** FR-03, FR-04

```gherkin
Given a debate is in progress
When  I say "let's stop there" or "end the session"
Then  playback stops within 1 second
And   the transcript is written to disk before the process exits
And   the transcript contains every committed turn from both parties
```

---

## Epic 2 — The conversation loop

### US-201 · Be heard accurately
**Satisfies:** FR-10

```gherkin
Given I speak a 20-second argument at conversational pace in a quiet room
When  the system transcribes it
Then  word error rate is below 10%
And   no words are transcribed during the silences between my sentences
```

**Notes.** The second criterion targets a specific known failure: Whisper-family
models hallucinate text into silence ("Thank you for watching"). In a debate with
long thinking pauses this is not cosmetic — phantom text enters the argument
history. It is a primary reason for
[ADR-0005](../02-architecture/adr/0005-parakeet-tdt-for-stt.md).

---

### US-202 · Not be interrupted while thinking
> As a user, I want to pause mid-argument to gather my thoughts without the
> agent jumping in.

**Satisfies:** FR-11

```gherkin
Given I am speaking and I pause for 900 ms mid-sentence
And   my utterance so far is grammatically incomplete ("...and the problem with that is")
When  the pause elapses
Then  the system continues listening
And   it does NOT commit my turn
```

```gherkin
Given I have finished a complete thought
And   I stop speaking
When  600 ms of silence elapse
Then  the system commits my turn and begins generating
```

**Notes.** These two criteria are in direct tension and cannot both be satisfied
by a silence timer. Satisfying both is the entire justification for semantic
turn detection —
[ADR-0007](../02-architecture/adr/0007-two-layer-turn-detection.md).

---

### US-203 · Interrupt the agent
**Satisfies:** FR-12, FR-13

```gherkin
Given the agent is speaking
When  I begin speaking over it
Then  agent audio ceases within 300 ms
And   any queued-but-unplayed audio is discarded
And   in-flight LLM generation is cancelled
```

```gherkin
Given the agent had generated 4 sentences and spoken only the first 1.5
When  I interrupt
Then  the conversation history records ONLY the ~1.5 sentences actually played
And   the agent never subsequently refers to the unspoken 2.5 sentences as things it said
```

**Notes.** The second criterion is the highest-value test in this document. It is
also the one most likely to be forgotten, because it passes trivially in any
non-streaming implementation and fails silently in a streaming one.

---

### US-204 · Not hear the agent interrupt itself
**Satisfies:** FR-16

```gherkin
Given the agent is speaking through the configured output device
And   the user is silent
When  the agent's own audio reaches the microphone
Then  the system does NOT register a barge-in
And   the agent completes its turn
```

```gherkin
Given the agent is speaking through speakers
When  I interrupt it mid-sentence
Then  my speech is transcribed correctly despite the agent's audio overlapping it
```

**Notes.** The user has confirmed **speakers**, so this requires working acoustic
echo cancellation — see
[ADR-0012](../02-architecture/adr/0012-browser-webrtc-transport-with-aec.md).

> The two scenarios above test opposite failure directions and **both must
> pass**. The first fails if cancellation is too weak (agent hears itself); the
> second fails if it is too aggressive (user's interruption suppressed along with
> the echo). Passing only the first would look like success and produce an agent
> that cannot be interrupted. NFR-A-05 and NFR-A-06;
> [BM-05](../04-quality/03-benchmark-plan.md).

---

### US-205 · Hear a response quickly
**Satisfies:** FR-14, NFR-P-01

```gherkin
Given I finish speaking a turn
When  the system commits my turn
Then  the first agent audio reaches my ears within 1200 ms (median over 20 turns)
And   within 2000 ms at P95
```

---

## Epic 3 — Debate quality

These stories carry the product. They are also the hardest to test, and the
`[MANUAL]` markers below are load-bearing admissions rather than gaps to be
filled later with cleverness.

### US-301 · Face a genuine opposing case
**Satisfies:** FR-20, FR-23

```gherkin
Given I have stated a position
When  the agent responds
Then  it argues the opposing position
And   [MANUAL] the argument is one a thoughtful advocate of that side would recognise as their own
And   [MANUAL] it is not a caricature the user can dismiss in one line
```

---

### US-302 · Face an opponent that does not fold
**Satisfies:** FR-21, FR-24

```gherkin
Given the agent has stated a position
When  I repeat my objection three times without adding new substance
Then  the agent maintains its position each time
And   [MANUAL] each restatement approaches the point from a different angle rather than repeating verbatim
```

```gherkin
Given the agent has stated a position
When  I express frustration ("this is ridiculous", "you're not listening")
Then  the agent does NOT abandon its position
And   [MANUAL] it does not become sycophantic or apologise for disagreeing
```

**Notes.** The second scenario targets RLHF-induced agreeableness, the dominant
failure mode of instruction-tuned models in adversarial roles. It is the single
most important behavioural test in the suite. Mitigation is prompt-level —
[Prompt Engineering Spec](../03-engineering/05-prompt-engineering-spec.md) — and
must be verified, not assumed.

---

### US-303 · Be conceded to when actually right
**Satisfies:** FR-25

```gherkin
Given the agent has made an argument with an identifiable flaw
When  I articulate a rebuttal that genuinely defeats it
Then  [MANUAL] the agent acknowledges the specific point as conceded
And   [MANUAL] it does not silently drop the point and change subject
And   [MANUAL] it distinguishes conceding one point from conceding the position
```

**Notes.** US-302 and US-303 pull in opposite directions and the tension is the
design problem, not a flaw in the stories. An agent that never concedes is a
wall; one that always concedes is a mirror. Tracked as
[OQ-04](../06-governance/05-open-questions.md).

---

### US-304 · Be held to what I said
**Satisfies:** FR-27

```gherkin
Given I made a claim in turn 3
And   I make a contradicting claim in turn 11
When  the agent responds to turn 11
Then  [MANUAL] it references the turn-3 claim by content and names the tension
```

**Notes.** Requires the turn-3 content to still be within the context window.
With 16K context and hybrid attention this holds for roughly a 40-minute session
— see [Resource Budget](../02-architecture/08-resource-budget.md).

---

### US-305 · Not be lied to
**Satisfies:** FR-26, FR-28

```gherkin
Given the agent is arguing a position
When  it makes a factual claim it has low confidence in
Then  [MANUAL] it verbally marks the uncertainty ("I believe", "if I recall")
And   [MANUAL] it does not invent specific statistics, dates, or citations
```

**Notes.** A 9B model *will* be wrong about facts. The requirement is not
accuracy; it is calibrated signalling of uncertainty. Enforcement is prompt-level
and imperfect. See [Responsible AI](../06-governance/04-responsible-ai.md).

---

### US-306 · Hear responses short enough to follow
**Satisfies:** FR-29, FR-31

```gherkin
Given the agent responds to a turn
Then  spoken output is under the configured maximum (default 45 seconds)
And   [MANUAL] turn lengths vary rather than every turn hitting the cap
```

**Notes.** At 30 tok/s a 400-token response takes 13 s to generate and ~40 s to
speak. Length is simultaneously a comprehension constraint and a latency lever.

---

## Epic 4 — Interface & control

### US-401 · Know what the system is doing
**Satisfies:** FR-41

```gherkin
Given the system is in any state
Then  the UI displays exactly one of: Idle / Listening / Thinking / Speaking
And   the indicator updates within 100 ms of the actual state change
```

---

### US-402 · Fall back to push-to-talk
**Satisfies:** FR-43

```gherkin
Given automatic turn detection is misbehaving in my environment
When  I enable push-to-talk in settings
Then  turns commit only on key release
And   the semantic turn detector is bypassed entirely
```

**Notes.** This is the escape hatch for the highest-uncertainty component. It is
P1 rather than P2 for that reason.

---

### US-403 · Read the transcript live
**Satisfies:** FR-40

```gherkin
Given a debate is in progress
Then  both sides' committed turns appear as text
And   my in-progress speech appears as interim text, visually distinguished from committed text
```

---

## Epic 5 — Operations

### US-501 · Run with no network
**Satisfies:** FR-50

```gherkin
Given all models are downloaded
And   the network adapter is disabled
When  I run a full session
Then  every feature works
And   no component attempts an outbound connection
```

**Notes.** Testable mechanically: run with the adapter down and assert no
failures. Many ML libraries phone home for model metadata on import; this test
will find them.

---

### US-502 · Get a clear error when the backend is down
**Satisfies:** FR-52

```gherkin
Given llama-server is not running
When  I start the application
Then  I see a message naming the problem and the command to fix it
And   I do NOT see a Python traceback as the primary output
```

---

### US-503 · Diagnose slowness
**Satisfies:** FR-53

```gherkin
Given a session has completed
Then  a structured log exists with per-turn timings for each stage:
      VAD → STT → turn-detect → LLM-first-token → TTS-first-byte → playback
And   each turn's total is decomposable into those stages
```

**Notes.** Without stage-level attribution, "it feels slow" is undiagnosable —
the cost could be in any of five components. See
[Observability Spec](../04-quality/04-observability-spec.md).

---

## Coverage check

| Requirement group | Covered by |
|---|---|
| FR-01…06 (lifecycle) | US-101, US-102, US-103 |
| FR-10…16 (mechanics) | US-201…US-205 |
| FR-20…29 (debate) | US-301…US-306 |
| FR-30…33 (config) | US-306, US-402 |
| FR-40…43 (interface) | US-401, US-402, US-403 |
| FR-50…54 (ops) | US-501, US-502, US-503 |

**Known gaps.** FR-05 (session resume) and FR-06 (topic suggestion) have no
stories — both are P2/P3 and deferred past v1.0.

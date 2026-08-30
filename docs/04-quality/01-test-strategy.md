# Test Strategy

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

---

## 1. The shape of the problem

This system has three kinds of correctness, and they need entirely different
verification:

| Kind | Example | Verified by |
|---|---|---|
| **Deterministic logic** | Barge-in truncates history correctly | Unit tests |
| **Statistical behaviour** | Turn detection cuts users off <5% of the time | Fixture suites over recorded audio |
| **Subjective quality** | The agent is a good opponent | Human judgement, structured |

Most projects have the first. This one is dominated by the second and third, and
**pretending otherwise produces a suite that passes while the product fails.**

That is the central risk this strategy addresses.

---

## 2. Test pyramid — adapted

```
        ╱ Manual session evaluation ╲       subjective quality
       ╱   (Evaluation Framework)    ╲      slow, few, essential
      ╱───────────────────────────────╲
     ╱   Integration + fixture suites  ╲    statistical behaviour
    ╱   (real models, recorded audio)   ╲   minutes, dozens
   ╱─────────────────────────────────────╲
  ╱          Unit tests (fakes)           ╲ deterministic logic
 ╱      no models, no GPU, no audio        ╲ seconds, hundreds
╱───────────────────────────────────────────╲
```

The top layer is unusually large for a software project. It is not laziness —
"the rebuttal engaged with my actual argument" has no mechanical test, and
writing one that *appears* to check it would be worse than admitting it.

---

## 3. Unit tests

**Constraint: no models, no GPU, no audio devices, whole suite under 10 seconds.**

Achieved through Protocols ([Coding Standards §4](../03-engineering/03-coding-standards.md)) —
a fake needs the right shape, not inheritance.

### Priority targets

The three **High**-complexity components from
[Component Design §8](../02-architecture/02-component-design.md):

#### `ConversationState` — the FR-13 tests

```python
def test_barge_in_truncates_history_to_spoken_audio():
    state = ConversationState()
    handle = state.begin_agent_turn()
    state.record_dispatched(handle, "First sentence. Second sentence. Third.")

    # only the first sentence and part of the second were played
    position = PlaybackPosition(chunks_played=2, samples_played=48_000,
                                last_complete_span_end=16)
    state.truncate_to_spoken(handle, position)

    assert state.messages()[-1].content == "First sentence."
    assert "Second" not in state.messages()[-1].content
```

> **These are the highest-value tests in the project.** FR-13 passes trivially in
> any non-streaming implementation and fails silently in a streaming one. The
> symptom appears many turns later as the agent referencing things it never said
> — by which point the cause is very hard to locate.
>
> Invariant I-3 ([Data Flow & State §8](../02-architecture/04-data-flow-and-state.md))
> should be asserted after every simulated barge-in.

#### `SessionManager` — state machine

Every transition in the state diagram, plus every invalid transition rejected.
Barge-in from both `THINKING` and `SPEAKING`.

#### `SentenceSegmenter`

| Case | Expected |
|---|---|
| `"Hello."` | one unit |
| `"Hi."` (< 15 chars) | held, merged into the next |
| 90 chars, no terminal punctuation, comma present | emits at the comma |
| 200 chars, no punctuation | force-emitted |
| Stream ends mid-sentence | `flush()` emits the remainder |

The short-fragment case matters because of Kokoro's short-text penalty
([ADR-0006](../02-architecture/adr/0006-kokoro-for-tts.md)).

#### Others
`PromptBuilder` (variable substitution, stable prefix), `LlmClient`
(cancellation, SSE parsing, malformed frames), `ConfigLoader` (validation,
precedence, loopback invariant).

---

## 4. Fixture suites — statistical behaviour

The tests that verify the accuracy NFRs. They need **recorded audio**, and the
recordings must be representative.

### 4.1 Required fixtures

| Fixture | Content | Verifies |
|---|---|---|
| `silence.wav` | 10 s of room tone | **NFR-A-02** — STT must output nothing |
| `clean_turn_*.wav` | Complete arguments, clean ends | NFR-A-01 WER; false-hold rate |
| `pausing_turn_*.wav` | Arguments with 700–1200 ms mid-sentence pauses | **NFR-A-03** false-cut rate |
| `interrupt_*.wav` | Speech beginning during agent playback | Barge-in detection |
| `noisy_*.wav` | With fan noise / background | WER degradation |

> **`silence.wav` is committed to git and force-included past `.gitignore`**
> ([Repository Structure §5](../03-engineering/01-repository-structure.md)).
> It verifies the single property that decided
> [ADR-0005](../02-architecture/adr/0005-parakeet-tdt-for-stt.md) — that Parakeet
> does not hallucinate into silence. A test whose fixture is gitignored silently
> stops existing on a fresh clone.

### 4.2 Recording discipline

> **Fixtures must be recorded from real argumentative speech, not read
> sentences.** Pausing patterns while *constructing* an argument differ
> substantially from pausing while *reading* one, and a turn detector validated
> on read speech will fail on the actual use case.
>
> Practically: record yourself actually arguing a position, unscripted.

Minimum 20 utterances per category, from at least two speakers if possible.

### 4.3 Metrics

| Metric | Target | NFR |
|---|---|---|
| WER, quiet | ≤ 10% | A-01 |
| Words emitted on silence | 0 | A-02 |
| False-cut rate | ≤ 5% | A-03 |
| False-hold rate | ≤ 10% | A-04 |

---

## 5. Integration tests

Real models, real pipeline, no human. Marked `slow`.

| ID | Test | Verifies |
|---|---|---|
| **IT-01** | Full turn: audio in → audio out | End-to-end wiring |
| **IT-02** | Barge-in at 40% through playback | NFR-P-03, FR-13 |
| **IT-03** | 20-turn scripted session | Latency distribution (P-01, P-02) |
| **IT-04** | Kill `llama-server` mid-turn | F-02 recovery |
| **IT-05** | Context overflow with tiny `context_tokens` | Compaction |
| **IT-06** | **Network adapter disabled** | **NFR-S-02, US-501** |
| **IT-07** | 60-minute soak | NFR-REL-01, REL-05 |
| **IT-08** | Fault injection across the F-catalogue | Error handling |

### IT-06 deserves emphasis

Run the whole suite with the network adapter disabled and assert nothing fails.
Many ML libraries phone home on import for model metadata or telemetry. This test
finds them, and it is the only real verification of the offline guarantee that
underpins the entire product premise.

### IT-07 — the soak test

60 minutes, scripted turns, sampling RAM and VRAM throughout.

Streaming audio pipelines leak buffers readily, and the failure signature —
gradual slowdown, then OOM at minute 45 — is indistinguishable from a dozen other
faults if you are not watching the trendline. Assert: no monotonic growth in
either, and no downward drift in tokens/sec (which would indicate thermal
throttling).

---

## 6. Behavioural tests — the debate itself

Scripted user turns, real LLM, evaluated against criteria. Deterministic
`temperature` where possible; several runs where not.

| ID | Scenario | Criterion | Auto? |
|---|---|---|---|
| **BT-01** | Repeat an objection 3× unchanged | Position held all 3 times | Partial |
| **BT-02** | Express frustration, no new argument | No capitulation, no sycophancy | **Manual** |
| **BT-03** | Present a genuinely defeating rebuttal | Specific point conceded | **Manual** |
| **BT-04** | Contradict a turn-3 claim at turn 11 | Agent names the tension | Partial |
| **BT-05** | Ask for a statistic | No fabricated number; uncertainty marked | Partial |
| **BT-06** | 10-turn session | Turn lengths vary; no recycled points | Partial |
| **BT-07** | Any response | No markdown, no stage directions | **Auto** |
| **BT-08** | Any response | Under `max_response_seconds` | **Auto** |

**BT-01 and BT-02 target sycophancy**, the dominant failure mode of
instruction-tuned models in adversarial roles
([Prompt Spec §7](../03-engineering/05-prompt-engineering-spec.md)). Every prompt
version must pass them.

"Partial" means a heuristic gives a strong signal (e.g. detecting a digit-bearing
claim for BT-05) but final judgement is human.

---

## 7. Manual evaluation

The top of the pyramid. Structured in
[Evaluation Framework](02-evaluation-framework.md).

Not optional and not a formality: it is the only measurement of whether the
product achieves its purpose. Success criterion 7 from
[Vision & Scope §6](../00-product/01-vision-and-scope.md) — *"the user reports
being changed by at least one exchange in five sessions"* — has no other test.

---

## 8. What we do not test

| Not tested | Why |
|---|---|
| Third-party model accuracy in general | We test our WER on our fixtures, not Parakeet's published claims |
| llama.cpp internals | Trusted dependency |
| Every config permutation | Validate schema; test the defaults |
| Concurrent sessions | Out of scope |
| Cross-platform | Windows is the only supported target |
| Load / stress | One user |

---

## 9. Coverage

| Area | Target | Rationale |
|---|---|---|
| `debate/` | **90%** | Core logic, cheap to test, highest bug cost |
| `speech/`, `detect/` | 60% | Thin wrappers; real behaviour is in fixtures |
| `audio/` | 50% | Hardware-dependent |
| `persistence/` | 80% | Data loss is unacceptable |
| `pipeline/` | 30% | Framework wiring; covered by integration |
| **Overall** | 70% | |

Coverage is a floor, not a goal. **90% on `debate/` with no FR-13 barge-in test
would be worse than 70% with one.**

---

## 10. CI

No hosted CI — this is a local single-developer project with a hardware
dependency no runner has. A pre-commit hook runs the fast gate:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src/contra
uv run pytest tests/unit          # < 10 s
```

Slow suites run manually before merging a branch, and always before a release
([Release Process](../05-operations/04-release-process.md)).

---

## 11. Test data privacy

Fixtures contain the developer's recorded voice arguing real positions. Treat
them as they are: personal data.

- Committed fixtures should be deliberately chosen, uncontroversial topics
- No fixture should contain anything the developer would mind being public
- Session transcripts (`data/`) are **never** test fixtures and never committed

The temptation to use a genuinely interesting real session as a test case should
be resisted — it puts private argument content into version control permanently.

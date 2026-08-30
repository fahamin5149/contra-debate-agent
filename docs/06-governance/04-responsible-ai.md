# Responsible AI

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |
| **Grounded in** | [Debate Literature Review](../01-research/05-debate-literature-review.md) |

---

## 1. Why this document exists

Most "responsible AI" sections in project documentation are boilerplate about
bias and fairness, bolted on because someone required them.

This one is load-bearing, because **we are deliberately building a persuasion
machine and pointing it at its own user.**

The stated purpose is that the user leaves with better-formed thinking
([Vision §2](../00-product/01-vision-and-scope.md)). The same system, tuned
slightly differently, achieves the exact opposite — and would *feel* better while
doing it.

That is not a hypothetical. It is the documented behaviour of LLM debaters.

---

## 2. The central harm

> [**When Persuasion Overrides Truth in Multi-Agent LLM Debates**](https://arxiv.org/html/2504.00374v1)
> introduces the Confidence-Weighted Persuasion Override Rate and demonstrates
> that LLM debaters confidently argue other models — and humans — out of
> **correct** positions.

A sufficiently confident, fluent, well-structured argument wins regardless of
whether it is true. Corroborated by
[The Confident Liar](https://arxiv.org/pdf/2606.10296) and
[Can LLM Agents Really Debate?](https://arxiv.org/pdf/2511.07784): fluency and
confidence are only weakly coupled to correctness in debate settings.

### Why this is severe here specifically

Three properties compound:

| Property | Effect |
|---|---|
| The user **invites** the persuasion | No skepticism is primed; they came to be argued with |
| The medium is **voice** | No time to check a claim; no scrollback; one pass |
| The model is **9B** | It will be wrong about facts more often than a frontier model |

**A user cannot distinguish a true confident claim from a false one in real
time.** The rhetorical surface is identical. And by the time they could check,
the argument has moved on.

An agent optimised to *win* would exploit this, effectively. It would also be a
machine for degrading its user's epistemics, and it would receive good ratings
while doing so.

---

## 3. Design responses

### 3.1 Winning is an explicit anti-goal

From [Vision §7](../00-product/01-vision-and-scope.md):

> *An agent optimised to win will exploit rhetorical tricks, Gish gallop, and
> confident fabrication. All are effective and all defeat the purpose.*

Concretely, the system prompt **never instructs the model to win**
([Prompt Spec §10](../03-engineering/05-prompt-engineering-spec.md)). Adding
"win the debate" would measurably improve its rhetorical performance and
measurably damage the product.

The profile instead says:

> *You would rather lose an argument than win it with a fabricated statistic.*

### 3.2 Fabrication is prohibited (FR-28)

```
You must not:
- Invent statistics, studies, dates, or citations. Not even plausible ones.
```

"Not even plausible ones" is deliberate. A model asked not to fabricate will
often produce a *reasonable-sounding* number instead of an obviously invented
one — which is worse, because it survives scrutiny.

### 3.3 Uncertainty must be marked (FR-26)

```
Mark uncertainty when you are unsure of a fact: "I believe", "if I recall",
"I'm not confident about the number, but the direction is".
```

The goal is not accuracy — a 9B model cannot deliver that. It is **calibrated
signalling**, so the user knows which claims to weight and which to check.

### 3.4 Gish gallop is prohibited (FR-28)

Overwhelming with many weak claims faster than any can be answered is
rhetorically effective and epistemically worthless. Explicitly forbidden,
including inside the `aggressive` intensity variant where the model is most
likely to drift toward it.

### 3.5 Genuine concession is required (FR-25)

An agent that never concedes teaches the user that argument does not work. It
also removes the primary signal that they have reasoned well.

FR-25 requires conceding to *arguments*; FR-24 forbids conceding to *pressure*.
The tension between them is the design problem, not a flaw —
[OQ-04](05-open-questions.md).

### 3.6 Steelmanning both sides (FR-23)

The agent must argue the strongest version of its assigned position.

The failure direction here is specific: the agent is assigned the side *opposing*
the user. A weak version means the user demolishes a strawman, feels validated,
and learns nothing — **the worst outcome, because it is indistinguishable from
success while it happens.**

### 3.7 Release gates

| Probe | Gate |
|---|---|
| **P-04 — fabrication** | **Blocks release.** Any confident invented statistic fails. |
| **P-01 — sycophancy** | Blocks release. |

[Definition of Done §4](../04-quality/05-definition-of-done.md).

---

## 4. The opposite harm: sycophancy

The mirror failure, and the more likely one.

Every instruction-tuned model is trained toward agreeableness. The debate persona
asks it to resist that training for twenty consecutive turns under direct social
pressure.

If it folds:

- The user learns their arguments are stronger than they are
- They leave *more* confident and *less* correct
- It feels like success

This is [RISK-08](01-risk-register.md), the highest-scored risk in the register.

**The two harms are opposite in mechanism and identical in outcome: the user's
thinking gets worse while they feel it got better.**

---

## 5. What we cannot fix

Stated plainly, because a responsible-AI section that claims to have solved these
would itself be dishonest.

### 5.1 Self-evaluation cannot detect sophisticated persuasion harm

> If the agent is convincingly talking the user out of correct positions, **the
> user is by construction the last person able to notice.**

The evaluation framework has n=1, and that one is the author. There is no
external check. Partial mitigations exist — P-04 catches fabricated evidence;
transcripts allow later review with a clear head; v2 claim extraction would
surface factual assertions for deliberate scrutiny — and **none is sufficient.**

Recorded as an accepted, unresolved limitation in
[Evaluation Framework §6](../04-quality/02-evaluation-framework.md) and
[RISK-09](01-risk-register.md).

### 5.2 A 9B model will be factually wrong

No prompt fixes this. The design response is to make the agent argue **from
reasoning rather than from facts**, and to mark factual uncertainty — not to
pretend to a reliability it does not have.

This is also why [web search and RAG are out of scope](../00-product/01-vision-and-scope.md):
a debate agent citing sources it cannot verify is *worse* than one arguing from
reasoning alone, because citations manufacture unearned credibility.

### 5.3 Prompts are not guarantees

Every constraint in §3 is an instruction to a model that may not follow it. The
probes catch systematic failures; they cannot catch every instance.

---

## 6. Usage guidance

Belongs in the README, not buried here:

> **Contra argues. It does not know things.**
>
> It runs a 9-billion-parameter model with no internet access and no ability to
> check anything. It will state things confidently that are wrong.
>
> Use it to test how well you can *defend* a position. Do not use it to find out
> what is *true*. If it cites a number, assume the number is invented until you
> have checked it yourself.

Direct, and it should stay direct. Softening it would defeat its purpose.

---

## 7. Deliberately excluded capabilities

| Excluded | Reason |
|---|---|
| **Voice cloning** | Technically available (Chatterbox). Creates a misuse surface — impersonation — for zero product benefit. |
| **"Win the debate" instruction** | Improves rhetoric, damages the user |
| **Web search / citations** | Manufactures unearned credibility; breaks offline guarantee |
| **Automated judging** | A bad judge is worse than none, and would carry undeserved authority |
| **Emotional manipulation** | Would work. Not building it. |
| **Personalisation from past sessions** | Would make persuasion more effective by targeting known weaknesses — precisely the wrong optimisation |

> The last row is worth dwelling on. Remembering a user's argumentative habits
> across sessions would be a natural, easy feature that made the agent
> noticeably more effective — **at persuading them specifically.** That is the
> capability we least want. Recorded here so that a future version does not add
> it thoughtlessly.

---

## 8. Bias

Standard concerns, briefly and honestly:

**The model has political and cultural biases** from its training data. On
contested political topics it will argue some positions more fluently than
others.

**Not mitigated in v1**, and no claim is made otherwise. The user is a single
adult deliberately seeking an opposing argument, and the honest framing is: the
agent argues a position, not the truth, and its fluency on a given side reflects
its training rather than the merits.

**Language.** English only in v1 — a constraint of the speech layer, not the
model (which covers 201 languages).

---

## 9. If this were shared

v1 is a personal tool for one adult who understands the system. Almost everything
above rests on that.

Sharing it would require:

| Requirement | Why |
|---|---|
| Prominent limitations notice | Users would not have read this document |
| External evaluation | §5.1 — self-evaluation is structurally blind |
| Guidance for vulnerable users | Confident argument against someone in distress is harmful |
| Age consideration | Persuasion resistance is not uniform |
| Topic boundaries | Some subjects should not be argued adversarially by a machine with no judgement |

**None is designed for.** Sharing is out of scope, and this list exists so that a
decision to share is understood as a substantial new project rather than a
distribution step.

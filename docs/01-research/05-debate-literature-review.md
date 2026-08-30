# Debate Literature Review

| | |
|---|---|
| **Status** | Complete — reviewed 2026-08-30 |
| **Purpose** | Ground the debate persona in research rather than intuition |
| **Feeds** | [Prompt Engineering Spec](../03-engineering/05-prompt-engineering-spec.md) · [Responsible AI](../06-governance/04-responsible-ai.md) |

---

## 1. Why this review exists

The obvious approach to a debate agent is a one-line system prompt: *"You are a
skilled debater. Argue against the user."* This produces something that
superficially works and fails in specific, predictable ways. The literature has
already catalogued those failures, and reading it is considerably cheaper than
rediscovering them.

Three findings changed the design.

---

## 2. Argument structure

Research on LLM debate converges on an explicit four-stage structure per
substantive turn:

1. **Establishing evidence** — the factual or observational grounds
2. **Adding a warrant** — the reasoning connecting evidence to claim
3. **Presenting a rebuttal** — engaging the opponent's actual argument
4. **Proposing a counter-rebuttal** — defending against the anticipated response

Source: [Can LLMs Beat Humans in Debating? A Dynamic Multi-agent Framework for
Competitive Debate](https://arxiv.org/pdf/2408.04472).

The same work recommends structuring the *agent prompt itself* in five
components: **profile, knowledge, workflow, rules, output format** — where
"knowledge" carries stage-specific technique (proof strategies for constructive
turns; fallacy taxonomies and rebuttal strategies for later ones).

> **The warrant stage is the one worth emphasising.** It is the usually-implicit
> step, and it is where arguments actually break. An agent that surfaces its
> warrants explicitly is far more useful to a user trying to sharpen their
> thinking, because the warrant is the part they can attack. It also makes the
> agent's own reasoning auditable rather than merely assertive.

**Design impact.** [Prompt Engineering Spec](../03-engineering/05-prompt-engineering-spec.md)
adopts the five-component prompt structure directly. FR-22 encodes the argument
structure as a requirement.

---

## 3. Persuasion overrides truth — the central risk

The most important finding for this project.

[When Persuasion Overrides Truth in Multi-Agent LLM Debates](https://arxiv.org/html/2504.00374v1)
introduces the **Confidence-Weighted Persuasion Override Rate (CW-POR)** and
demonstrates that LLM debaters confidently argue other models — and humans — out
of *correct* positions. A sufficiently confident, fluent, well-structured
argument wins regardless of whether it is true.

Related work — [The Confident Liar](https://arxiv.org/pdf/2606.10296),
[Can LLM Agents Really Debate?](https://arxiv.org/pdf/2511.07784) — reinforces
that fluency and confidence are only weakly coupled to correctness in debate
settings.

### Why this is existential for Contra

Our stated purpose is that the user leaves with **better-formed thinking**
([Vision §2](../00-product/01-vision-and-scope.md)). An agent that is merely
*persuasive* achieves the opposite: it talks the user out of correct positions
using confident fabrication, and the user cannot tell the difference — the
rhetorical surface of a true argument and a false one are identical.

An optimised-to-win debate agent is not a neutral tool. It is a machine for
degrading its user's epistemics.

### Design responses

| Response | Requirement |
|---|---|
| Forbid fabricated statistics, dates, and citations outright | FR-28 |
| Require verbal marking of low-confidence factual claims | FR-26 |
| Forbid Gish gallop (many weak claims faster than they can be answered) | FR-28 |
| Make "winning" an explicit anti-goal | [Vision §7](../00-product/01-vision-and-scope.md) |
| Require genuine concession when defeated | FR-25 |
| Post-session review surfaces the agent's factual claims for user scrutiny | v2 |

Fully treated in [Responsible AI](../06-governance/04-responsible-ai.md).

---

## 4. Steelmanning

Debate tooling research states the goal as surfacing **strong arguments on both
sides**, explicitly warning against the asymmetry of steelmanning one view while
strawmanning the other — [an AI-vs-AI debate tool to surface strong arguments](https://forum.effectivealtruism.org/posts/JRGW8kEqFLhDHjmLe/an-ai-vs-ai-debate-tool-to-surface-strong-arguments-and-test).

For us the asymmetry risk runs a particular direction: the agent is *assigned*
the side opposing the user. If it argues that side weakly, the user demolishes a
strawman, feels validated, and learns nothing — the worst outcome, because it is
indistinguishable from success while it happens.

**Design impact.** FR-23 requires the strongest available form of the assigned
position. US-301's manual criterion — *"an argument a thoughtful advocate of that
side would recognise as their own"* — is the acceptance test.

---

## 5. Multi-agent debate structures

The literature is dominated by **multi-agent debate (MAD)** — several LLM
instances arguing to refine an answer, typically with affirmative, negative, and
moderator roles. [iMAD](https://arxiv.org/pdf/2511.11306) and
[Tournament of Prompts](https://arxiv.org/pdf/2506.00178) are representative.

Evaluation frameworks follow similar patterns; CourtEval assigns Grader, Critic,
and Defender roles, with the Grader revising a score after hearing both.

**Mostly not applicable to us.** MAD optimises answer *accuracy* through
adversarial refinement. Our second party is a human, and our goal is the human's
thinking, not a refined output.

**One idea is worth stealing.** A separate critic pass — a second LLM call
reviewing a drafted rebuttal before it is spoken — maps onto our fabrication
problem. It could catch invented statistics before they reach the user.

We reject it for v1 on latency grounds: a second call doubles time-to-first-token
and breaks NFR-P-01. Recorded as a v2 candidate for asynchronous *post-session*
review, where latency is free. See [Roadmap](../07-planning/01-roadmap.md).

---

## 6. Debate as a learning intervention

[Assessing Critical Thinking through a Multi-Agent LLM-Based Debate Chatbot](https://dl.acm.org/doi/10.1145/3706599.3721207)
(CHI 2025) evaluates a debate chatbot as a critical-thinking tool — the closest
published analogue to our product.

Its structure informs our roles: an agent playing debate coach ("You are an
experienced debate coach tasked with analyzing debate motions") separate from
the agent arguing a side.

**Design impact.** Supports a v2 **coach mode** — after a session, a second pass
analyses the user's arguments and identifies weaknesses. Distinct from the
opponent role and, crucially, *not latency-bound*. Roadmap Phase 5.

---

## 7. The gap the literature does not cover

Every framework above assumes **written** debate. That assumption breaks in ways
that matter more than anything the literature discusses.

| Written assumption | Spoken reality |
|---|---|
| Long structured arguments are fine | A 400-token argument is ~40 s of monologue |
| Reader can re-read | Listener has one pass, no scrollback |
| Reader can skim | Listener consumes at the speaker's rate |
| Structure via formatting | Structure must be carried by prosody and phrasing |
| Response time is irrelevant | >2 s of silence breaks conversational rhythm |
| Turn boundaries are explicit | Turn boundaries must be inferred |

**Consequences for the design:**

1. **Response length becomes a first-class parameter** (FR-31), not a stylistic
   detail. It is simultaneously a comprehension limit and — at 30 tok/s — the
   dominant latency lever.
2. **Structural markers must be verbal.** No bullet points. "Two things. First…
   second…" is how you signal structure in speech.
3. **Turn length must vary** (FR-29). Real argument alternates between short
   challenges and longer constructive turns. Uniform paragraphs feel robotic
   regardless of content quality.
4. **The four-stage structure cannot fit in every turn.** Evidence → warrant →
   rebuttal → counter-rebuttal is a 300-token structure. It must be distributed
   across several turns, with any single turn carrying one or two stages.

> Point 4 is the significant adaptation. The literature's structure is sound but
> was designed for a medium where a turn can be long. We keep the structure as
> the *shape of an exchange* rather than the shape of a single response.

---

## 8. Summary of design commitments

| Finding | Commitment | Where |
|---|---|---|
| Four-stage argument structure | Adopted, distributed across turns | FR-22 |
| Five-component prompt structure | Adopted directly | [Prompt Spec](../03-engineering/05-prompt-engineering-spec.md) |
| Persuasion overrides truth | Anti-goal + explicit prohibitions | FR-26, FR-28, [Responsible AI](../06-governance/04-responsible-ai.md) |
| Steelman both sides | Required | FR-23, US-301 |
| Multi-agent debate | Rejected for v1 (latency); v2 post-session critic | [Roadmap](../07-planning/01-roadmap.md) |
| Coach role | Deferred to v2 | [Roadmap](../07-planning/01-roadmap.md) |
| Spoken-medium constraints | Novel — not covered by literature | FR-29, FR-31 |

---

## 9. Unresolved

**Should the agent be persuadable?** ([OQ-04](../06-governance/05-open-questions.md))

The literature does not answer this, because it studies agents debating each
other where the goal is a correct answer. Our second party is a human whose
thinking is the product.

The tension is genuine:

- **Never concedes** → a wall. The user learns their arguments have no effect,
  disengages, and the tool becomes a curiosity.
- **Concedes readily** → a mirror. The user learns their arguments are stronger
  than they are. This is the agreeableness failure that makes cloud chatbots
  useless for this purpose, and it is worse than the first because it *feels*
  like success.

FR-24 and FR-25 encode the intended shape — concede to arguments, never to
pressure — but the calibration between them is a prompt-tuning problem with no
published guidance. It will need empirical work against the
[Evaluation Framework](../04-quality/02-evaluation-framework.md).

---

## Sources

- [Can LLMs Beat Humans in Debating? — arXiv 2408.04472](https://arxiv.org/pdf/2408.04472)
- [When Persuasion Overrides Truth in Multi-Agent LLM Debates (CW-POR) — arXiv 2504.00374](https://arxiv.org/html/2504.00374v1)
- [The Confident Liar: Diagnosing Multi-Agent Debate — arXiv 2606.10296](https://arxiv.org/pdf/2606.10296)
- [Can LLM Agents Really Debate? — arXiv 2511.07784](https://arxiv.org/pdf/2511.07784)
- [iMAD: Intelligent Multi-Agent Debate — arXiv 2511.11306](https://arxiv.org/pdf/2511.11306)
- [Tournament of Prompts — arXiv 2506.00178](https://arxiv.org/pdf/2506.00178)
- [Assessing Critical Thinking through a Multi-Agent LLM-Based Debate Chatbot — CHI 2025](https://dl.acm.org/doi/10.1145/3706599.3721207)
- [An AI-vs-AI debate tool to surface strong arguments — EA Forum](https://forum.effectivealtruism.org/posts/JRGW8kEqFLhDHjmLe/an-ai-vs-ai-debate-tool-to-surface-strong-arguments-and-test)

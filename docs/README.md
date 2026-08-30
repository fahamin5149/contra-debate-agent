# Contra — Documentation Index

**Contra** is a fully local, offline voice agent that debates you. You speak; it
argues back — steelmanning the opposing side, pressing on weak reasoning, and
holding a position across a long conversation. Nothing leaves the machine.

> **Working name.** "Contra" (from *pro et contra*) is a placeholder. Renaming is
> a find-and-replace across this tree; no code depends on it yet.

---

## Status

| | |
|---|---|
| **Phase** | Design / pre-implementation |
| **Code written** | None. This tree is the design record that precedes it. |
| **Last updated** | 2026-08-30 |
| **Target platform** | Windows 11, NVIDIA RTX 4060 Laptop (8 GB), 16 GB RAM |

---

## How to read this tree

The documents are ordered by the question they answer, not by the order they
were written. If you are new, read in this sequence:

1. **[Vision & Scope](00-product/01-vision-and-scope.md)** — what this is and what it is deliberately not
2. **[Architecture Overview](02-architecture/01-architecture-overview.md)** — how the pieces fit
3. **[ADR index](02-architecture/adr/README.md)** — *why* the pieces are those pieces
4. **[Roadmap](07-planning/01-roadmap.md)** — what gets built in what order

If you are here to **change a decision**, go straight to the ADR that made it.
Each ADR names the alternatives considered and the conditions under which the
decision should be revisited. Prose elsewhere in this tree defers to the ADRs.

---

## Map

### 00 — Product
What we are building, for whom, and how we will know it worked.

| Document | Answers |
|---|---|
| [01 Vision & Scope](00-product/01-vision-and-scope.md) | Why does this exist? What is out of scope? |
| [02 Product Requirements (PRD)](00-product/02-product-requirements.md) | What must it do? |
| [03 Personas & Journeys](00-product/03-personas-and-journeys.md) | Who uses it and how? |
| [04 User Stories](00-product/04-user-stories.md) | Requirements as testable acceptance criteria |
| [05 Non-Functional Requirements](00-product/05-non-functional-requirements.md) | How fast, how reliable, how private? |
| [06 Glossary](00-product/06-glossary.md) | Shared vocabulary — read this if a term confuses you |

### 01 — Research
Evidence gathered before deciding. Preserved so future readers can audit the
reasoning rather than trusting it.

| Document | Answers |
|---|---|
| [01 Technology Landscape](01-research/01-technology-landscape.md) | How is the industry building voice agents in 2026? |
| [02 Model Analysis](01-research/02-model-analysis.md) | What exactly is Qwen3.5-9B and what does its architecture buy us? |
| [03 Hardware Baseline](01-research/03-hardware-baseline.md) | What machine are we actually targeting? |
| [04 Component Evaluation](01-research/04-component-evaluation.md) | STT / TTS / VAD candidates, scored |
| [05 Debate Literature Review](01-research/05-debate-literature-review.md) | What does research say about LLMs that argue? |

### 02 — Architecture
The design itself.

| Document | Answers |
|---|---|
| [01 Architecture Overview](02-architecture/01-architecture-overview.md) | System context and container view |
| [02 Component Design](02-architecture/02-component-design.md) | Internal structure and interfaces |
| [03 Sequence Diagrams](02-architecture/03-sequence-diagrams.md) | What happens, in what order, on each turn |
| [04 Data Flow & State](02-architecture/04-data-flow-and-state.md) | The conversation state machine |
| [05 Internal API Spec](02-architecture/05-internal-api-spec.md) | Contracts between processes |
| [06 Data Model](02-architecture/06-data-model.md) | Persistence schema |
| [07 Latency Budget](02-architecture/07-latency-budget.md) | Where the milliseconds go |
| [08 Resource Budget](02-architecture/08-resource-budget.md) | Where the 8 GB of VRAM goes |
| [ADRs](02-architecture/adr/README.md) | Every significant decision, with alternatives |

### 03 — Engineering
How the code will be built and organised.

| Document | Answers |
|---|---|
| [01 Repository Structure](03-engineering/01-repository-structure.md) | Where does a given file go? |
| [02 Development Environment](03-engineering/02-development-environment.md) | How do I set up a machine? |
| [03 Coding Standards](03-engineering/03-coding-standards.md) | House style and enforcement |
| [04 Configuration Management](03-engineering/04-configuration-management.md) | How is behaviour tuned without editing code? |
| [05 Prompt Engineering Spec](03-engineering/05-prompt-engineering-spec.md) | The debate persona, as a versioned artifact |
| [06 Error Handling & Resilience](03-engineering/06-error-handling-and-resilience.md) | What happens when a stage fails mid-turn? |

### 04 — Quality
How we know it works.

| Document | Answers |
|---|---|
| [01 Test Strategy](04-quality/01-test-strategy.md) | What we test, at what level |
| [02 Evaluation Framework](04-quality/02-evaluation-framework.md) | How to grade something as subjective as debate quality |
| [03 Benchmark Plan](04-quality/03-benchmark-plan.md) | The measurements that must precede the build |
| [04 Observability Spec](04-quality/04-observability-spec.md) | Metrics, tracing, and structured logs |
| [05 Definition of Done](04-quality/05-definition-of-done.md) | When is a task actually finished? |

### 05 — Operations
Running it.

| Document | Answers |
|---|---|
| [01 Installation Guide](05-operations/01-installation-guide.md) | Bare machine to first conversation |
| [02 Runbook](05-operations/02-runbook.md) | Day-to-day operation |
| [03 Troubleshooting](05-operations/03-troubleshooting.md) | Symptom → cause → fix |
| [04 Release Process](05-operations/04-release-process.md) | Versioning and shipping |

### 06 — Governance
Risk, safety, and the things we chose not to resolve yet.

| Document | Answers |
|---|---|
| [01 Risk Register](06-governance/01-risk-register.md) | What could sink this, and what we will do |
| [02 Security & Privacy](06-governance/02-security-and-privacy.md) | Data handling posture |
| [03 Threat Model](06-governance/03-threat-model.md) | Adversarial analysis |
| [04 Responsible AI](06-governance/04-responsible-ai.md) | A persuasion machine deserves an explicit safety design |
| [05 Open Questions](06-governance/05-open-questions.md) | Known unknowns, with owners |

### 07 — Planning
Sequence and effort.

| Document | Answers |
|---|---|
| [01 Roadmap](07-planning/01-roadmap.md) | Phases from spike to v1.0 |
| [02 Milestones](07-planning/02-milestones.md) | Exit criteria and estimates per milestone |

---

## Reading the confidence markers

Design documents mix things we verified with things we assumed. To avoid
laundering guesses into facts, claims are marked:

| Marker | Meaning |
|---|---|
| **[VERIFIED]** | Measured on this machine, or read from a primary source. Cited. |
| **[SOURCED]** | Published by a third party and cited, but not reproduced by us. |
| **[ESTIMATED]** | Derived by calculation from verified inputs. Arithmetic shown. |
| **[ASSUMED]** | A judgement call with no evidence behind it yet. Should become one of the above. |

An **[ASSUMED]** claim load-bearing enough to sink the project belongs in the
[Risk Register](06-governance/01-risk-register.md) or
[Open Questions](06-governance/05-open-questions.md), not buried in prose.

---

## The one thing to know before reading anything else

Every non-obvious decision in this design traces back to a single number:

> **~1.1 GiB.** That is the VRAM left on an 8 GB RTX 4060 after Qwen3.5-9B and
> its KV cache are resident. It is the entire budget for speech recognition,
> speech synthesis, and turn detection combined.

Most published voice-agent guidance assumes a 24 GB datacentre card and does not
survive contact with that constraint. Where this design departs from mainstream
practice — running STT and TTS on the CPU, for instance — that number is usually
the reason. See [Resource Budget](02-architecture/08-resource-budget.md).

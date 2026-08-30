# Definition of Done

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

Three scopes: a task, a milestone, a release. Each is a checklist, not a
sentiment.

---

## 1. A task is done when…

### Code
- [ ] Implements the requirement it claims, and no more
- [ ] `ruff check` passes — including the **banned-import boundaries** that keep
      `debate/` free of I/O libraries
- [ ] `ruff format` applied
- [ ] `mypy` passes (strict on `debate/`)
- [ ] No file over ~400 lines without a documented reason (NFR-M-05)
- [ ] No magic numbers — named constants citing their source
- [ ] Async: no blocking calls in the event loop; cancellation actually cancels

### Tests
- [ ] Unit tests for new logic
- [ ] **A regression test for any bug being fixed, written before the fix**
- [ ] The full unit suite still runs in under 10 seconds
- [ ] Relevant state invariants asserted
      ([Data Flow & State §8](../02-architecture/04-data-flow-and-state.md))

### Documentation
- [ ] Any decision worth revisiting is an ADR, not a comment
- [ ] Any changed tunable is in `config/default.yaml` with a rationale comment
- [ ] Affected documents in this tree updated **in the same commit**
- [ ] Confidence markers upgraded if measurement now supports a claim

### Commit
- [ ] Conventional format with a scope
- [ ] A prompt change states which behaviour it targets

> **The regression-test-first rule is the one that gets skipped.** It is also the
> only thing that stops the same bug recurring. Writing it after the fix means
> writing a test you already know passes, which verifies nothing.

---

## 2. A milestone is done when…

- [ ] Every task in it meets §1
- [ ] The milestone's stated exit criteria are met
      ([Milestones](../07-planning/02-milestones.md))
- [ ] Integration tests for the milestone's scope pass
- [ ] Measured performance is recorded against the relevant NFRs
- [ ] The [Risk Register](../06-governance/01-risk-register.md) is re-scored —
      risks this milestone should have retired are closed or explained
- [ ] [Open Questions](../06-governance/05-open-questions.md) resolved by this
      work are closed, with the answer recorded in the relevant ADR
- [ ] A manual walkthrough of the milestone's user-facing behaviour has been done

The risk re-scoring matters. A risk register that is written once and never
revisited is decoration; the value is in watching entries close, or fail to.

---

## 3. A release is done when…

### Requirements
- [ ] Every **P0** requirement passes its acceptance test
      ([User Stories](../00-product/04-user-stories.md))
- [ ] Every **P1** requirement either passes or has a written decision to defer
- [ ] `[MANUAL]` criteria have been manually verified and recorded

### Performance — measured on the target machine, not estimated
- [ ] NFR-P-01: median turn latency ≤ 1,200 ms over ≥ 20 turns
- [ ] NFR-P-02: P95 ≤ 2,000 ms
- [ ] NFR-P-03: barge-in stop ≤ 300 ms
- [ ] NFR-P-20: ≥ 25 tok/s sustained
- [ ] NFR-R-01: peak VRAM ≤ 7.5 GiB

### Reliability
- [ ] IT-07 60-minute soak passes: no memory growth, no VRAM growth, no
      tokens/sec decay beyond 10%
- [ ] 20 sessions with ≥ 95% crash-free (NFR-REL-02)
- [ ] Hard-kill test: no committed turn lost (NFR-REL-03)

### Accuracy
- [ ] WER ≤ 10% on the fixture suite
- [ ] **Zero words emitted on `silence.wav`** (NFR-A-02)
- [ ] False-cut rate ≤ 5%; false-hold rate ≤ 10%

### Privacy — the non-negotiable gate
- [ ] **IT-06 passes: full session with the network adapter disabled**
- [ ] Packet capture during a session shows no outbound traffic
- [ ] All service ports verified bound to `127.0.0.1`
- [ ] No transcript content in logs above `DEBUG`
- [ ] No telemetry in any dependency

### Debate quality
- [ ] All Layer 2 probes pass ([Evaluation Framework §4](02-evaluation-framework.md))
- [ ] **P-01 (sycophancy) and P-04 (fabrication) pass** — these are gates, not
      scores
- [ ] ≥ 5 real sessions rated at Layer 3
- [ ] The active `prompt_version` is recorded in the release notes

### Operations
- [ ] Clean-machine install completes in ≤ 15 minutes excluding downloads
- [ ] [Installation Guide](../05-operations/01-installation-guide.md) verified by
      following it literally on a fresh machine
- [ ] [Troubleshooting](../05-operations/03-troubleshooting.md) covers every
      failure encountered during development
- [ ] Version tagged; release notes written

---

## 4. The two gates that override everything

Most checklist items can be waived with a written decision under time pressure.
**These two cannot.**

### Gate 1 — Privacy

> A single outbound connection carrying transcript content contradicts the
> product's central premise
> ([Vision §3](../00-product/01-vision-and-scope.md)). The tool exists so people
> can rehearse arguments they are not ready to have publicly. A tool users
> self-censor in front of is worthless, and trust here is lost once, permanently.
>
> IT-06 is not a nice-to-have. **No release ships without it passing.**

### Gate 2 — Fabrication (probe P-04)

> An agent that invents confident statistics is worse than no agent, because the
> user cannot detect it and the research shows
> [persuasion overrides truth](https://arxiv.org/html/2504.00374v1) in precisely
> this setting. Shipping a fluent fabricator degrades the user's thinking while
> feeling like it sharpens it.
>
> This is the harm case in
> [Responsible AI](../06-governance/04-responsible-ai.md), and it blocks release.

---

## 5. What "done" explicitly does not require

Stated to prevent scope creep dressed as rigour:

| Not required | Why |
|---|---|
| 100% test coverage | 90% on `debate/`; coverage is a floor, not a goal |
| Cross-platform verification | Windows is the only supported target |
| Performance beyond the NFRs | 900 ms is not better than 1,150 ms in any way the user notices |
| Documentation of obvious code | Comments explain *why*; the code shows *what* |
| Handling of failures we have not seen | The F-catalogue covers the anticipated set |
| Optimising anything that meets its budget | Measure first, and only optimise what fails |

---

## 6. Reviewing your own work

This is a single-developer project, so review is self-review, which is
structurally weak. Two mitigations that actually help:

**Read the diff, not the code.** Reviewing the change in isolation from the file
it lives in surfaces things — a stray debug line, an inconsistent name, a
forgotten TODO — that reading in context hides.

**Wait.** Where the change is subtle, particularly around FR-13 or the state
machine, review it the following day. The cost is a day; the alternative is a
class of bug that surfaces weeks later as inexplicable agent behaviour.

For substantial changes, the questions worth asking explicitly:

1. What breaks if this is wrong, and how would I find out?
2. Is there a simpler version?
3. Which document does this change invalidate?

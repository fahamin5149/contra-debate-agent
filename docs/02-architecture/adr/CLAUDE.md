# CLAUDE.md — writing and changing ADRs

ADRs are the load-bearing documents in this tree. Everything else defers to them.

---

## What belongs here

An ADR records **one decision** that was not obvious, where a reasonable engineer
could have chosen differently.

| Write an ADR | Do not write an ADR |
|---|---|
| Choosing between two viable libraries | A naming convention |
| A structural constraint (GPU has one tenant) | An implementation detail with one sensible option |
| Anything you would have to re-argue in three months | Anything the code makes obvious |
| Reversing an earlier decision | A bug fix |

If you find yourself explaining *why* in more than a sentence inside a
non-ADR document, that explanation belongs here and the document should link to
it.

---

## Template

```markdown
# ADR-NNNN: <decision, stated as an action>

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | YYYY-MM-DD | High/Medium/Low | Easy/Moderate/Hard |

## Context
What forces the decision. Constraints, requirements, measurements.
Cite requirement and NFR IDs.

## Decision
What we are doing. One paragraph, stated plainly.

## Alternatives considered
Each with why it was rejected. THE MOST VALUABLE SECTION — it stops the same
ground being re-litigated. Include options that were close calls and say so.

## Consequences
### Positive
### Negative      ← must be non-empty and honest
### Neutral

## Revisit when
Concrete triggers. Not "if problems arise".

## Verification
Which benchmark or test would show this was wrong.
```

---

## The four sections people get wrong

### "Alternatives considered" — the reason ADRs are worth writing

Record the options you rejected **and why**, including ones that were close.
ADR-0003 records that DIY orchestration was "rejected, but closely", and names
the single factor that decided it. That is the useful form.

An ADR whose alternatives section says "we considered X and it was worse" tells a
future reader nothing they can act on.

### "Negative consequences" — must be honest

An ADR with no real negatives is a decision that was not examined. Every choice
here costs something:

- ADR-0006 records that we cannot have Orpheus's emotional prosody, and that this
  is a genuine loss for a debate agent.
- ADR-0009 records that the GIL might make CPU placement unworkable.
- ADR-0012 records that the browser becomes a required component.

Write the negative you would least like to be quoted on.

### "Revisit when" — concrete triggers only

| Good | Bad |
|---|---|
| "BM-01 shows < 18 tok/s" | "If performance is inadequate" |
| "Hardware reaches ≥ 12 GB VRAM" | "If we get better hardware" |
| "Measured false-cut rate exceeds 5%" | "If users complain" |

A decision without revisit triggers becomes folklore — something the project does
because it always has, long after the constraint that justified it has gone.

### Confidence and Reversibility

These two columns are the register's early-warning system.

| Reversibility | Cost of changing later |
|---|---|
| Easy | One component behind an interface. Hours. |
| Moderate | Several components or the pipeline shape. Days. |
| Hard | Structural. Weeks, or a rewrite. |

**Watch for low confidence + hard reversibility.** Nothing currently sits there,
and nothing should without a deliberate discussion.

ADR-0008 is the worked example of the system functioning: Low confidence,
Moderate reversibility, marked **Provisional**, and when the assumption proved
wrong the cost was ~3 days rather than a rewrite — because the low confidence was
declared up front and the affected component sat behind an interface.

---

## Superseding an ADR

**Never delete or rewrite. Never renumber.**

1. New ADR gets the next number; state `**Supersedes** [ADR-nnnn](...)`.
2. Old ADR: status becomes `**SUPERSEDED** by [ADR-nnnn](...)`.
3. Old ADR gains a banner at the top: what changed, why, and — usefully — what
   the reversal cost.
4. **Keep the old body unedited.** Its reasoning is still worth reading; often it
   correctly identified the option that later won.
5. Update `README.md`: strike through the old row, add the new one.
6. `grep -rn "ADR-nnnn" ../../..` and fix every citing document.

See ADR-0008 → ADR-0012 for the complete worked example.

---

## Status values

| Status | Meaning |
|---|---|
| **Proposed** | Under discussion; do not build on it |
| **Accepted** | Decided; implementation should follow it |
| **Provisional** | Decided *pending* a specific named open question |
| **Superseded** | Replaced; links to its replacement |
| **Deprecated** | No longer applies; not replaced |

**Provisional is the useful one.** It lets work proceed on a decision that may
reverse, while making the exposure explicit. Use it when you are choosing a
default in the absence of an answer — and always name the OQ it depends on.

---

## Current set

12 ADRs. Read `README.md` for the index with confidence and reversibility.

The four whose reasoning is most worth understanding before changing anything:

| | Why |
|---|---|
| **ADR-0004** | LLM on GPU, everything else on CPU. The central resource decision; most others follow from it. |
| **ADR-0001** | Cascaded, not speech-to-speech. Structural, and the reason transcripts exist at all. |
| **ADR-0012** | Browser/WebRTC with AEC. Recent, and its non-obvious consequence — audio must be *played* by the browser — is easy to miss. |
| **ADR-0009** | Python 3.11. The only `Hard` reversibility in the set. |

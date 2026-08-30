# CLAUDE.md — Contra

Read this before doing anything in this repository.

---

## 1. What this is

**Contra** — a fully local, offline voice agent that debates the user. Speech in,
argument out, nothing leaves the machine. Working name; renameable by
find-and-replace.

**Current state: documentation only. There is no code yet.**
`docs/` (56 files) is the complete design record. `src/` does not exist.

**The next action is Phase 0 benchmarks**, not implementation. See §7.

---

## 2. Five facts that are load-bearing

Do not re-derive these. Do not contradict them without evidence.

1. **8 GB VRAM is the constraint that shapes everything.** After Qwen3.5-9B, its
   KV cache, and CUDA overhead (~6.86 GiB), roughly **1.1 GiB remains** — and
   possibly only 0.34 GiB. Nearly every non-obvious decision traces here.
   → `docs/02-architecture/08-resource-budget.md`

2. **Qwen3.5-9B is hybrid-attention.** 24 Gated DeltaNet + 8 full-attention
   layers, so only 8 contribute a KV cache: **32 KiB/token**, ~4× smaller than a
   conventional 9B. This is what makes the project fit in 8 GB.

3. **The GPU has exactly one tenant.** LLM on GPU; STT, TTS, VAD, turn detection
   all on CPU. Partial GPU offload collapses throughput rather than degrading it,
   so the LLM's VRAM is protected absolutely. → ADR-0004

4. **Nothing has been measured.** Every performance number is `[SOURCED]` or
   `[ESTIMATED]` from other people's hardware. Treat all of them as unverified.

5. **The user uses speakers, not headphones.** Echo cancellation is mandatory,
   and audio therefore loops through a browser in *both* directions — the
   browser's AEC can only cancel audio it renders itself. → ADR-0012

---

## 3. The docs tree — what each folder is for

| Folder | Contains | Go here when |
|---|---|---|
| `docs/00-product/` | Vision, PRD, personas, user stories, NFRs, glossary | You need to know **what** to build or **why** |
| `docs/01-research/` | Technology landscape, model analysis, hardware baseline, component evaluation, debate literature | You are tempted to research something — check here first, it may already be done and cited |
| `docs/02-architecture/` | C4 views, sequence diagrams, state machine, API spec, data model, latency + resource budgets | You need to know **how** it fits together |
| `docs/02-architecture/adr/` | 12 decision records | You need to know **why** a choice was made, or want to change one |
| `docs/03-engineering/` | Repo structure, dev env, coding standards, config, **prompt spec**, error handling | You are about to write code |
| `docs/04-quality/` | Test strategy, evaluation framework, **benchmark plan**, observability, definition of done | You need to know when something is correct or finished |
| `docs/05-operations/` | Install, runbook, troubleshooting, release | You are running or shipping it |
| `docs/06-governance/` | Risk register, security, threat model, responsible AI, open questions | You need to know what could go wrong or what is undecided |
| `docs/07-planning/` | Roadmap, milestones | You need to know what comes next |

**Entry point:** `docs/README.md` is the index and explains the reading order.

---

## 4. ID schemes — how to refer to things

Every artifact has a stable ID. **Use them; never paraphrase a requirement.**

| Prefix | Means | Defined in |
|---|---|---|
| `FR-nn` | Functional requirement | `00-product/02-product-requirements.md` |
| `NFR-<class>-nn` | Non-functional (P=perf, R=resource, A=accuracy, S=security, REL, U, M, PORT) | `00-product/05-non-functional-requirements.md` |
| `US-nnn` | User story with acceptance criteria | `00-product/04-user-stories.md` |
| `ADR-nnnn` | Architecture decision | `02-architecture/adr/` |
| `RISK-nn` | Risk | `06-governance/01-risk-register.md` |
| `OQ-nn` | Open question | `06-governance/05-open-questions.md` |
| `BM-nn` | Benchmark | `04-quality/03-benchmark-plan.md` |
| `IT-nn` | Integration test | `04-quality/01-test-strategy.md` |
| `BT-nn` | Behavioural test | `04-quality/01-test-strategy.md` |
| `P-nn` | Evaluation probe | `04-quality/02-evaluation-framework.md` |
| `F-nn` | Failure mode | `03-engineering/06-error-handling-and-resilience.md` |
| `I-n` | State invariant | `02-architecture/04-data-flow-and-state.md` |

Write "FR-13 requires…", not "the requirement about barge-in history".

### Confidence markers — use them in any claim you add

| Marker | Meaning |
|---|---|
| `[VERIFIED]` | Measured on this machine, or read from a primary source. Cite it. |
| `[SOURCED]` | Published by a third party, cited, **not reproduced by us** |
| `[ESTIMATED]` | Derived by arithmetic from verified inputs. **Show the arithmetic.** |
| `[ASSUMED]` | A judgement call with no evidence. Should become one of the above. |

Never silently upgrade a marker. An `[ASSUMED]` claim that could sink the project
belongs in the risk register or open questions, not buried in prose.

---

## 5. How to change things

### Changing a decision
**Edit the ADR, not the prose.** Every document defers to the ADRs. If you change
a decision, update its ADR, then propagate to every document that cites it — and
grep to find them all.

A superseded ADR is **never deleted**. Set its status to `SUPERSEDED by
ADR-nnnn`, add a banner explaining what changed and why, and keep the original
reasoning. See ADR-0008 for the worked example.

### Adding a decision
Next number in sequence. Use the template in `docs/02-architecture/adr/README.md`.
**The "Alternatives considered" and "Revisit when" sections are mandatory** — a
decision without revisit triggers becomes folklore.

### Answering an open question
1. Record the answer, date, and evidence in the OQ's entry
2. Move it to the "Closed questions" section — do not delete it
3. Create or update the ADR that now carries the decision
4. Update the summary table
5. **Grep for every document that referenced it and fix them**
6. Check whether closing it creates a *new* risk or question

OQ-01 → ADR-0012 is the worked example of all six steps.

### Changing a requirement
Requirements are referenced by ID from user stories and tests. Changing one means
updating its story's acceptance criteria too. Adding one means adding a story.

### Changing a prompt (once code exists)
**Never edit a prompt version in place.** Copy to `vN+1`, edit, run the Layer 2
probes, run three real sessions, then update `prompts/ACTIVE.yaml`. Old versions
are the evidence base. → ADR-0011

---

## 6. Conventions for writing in this tree

- **Markdown links, relative paths.** All 440+ internal links resolve; keep it
  that way. Verify after bulk edits.
- **Mermaid** for diagrams. Renders on GitHub, diffs as text.
- **Tables** for anything comparative.
- **Blockquotes** for the one insight per document that the reader must not miss.
  Use them sparingly — if everything is emphasised, nothing is.
- **Explain trade-offs, don't just state conclusions.** A rejected alternative
  with its reason is worth more than the chosen one, because it stops the same
  ground being re-litigated.
- **Be honest about what is unknown.** This tree's main value is that it
  distinguishes measured from assumed. Do not erode that by rounding uncertainty
  up to confidence.
- Every document starts with a status/date table.

---

## 7. What to do next

**Phase 0 benchmarks — `docs/04-quality/03-benchmark-plan.md`.**

Five measurements, ~2 days, retiring five of the top seven risks:

| | Answers | Gates |
|---|---|---|
| BM-01 | ≥ 25 tok/s on this laptop GPU? | The whole latency design |
| BM-02 | Does prefix caching work on hybrid DeltaNet? | NFR-P-12, speculative prefill |
| BM-03 | CPU speech RTF under GPU load? Does the GIL release? | ADR-0004, ADR-0009 |
| BM-04 | Actual free VRAM? | The resource budget |
| BM-05 | Does AEC survive double-talk with speakers? | Barge-in (Phase 2) |

Benchmarks live in `benchmarks/`, a **sibling of `src/`, not of `tests/`** —
they run before application code exists. Results go in `benchmarks/results/` and
are **committed**; they are the evidence that upgrades `[SOURCED]` to
`[VERIFIED]`.

**Do not start implementation before these run.** If BM-01 returns 15 tok/s the
right answer is to switch to Qwen3.5-4B *now*, not to discover it during
integration.

---

## 8. When you do write code

Read `docs/03-engineering/` first. The rules that are non-obvious:

| Rule | Why |
|---|---|
| `debate/` imports **no** I/O library | It is the core; enforced by `ruff` banned-imports, not convention |
| Pipecat only in `pipeline/assembly.py` | Framework as runtime, not architecture — keeps ADR-0003 reversible |
| One composition root (`app.py`) | Swapping a component is a one-line change |
| Never block the event loop | A blocking call stalls **audio capture** — use `asyncio.to_thread` |
| `cancel()` must abort the HTTP request | Not just stop reading the stream, or the GPU keeps generating unheard tokens |
| Prompts are versioned files, not string literals | ADR-0011 |
| Python **3.11**, not the 3.13 installed | ML wheel coverage on Windows — RISK-04 |

### The three highest-value tests

1. **FR-13 barge-in truncation** (`ConversationState`). History must record what
   was *spoken*, not what was *generated*. Passes trivially without streaming,
   fails silently with it, and surfaces weeks later as the agent referencing
   things it never said. Assert invariant **I-3**.
2. **`silence.wav` → empty transcript** (NFR-A-02). The reason Parakeet was
   chosen. Force-included past `.gitignore`.
3. **IT-06 offline test.** Full session with the network adapter disabled. A
   **release gate** — the product's central premise.

---

## 9. Things not to do

- **Do not load `mmproj-*.gguf`.** The vision projector costs 918 MB of VRAM for
  a capability this product does not use.
- **Do not bind any service to `0.0.0.0`.** `llama-server` has no auth. Loopback
  is a hard, non-overridable invariant, not a default. → T-01 in the threat model
- **Do not add "win the debate" to the prompt.** It would improve rhetoric and
  damage the user. Explicit anti-goal. → `06-governance/04-responsible-ai.md`
- **Do not add web search / RAG.** Breaks the offline guarantee, and citations the
  agent cannot verify manufacture unearned credibility.
- **Do not log transcript content above `DEBUG`.**
- **Do not use `Win32_VideoController` to read VRAM.** It reports 4 GB for this
  8 GB card. Use `nvidia-smi`.
- **Do not add assistant features.** RISK-10. Every one dilutes the single thing
  this does.

---

## 10. The two risks that decide whether this is worth building

Both are about model behaviour and human epistemics, not engineering. Neither is
retired by measurement.

- **RISK-08 (score 20) — sycophancy.** Instruction-tuned models are trained
  toward agreeableness; this persona asks one to resist that for twenty turns
  under social pressure. Every test can pass while the product is worthless.
  Gated by probes P-01 and P-02.
- **RISK-09 (score 15) — persuasive fabrication.** Research shows persuasion
  overrides truth in LLM debate. An agent that invents confident statistics
  degrades the user's thinking while feeling like it sharpens it. Gated by probe
  P-04.

If you are ever choosing between making the agent *more effective* and making it
*more honest*, choose honest. That trade is the product.

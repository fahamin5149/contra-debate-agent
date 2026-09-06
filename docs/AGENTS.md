# CLAUDE.md — editing the docs tree

Applies to everything under `docs/`. The root `CLAUDE.md` covers the project;
this covers **writing in it**.

---

## The tree's purpose

This tree exists to distinguish **what we measured** from **what we assumed**,
and to record **why** each decision was made so it can be revisited rather than
inherited.

Every convention below serves one of those two jobs. Erode them and the tree
becomes 56 files of confident-sounding prose, which is worse than no
documentation because it invites trust it has not earned.

---

## Which tier does this belong in?

| Content | Tier | Not |
|---|---|---|
| What to build, for whom, success criteria | `00-product/` | — |
| Evidence gathered before deciding, with citations | `01-research/` | Decisions — those go in ADRs |
| How the system fits together | `02-architecture/` | Why a choice was made — that is an ADR |
| **Why** a choice was made, and its alternatives | `02-architecture/adr/` | Anywhere else |
| How code is written and organised | `03-engineering/` | — |
| How we know it works | `04-quality/` | — |
| How it is run and shipped | `05-operations/` | — |
| What could go wrong; what is undecided | `06-governance/` | Buried in prose elsewhere |
| Sequence and effort | `07-planning/` | — |

**If content seems to fit two tiers, the boundary is wrong** — reconsider the
split rather than duplicating.

### The rule that matters most

> **Rationale lives in ADRs. Everything else cites them.**
>
> When a document explains *why* something is the way it is in more than a
> sentence, that explanation belongs in an ADR and the document should link to it.
> Otherwise the reasoning gets duplicated, the copies drift, and changing the
> decision means hunting through nine files.

---

## Confidence markers — non-negotiable

Every factual claim about performance, resources, or third-party behaviour
carries one:

| Marker | Meaning | Obligation |
|---|---|---|
| `[VERIFIED]` | Measured here, or read from a primary source | Cite the source or the measurement |
| `[SOURCED]` | Published by a third party, **not reproduced by us** | Link it |
| `[ESTIMATED]` | Derived by arithmetic from verified inputs | **Show the arithmetic** |
| `[ASSUMED]` | Judgement call, no evidence | Should appear in OQ or the risk register |

**Never upgrade a marker without the evidence that justifies it.** When a
benchmark result arrives, upgrade the specific claims it covers and say which
benchmark did it.

`[ESTIMATED]` without visible arithmetic is indistinguishable from `[ASSUMED]`
dressed up. Show the working — see the KV-cache derivation in
`02-architecture/08-resource-budget.md` §2.2 for the standard.

---

## Cross-referencing

- **Always by ID**: "FR-13 requires…", never "the barge-in history requirement".
- **Always with a link** on first mention in a document.
- **Relative paths only.** 440+ internal links currently resolve; keep it that
  way.

After any bulk edit, verify:

```powershell
# from repo root — lists any link whose target does not exist
$root="docs"; Get-ChildItem -Recurse -File $root -Filter *.md | ForEach-Object {
  $d=$_.DirectoryName; $t=Get-Content $_.FullName -Raw
  [regex]::Matches($t,'\]\(([^)]+)\)') | ForEach-Object {
    $l=$_.Groups[1].Value
    if ($l -match '^(https?:|mailto:|#)') { return }
    $p=($l -split '#')[0]; if ($p -eq '') { return }
    if (-not (Test-Path (Join-Path $d $p))) { "$($_.Groups[1].Value)  in  $($_.Name)" }
  }
}
```

---

## Document structure

Every document opens with a status table:

```markdown
# Title

| | |
|---|---|
| **Status** | Draft / Complete / Live |
| **Last updated** | YYYY-MM-DD |
| **Related** | links |
```

Then numbered sections. Long documents get a table of contents; short ones do
not need one.

---

## Writing style

**Tables for anything comparative.** Options, trade-offs, thresholds, failure
modes. Prose comparisons are harder to scan and harder to keep complete.

**Mermaid for diagrams.** Renders on GitHub, diffs as text, editable without a
tool.

**Blockquotes for the one insight per document the reader must not miss.**
Sparingly — one or two per document. If everything is emphasised, nothing is.
Good candidates: a non-obvious consequence, a trap, or the reason a decision
that looks odd is correct.

**Explain trade-offs, not just conclusions.** A rejected alternative with its
reason is worth more than the chosen one — it stops the same ground being
re-litigated in three months.

**State limitations plainly.** `04-quality/02-evaluation-framework.md` §6 and
`06-governance/04-responsible-ai.md` §5 are the standard: a section that says
"here is what this cannot do" is more useful than one that overclaims.

**Do not pad.** Every table row and every sentence should earn its place. If a
section exists only to make the document look complete, delete it.

---

## Keeping the tree consistent

When you change something, the propagation is the work. A partial update is
worse than none, because it produces two documents that disagree.

**Checklist after changing a decision:**

1. Update the ADR (or write a new one and supersede the old)
2. `grep -rn "ADR-nnnn" docs/` — fix every citing document
3. `grep -rni "<the-old-assumption>" docs/` — catch prose that assumed it
4. Update affected budgets (latency, resource) — numbers, not just words
5. Update the risk register: does this close a risk, or create one?
6. Update open questions: does this close one, or create one?
7. Update roadmap and milestones if the schedule moves
8. Re-run the link check

The OQ-01 → ADR-0012 change (headphones → speakers) touched **19 files**. That
is normal for a decision reversal, and doing it fully is what keeps the tree
trustworthy.

---

## Superseding, never deleting

A superseded ADR keeps its original text, gains a banner explaining what changed,
and its status becomes `SUPERSEDED by ADR-nnnn`. A closed open question moves to
"Closed questions" with its answer, date, and evidence.

> The reasoning is worth more than the conclusion. Someone — possibly you in
> three months — will want to know whether an option was considered and rejected,
> or simply never thought of. Deleting the record destroys that distinction.

ADR-0008 is the worked example: superseded, retained in full, with a note on what
the reversal cost and why it was cheap.

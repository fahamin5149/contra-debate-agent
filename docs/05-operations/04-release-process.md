# Release Process

| | |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-08-30 |

A single-developer local application still benefits from releases: they create a
point where the whole system is verified together, and a known-good state to
return to when a change makes things worse in ways that are hard to attribute.

---

## 1. Versioning

Semantic versioning, adapted — there is no public API, so the components are
reinterpreted:

| Component | Increments when |
|---|---|
| **Major** | The architecture changes, or config/database migration is required |
| **Minor** | A feature is added; a P1 requirement is met |
| **Patch** | A bug is fixed; a prompt version is promoted |

Pre-1.0 while any P0 requirement is unmet.

### The prompt version is part of the release identity

```
v0.4.2 (prompt debate-v5, model Qwen3.5-9B-UD-Q4_K_XL)
```

> A prompt change can alter the product's behaviour more than most code changes,
> and it is the change least likely to be caught by tests. Recording it in the
> release identity means "which version was I using when it felt good?" has an
> answer.

---

## 2. Release checklist

Full gate in [Definition of Done §3](../04-quality/05-definition-of-done.md).
Condensed:

```
□ All P0 requirements pass acceptance tests
□ Unit + integration suites pass
□ Performance measured on target hardware:
    □ NFR-P-01  median ≤ 1,200 ms over ≥ 20 turns
    □ NFR-P-02  P95 ≤ 2,000 ms
    □ NFR-P-03  barge-in ≤ 300 ms
    □ NFR-R-01  peak VRAM ≤ 7.5 GiB
□ IT-07 60-minute soak: no memory/VRAM growth, no tok/s decay
□ Accuracy fixtures pass, incl. ZERO output on silence.wav
□ ▶ GATE 1 — IT-06 offline test passes (network adapter disabled)
□ ▶ GATE 2 — Probe P-04 (fabrication) passes
□ Probe P-01 (sycophancy) passes
□ ≥ 5 real sessions rated
□ Clean-machine install verified by following the guide literally
□ Troubleshooting updated with every failure hit during development
□ Version tagged, release notes written
```

**The two gates cannot be waived.** Everything else can be deferred with a
written decision; these two are the product's premises, not its features.

---

## 3. Release notes format

```markdown
# v0.4.0 — 2026-10-15

**Prompt:** debate-v5 · **Model:** Qwen3.5-9B-UD-Q4_K_XL · **llama.cpp:** b7412

## Changed
- Turn detection now extends to 1,800 ms on incomplete transcripts.
  False-cut rate 7.2% → 3.1% on the fixture suite.
- Prompt v5 strengthens the anti-sycophancy rules. Probe P-01 now passes on
  all three intensity settings (v4 failed at `socratic`).

## Measured
| Metric | v0.3.0 | v0.4.0 | Target |
|---|---|---|---|
| Latency p50 | 1,340 ms | 1,190 ms | ≤ 1,200 |
| Latency p95 | 2,210 ms | 1,880 ms | ≤ 2,000 |
| tok/s | 29.4 | 30.1 | ≥ 25 |
| Peak VRAM | 6,940 MiB | 6,948 MiB | ≤ 7,680 |
| False-cut rate | 7.2% | 3.1% | ≤ 5% |

## Known issues
- Prefix cache hit rate drops to ~60% after context compaction (OQ-03)

## Migration
None. (Or: schema migration 003 runs automatically on first start.)
```

> **The Measured table is the point of the release note.** In a project where the
> primary risks are performance and subjective quality, a release note listing
> only what changed is much less useful than one showing what moved. It also makes
> regressions visible — a change that improves debate quality while adding 300 ms
> is a trade worth seeing explicitly.

---

## 4. Branching

```
main            ← always releasable
  └── feat/turn-detection-tuning
  └── fix/barge-in-history-truncation
  └── prompt/v5-anti-sycophancy
```

`prompt/` is a distinct prefix because prompt changes follow a different
validation path — probes and real sessions rather than tests
([Evaluation Framework §8](../04-quality/02-evaluation-framework.md)) — and
separating them makes that visible in history.

Tags: `v0.4.0` on `main`.

---

## 5. Migrations

Forward-only numbered SQL scripts, applied automatically at startup, recorded in
`schema_version`.

```
src/contra/persistence/migrations/
  001_initial.sql
  002_add_prefix_cache_hit.sql
```

Rules:

1. **Never edit an applied migration.** Add a new one.
2. Never drop a column holding session data. Deprecate instead.
3. Back up `data/contra.db` before applying a major-version migration.

> Rule 2 matters more than it looks. The database holds the user's actual debate
> history — data that cannot be regenerated and that they may care about far more
> than the application itself. Losing a schema experiment is free; losing six
> months of transcripts is not.

---

## 6. Rollback

```powershell
git checkout v0.3.0
uv sync
# revert prompts/ACTIVE.yaml if it changed
```

Rolling back **code** is easy. Rolling back a **schema migration** is not —
forward-only migrations have no down scripts. Restore the database backup taken
before the migration.

For a bad prompt version, rollback is simply editing `ACTIVE.yaml` and
restarting. This is why old versions are never deleted.

---

## 7. Cadence

No schedule. Release when:

- A milestone completes ([Milestones](../07-planning/02-milestones.md))
- A prompt version passes promotion and materially improves the product
- A significant bug is fixed
- Before any risky refactor — so there is a known-good state to return to

The last one is the most valuable in practice.

---

## 8. What a release is not

| Not | Why |
|---|---|
| A distribution artifact | No installer, no packaging. Users clone and run. |
| A public announcement | Single user |
| A support commitment | No back-porting; `main` is the only supported line |
| A feature freeze | Work continues immediately |

A release here is a **verified checkpoint**, nothing more. That is enough to be
worth doing.

# ADR-0010: SQLite for session persistence

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | High | Easy |

## Context

We must persist sessions, turns, and per-turn timings (FR-04, FR-53). Constraints:

- **Single user, single machine, single writer.** No concurrency to speak of.
- **NFR-REL-03:** no committed turn may be lost, even on a hard kill.
- **NFR-S-01:** local only.
- Volume is trivial — ~25 KB per session, ~12 MB for 500 sessions.
- The [Evaluation Framework](../../04-quality/02-evaluation-framework.md) needs
  to query across sessions: *"did prompt v3 produce longer user turns than v2?"*

## Decision

**SQLite**, with `journal_mode = WAL`, accessed through a thin repository layer.
Committed turns are written **synchronously** before the next turn begins.

Schema: [Data Model](../06-data-model.md).

## Alternatives considered

### JSON files per session — rejected

Tempting for its simplicity: one file per session, human-readable, trivially
inspectable, no schema.

Rejected on two counts:

1. **Durability.** Writing a whole JSON file per turn means rewriting the entire
   session on every turn — slow and, more importantly, a crash mid-write
   truncates the file and loses *the whole session*, not just the last turn.
   Directly violates NFR-REL-03.
2. **Queryability.** The evaluation work needs cross-session aggregation. Doing
   that over a directory of JSON files means loading everything into memory and
   filtering by hand — a small ad-hoc database, written badly.

We keep the readable artifact anyway: a Markdown transcript is exported per
session ([Data Model §3](../06-data-model.md)). Best of both, since the export
is derived rather than authoritative.

### Append-only JSONL — rejected, but close

Genuinely good: append is atomic-ish, crash-safe, streams naturally, and one line
per turn matches our write pattern well. This is the strongest alternative.

Rejected for the same query reason. Cross-session analysis over JSONL means
writing aggregation code that SQLite provides for free, and correlating turns
with metrics requires a join we would have to implement ourselves.

### DuckDB — rejected

Better at the analytical queries the evaluation work wants. Worse at the
transactional per-turn writes that are the primary workload. Optimises the
secondary use case at the expense of the primary. If analysis ever outgrows
SQLite, DuckDB can read SQLite files directly — so this is available later
without committing now.

### PostgreSQL — rejected

A server process, a service to install, a connection to manage, credentials to
handle — all to store 12 MB for one local user. Operationally absurd here, and it
would add a second supervised process to a system that already has two.

### In-memory only — rejected

FR-04 requires persistence. A debate the user cannot review afterwards loses
Journey D entirely ([Personas & Journeys §8](../../00-product/03-personas-and-journeys.md)).

## Consequences

### Positive
- **In the Python standard library.** Zero dependencies, nothing to install.
- Genuinely crash-safe with WAL — a hard kill loses at most the in-flight turn,
  satisfying NFR-REL-03.
- Real SQL for the cross-session analysis the evaluation work needs.
- Single file — trivial to back up, copy, or delete (NFR-S-06).
- Excellent tooling for manual inspection.
- Handles our volume with orders of magnitude to spare.

### Negative
- **Schema migrations must be managed** even for a local app. Forward-only
  numbered scripts and a `schema_version` table
  ([Data Model §2.6](../06-data-model.md)). Modest ongoing overhead.
- Not human-readable without a tool — mitigated by the Markdown export.
- **`PRAGMA foreign_keys = ON` must be set on every connection.** SQLite
  silently ignores foreign key constraints otherwise, which would make the
  `ON DELETE CASCADE` clauses in our schema inert. This is a classic and quiet
  footgun; it belongs in the repository layer's connection factory, not in
  application code.
- Concurrent writers are a weakness — irrelevant, we have one.

### Neutral
- Ties transcripts to a file that must travel with the app data directory.

## Implementation notes

| Pragma | Value | Why |
|---|---|---|
| `journal_mode` | `WAL` | Readers (UI, analysis) never block the writer |
| `synchronous` | `NORMAL` | Durable enough with WAL; `FULL` is unnecessary latency |
| `foreign_keys` | `ON` | **Per connection**, see above |
| `busy_timeout` | `5000` | Analysis scripts should wait, not fail |

**Write policy.** Committed turns write synchronously; metrics may batch. The
asymmetry is deliberate — losing a turn breaks the transcript, losing a timing
row loses a data point.

## Revisit when

- Cross-session analysis becomes slow enough to matter → DuckDB reading the same
  file.
- Multi-user or networked sessions enter scope (they will not in v1).
- Session volume exceeds ~100,000 (roughly 200 years of daily use).

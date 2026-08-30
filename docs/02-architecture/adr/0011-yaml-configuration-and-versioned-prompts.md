# ADR-0011: YAML configuration; prompts as versioned files

| Status | Date | Confidence | Reversibility |
|---|---|---|---|
| Accepted | 2026-08-30 | High | Easy |

## Context

Two kinds of tunable exist in this system, and conflating them is a mistake.

**Ordinary configuration** — ports, device names, thresholds, sampling
parameters. FR-33 and NFR-M-03 require these to live outside code.

**The debate persona** — the system prompt that defines how the agent argues. This
is different in kind:

- It is the **highest-iteration artifact in the project**. It will be rewritten
  dozens of times.
- Changes to it are the primary way the product improves.
- Its effect is **subjective and only measurable across many sessions**.
- A change can silently degrade quality in ways no test catches.

Treating the persona as an ordinary config string loses the ability to answer
*"was the agent a better opponent before I changed this?"* — which is the central
question of the whole project.

## Decision

**Two mechanisms, deliberately separated.**

### 1. YAML for configuration

```
config/
  default.yaml        # committed; all defaults
  user.yaml           # gitignored; user overrides
```

Precedence: `CONTRA_*` env vars > `user.yaml` > `default.yaml`.
Validated once at startup into typed objects; **fails loudly** on invalid values.

### 2. Prompts as versioned files

```
prompts/
  debate/
    v1.md
    v2.md
    v3.md          ← active
  topic_extraction/
    v1.md
  summarisation/
    v1.md
  ACTIVE.yaml      # names the active version per role
```

`ACTIVE.yaml`:
```yaml
debate: v3
topic_extraction: v1
summarisation: v1
```

**The active version is recorded in every session row** (`sessions.prompt_version`
— [Data Model §2.1](../06-data-model.md)).

## Rationale for the split

> Recording `prompt_version` per session is what turns persona iteration from
> impression into evidence. It lets us ask, in SQL: *"across sessions using
> `debate-v3`, were user turns longer than under `debate-v2`?"* — longer user
> turns being a plausible proxy for a more engaging opponent.
>
> Without it, every persona change is judged by recollection, and recollection
> about something as subjective as debate quality is worthless.

Prompts also want **prose editing** — paragraphs, structure, comments — which is
miserable inside YAML string blocks and produces unreadable diffs. Separate
Markdown files diff cleanly, which matters when the diff is the thing you are
reasoning about.

## Alternatives considered

### Prompts inline in YAML — rejected

The obvious approach; it is configuration after all. Rejected because multi-line
YAML strings diff badly, cannot carry comments explaining *why* a line exists,
and — critically — versioning them means versioning the whole config file, so
you cannot tell a prompt change from a port change.

### Prompts in Python string constants — rejected

Violates NFR-M-02. Every persona experiment becomes a code change, which
discourages the rapid iteration this artifact specifically needs.

### TOML for config — reasonable, not chosen

Better-specified than YAML and free of its sharper edges (the Norway problem,
significant whitespace). Chosen against because YAML's nesting reads better for
the deep structure here (per-stage settings, sampling parameters), and it is more
familiar. A defensible reversal.

### JSON for config — rejected

No comments. For a file whose entire purpose is human tuning, that is
disqualifying — the *why* behind a threshold is as valuable as the number.

### Environment variables only — rejected

Fine for a handful of settings, unmanageable for nested structure. Retained as
the highest-precedence override layer, which is where they work well.

### A prompt-management library / registry — rejected

Over-engineered for one user and three prompt roles. Files plus git already give
us history, diffs, and rollback.

## Consequences

### Positive
- Persona iteration is cheap, diffable, and revertible via git.
- `prompt_version` in the session record makes A/B comparison possible.
- Rolling back a bad persona change is `ACTIVE.yaml` plus a restart.
- Config validated once at startup; failures are immediate and named.
- `user.yaml` is gitignored, so personal settings never collide with committed
  defaults.

### Negative
- **Two mechanisms to learn**, and an ambiguous middle ground: does
  `max_tokens` belong in config or prompt? *Rule:* if it is a number the runtime
  enforces, it is config; if it is instruction the model reads, it is prompt.
  `max_tokens: 220` is config; "keep responses under 45 seconds of speech" is
  prompt. Both exist, deliberately — see
  [Internal API Spec §A.2](../05-internal-api-spec.md) on why the hard cap alone
  is insufficient.
- Prompt versions accumulate. Old ones are kept — they cost nothing and are the
  evidence base.
- YAML's quirks are real; the schema validation layer must be strict.

### Neutral
- Requires a small `ConfigLoader` and `PromptLoader`.

## Validation policy

Configuration is validated **once at startup**, and invalid values **stop the
process** with a message naming the offending key and its acceptable range.

> Silently coercing a bad `temperature` to a default is worse than crashing. The
> failure would surface weeks later as mysteriously poor debate quality with no
> connecting signal — the hardest class of bug to trace, produced entirely by
> well-meant leniency.

## Revisit when

- Prompt count exceeds ~10 roles → consider a lightweight registry.
- Runtime prompt editing (without restart) becomes desirable for faster
  iteration.
- Config schema grows complex enough that YAML's ambiguities cause real bugs →
  TOML.

## References

- [Configuration Management](../../03-engineering/04-configuration-management.md)
- [Prompt Engineering Spec](../../03-engineering/05-prompt-engineering-spec.md)

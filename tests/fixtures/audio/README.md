# Audio fixtures

`silence.wav` — 10 seconds of low-level room tone.

**Force-included past `.gitignore`.** It verifies NFR-A-02: Parakeet must emit
*nothing* on silence. That property is the single reason Parakeet was chosen
over Whisper (ADR-0005) — Whisper-family models hallucinate "Thank you for
watching!" into dead air, and in a debate with deliberate thinking pauses that
phantom text enters the argument history.

A test whose fixture is gitignored silently stops existing on a fresh clone,
which is exactly how this protection would be lost.

Phase 2 adds fixtures recorded from **real argumentative speech** (not read
sentences — the pausing patterns differ) for turn-detection tuning.

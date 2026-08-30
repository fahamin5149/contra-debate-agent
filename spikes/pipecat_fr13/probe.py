"""Probe: can Pipecat's frame model express FR-13 spoken-history truncation?

We do NOT need a working agent. We need to answer three questions:

  Q1. Can we attach text-span metadata to a TTS audio frame?
  Q2. Can we observe which audio frames were actually PLAYED (not just queued)?
  Q3. On an interruption, can we recover the played offset before state is lost?

This is a spike — its output is an answer, not code we keep.
ADR-0003 names exactly one revisit trigger, and this probe tests it.
"""

from __future__ import annotations

import inspect


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def show(obj: object, label: str) -> None:
    print(f"\n--- {label} ---")
    try:
        print("signature:", inspect.signature(obj))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        print("signature: <unavailable>", exc)
    attrs = [a for a in dir(obj) if not a.startswith("_")]
    print("attributes:", ", ".join(attrs[:40]))


def main() -> int:
    import pipecat

    print("pipecat version:", getattr(pipecat, "__version__", "unknown"))

    section("Q1 — can a TTS audio frame carry text-span metadata?")
    from pipecat.frames.frames import TTSAudioRawFrame

    show(TTSAudioRawFrame, "TTSAudioRawFrame")
    print("\ndataclass fields:")
    try:
        import dataclasses

        for f in dataclasses.fields(TTSAudioRawFrame):
            print(f"  {f.name}: {f.type}")
    except TypeError:
        print("  not a dataclass")

    section("Q2 — what interruption / playback frames exist?")
    from pipecat.frames import frames as F

    names = [n for n in dir(F) if n.endswith("Frame")]
    interesting = [
        n
        for n in names
        if any(k in n for k in ("Interrup", "TTSStop", "TTSStart", "Played", "Bot", "Stopped"))
    ]
    print("candidate frames:", ", ".join(interesting) or "(none)")
    for name in interesting[:8]:
        show(getattr(F, name), name)

    section("Q3 — can a processor sit downstream of playback?")
    from pipecat.processors.frame_processor import FrameProcessor

    methods = [m for m in dir(FrameProcessor) if not m.startswith("_")]
    print("FrameProcessor methods:", ", ".join(methods))

    section("Q3b — does the output transport report what it actually played?")
    try:
        from pipecat.transports.base_output import BaseOutputTransport

        methods = [m for m in dir(BaseOutputTransport) if not m.startswith("_")]
        print("BaseOutputTransport methods:", ", ".join(methods))
    except ImportError as exc:
        print("BaseOutputTransport not importable:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

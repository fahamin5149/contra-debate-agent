"""Silero VAD integration tests.

> **What these tests can and cannot verify.**
>
> Silero is a *neural* VAD, not an energy threshold — it is trained to reject
> non-speech. Measured on this model (2026-08-31), peak speech probability is:
>
>     silence         0.0006
>     synthetic tone  0.0007
>     white noise     0.0020
>
> All far below the 0.5 threshold. That is correct behaviour and precisely why
> Silero was chosen, but it means **no synthetic signal can exercise the
> positive path.** These tests therefore verify the ONNX plumbing and the
> silence floor; genuine speech detection needs recorded audio.
>
> That recording is the Phase 2 fixture suite, which the test strategy already
> requires be captured from *real argumentative speech* rather than read
> sentences, because pausing patterns differ.
"""

import numpy as np
import pytest

from contra.audio.types import AudioFrame
from contra.detect.interfaces import VadEvent
from contra.detect.silero_vad import SileroVad

pytestmark = pytest.mark.slow

MODEL = "models/silero_vad.onnx"


def frames_from(pcm: np.ndarray, frame_samples: int = 320):
    for i in range(0, len(pcm) - frame_samples, frame_samples):
        yield AudioFrame(
            samples=pcm[i : i + frame_samples].tobytes(),
            sample_rate=16000,
            timestamp_ms=0,
        )


def test_silence_never_reports_speech_start():
    vad = SileroVad(MODEL)
    silence = np.zeros(16000, dtype=np.int16)
    events = [vad.process(f) for f in frames_from(silence)]
    assert VadEvent.SPEECH_START not in events


def test_white_noise_never_reports_speech_start():
    """A neural VAD must reject noise; an energy threshold would not."""
    vad = SileroVad(MODEL)
    noise = (np.random.default_rng(0).normal(0, 1, 16000) * 6000).astype(np.int16)
    events = [vad.process(f) for f in frames_from(noise)]
    assert VadEvent.SPEECH_START not in events


def test_onnx_session_runs_and_threads_state():
    """Verifies the plumbing: input names, state shape, output parsing."""
    vad = SileroVad(MODEL)
    before = vad._state.copy()  # noqa: SLF001 - deliberate white-box check
    tone = (np.sin(2 * np.pi * 220 * np.linspace(0, 1, 16000)) * 12000).astype(np.int16)
    for f in frames_from(tone):
        vad.process(f)
    assert not np.array_equal(before, vad._state), "recurrent state did not advance"  # noqa: SLF001


def test_sustained_silence_after_speech_flag_emits_silence_sustained():
    """Drive the state machine directly — the model can't produce speech here."""
    vad = SileroVad(MODEL, silence_confirm_ms=100)
    vad._speaking = True  # noqa: SLF001 - simulate a completed speech run
    silence = np.zeros(16000, dtype=np.int16)
    events = [vad.process(f) for f in frames_from(silence)]
    assert VadEvent.SILENCE_SUSTAINED in events


def test_reset_clears_speaking_state():
    vad = SileroVad(MODEL)
    silence = np.zeros(8000, dtype=np.int16)
    for f in frames_from(silence):
        vad.process(f)
    vad.reset()
    events = [vad.process(f) for f in frames_from(silence)]
    assert VadEvent.SPEECH_START not in events

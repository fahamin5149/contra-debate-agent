"""Download the speech models Contra needs.

This is the ONLY step that requires network access. Everything afterwards runs
fully offline (NFR-S-01), and IT-06 verifies that by running with the network
adapter disabled.

Usage:  python scripts/fetch_models.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "models"

SILERO_URL = (
    "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx"
)
KOKORO_MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
)
KOKORO_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
)
PARAKEET_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [skip] {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [get ] {dest.name} <- {url}")

    def hook(block: int, size: int, total: int) -> None:
        if total > 0:
            pct = min(100, block * size * 100 // total)
            print(f"\r         {pct:3d}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=hook)  # noqa: S310
    print(f"\r         done ({dest.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    MODELS.mkdir(parents=True, exist_ok=True)
    print(f"Models directory: {MODELS}\n")

    print("Silero VAD:")
    _download(SILERO_URL, MODELS / "silero_vad.onnx")

    print("\nKokoro TTS:")
    _download(KOKORO_MODEL_URL, MODELS / "kokoro-v1.0.onnx")
    _download(KOKORO_VOICES_URL, MODELS / "voices-v1.0.bin")

    print("\nParakeet TDT STT:")
    target = MODELS / "parakeet-tdt-0.6b-v3-onnx"
    if target.exists() and any(target.glob("*.onnx")):
        print(f"  [skip] {target.name}")
    else:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("  huggingface_hub not installed; run: pip install huggingface_hub")
            return 1
        print(f"  [get ] {PARAKEET_REPO}")
        snapshot_download(repo_id=PARAKEET_REPO, local_dir=str(target))
        print("         done")

    print("\nAll models present. Everything from here runs offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from contra.config.loader import ConfigError, load_config
from contra.config.models import Config
from contra.observability.logging import get_logger, setup_logging

LLM_DOWN = """
[X] Cannot reach the model server on 127.0.0.1:8080.

  Start it first:
      llama serve -m C:\\local-models\\Qwen3.5-9B-UD-Q4_K_XL.gguf ^
          -dev Vulkan1 -ngl 99 -c 16384 -fa on --host 127.0.0.1 --port 8080

  -dev Vulkan1 selects the NVIDIA GPU. Check your indices first:
      llama serve --list-devices

  Then confirm it loaded onto the right GPU (expect ~5970 MiB used):
      nvidia-smi --query-gpu=memory.used --format=csv
"""

MODELS_MISSING = """
[X] Speech models are missing: {missing}

  Download them:
      python scripts/fetch_models.py
"""


def _missing_models(config: Config) -> list[str]:
    required = [
        Path("models/silero_vad.onnx"),
        Path(config.tts.model_path),
        Path(config.tts.voices_path),
        Path(config.stt.model_dir),
    ]
    return [str(p) for p in required if not p.exists()]


def main() -> int:
    try:
        config = load_config(Path("config"))
    except ConfigError as exc:
        print(f"\n[X] Configuration error\n\n{exc}\n", file=sys.stderr)
        return 2

    setup_logging(config.logging.level)
    log = get_logger("contra")

    missing = _missing_models(config)
    if missing:
        print(MODELS_MISSING.format(missing=", ".join(missing)), file=sys.stderr)
        return 4

    from contra.debate.llm_client import LlmClient

    async def _check() -> bool:
        client = LlmClient(config.llm)
        try:
            return await client.health()
        finally:
            await client.aclose()

    if not asyncio.run(_check()):
        print(LLM_DOWN, file=sys.stderr)
        return 3

    import uvicorn

    from contra.app import build_app

    app, _, _ = build_app(config)
    log.info("ready", url=f"http://{config.ui.host}:{config.ui.port}")
    uvicorn.run(app, host=config.ui.host, port=config.ui.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

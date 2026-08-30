from __future__ import annotations

import dataclasses
import os
import typing
from pathlib import Path
from typing import Any

import yaml

from contra.config.models import (
    AudioConfig,
    Config,
    ConfigError,
    DebateConfig,
    LlmConfig,
    LoggingConfig,
    SttConfig,
    TtsConfig,
    UiConfig,
    VadConfig,
)

__all__ = ["load_config", "ConfigError"]

_SECTIONS: dict[str, type] = {
    "llm": LlmConfig,
    "audio": AudioConfig,
    "vad": VadConfig,
    "stt": SttConfig,
    "tts": TtsConfig,
    "ui": UiConfig,
    "debate": DebateConfig,
    "logging": LoggingConfig,
}


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(path.name, data, "a top-level mapping")
    return data


def _env_overrides() -> dict[str, Any]:
    """CONTRA_LLM_TIMEOUT_S=45 -> {'llm': {'timeout_s': '45'}}"""
    out: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith("CONTRA_"):
            continue
        parts = key[len("CONTRA_") :].lower().split("_", 1)
        if len(parts) != 2:
            continue
        section, field_name = parts
        if section in _SECTIONS:
            out.setdefault(section, {})[field_name] = value
    return out


def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


def _coerce(cls: type, data: dict[str, Any], prefix: str) -> Any:
    """Build a frozen dataclass, coercing scalars to their annotated types.

    Nested dataclass fields (sampling, webrtc) recurse. Unknown keys are
    ignored rather than raising, so a newer config file stays loadable.
    """
    if not isinstance(data, dict):
        raise ConfigError(prefix, data, "a mapping")

    hints = typing.get_type_hints(cls)
    fields = {f.name for f in dataclasses.fields(cls)}
    kwargs: dict[str, Any] = {}

    for name, raw in data.items():
        if name not in fields:
            continue
        target = hints[name]
        key = f"{prefix}.{name}"
        try:
            if isinstance(target, type) and dataclasses.is_dataclass(target):
                kwargs[name] = _coerce(target, raw, key)
            elif target is bool:
                kwargs[name] = _to_bool(raw)
            elif target is int:
                kwargs[name] = int(raw)
            elif target is float:
                kwargs[name] = float(raw)
            else:
                kwargs[name] = raw
        except (TypeError, ValueError) as exc:
            raise ConfigError(key, raw, f"a valid {target.__name__}") from exc

    return cls(**kwargs)


def load_config(config_dir: Path) -> Config:
    """Load, merge, and validate configuration.

    Precedence: CONTRA_* env vars > user.yaml > default.yaml.
    Validation happens once, here, and fails the process on any bad value.
    """
    merged = _read(config_dir / "default.yaml")
    merged = _deep_merge(merged, _read(config_dir / "user.yaml"))
    merged = _deep_merge(merged, _env_overrides())

    sections: dict[str, Any] = {}
    for name, cls in _SECTIONS.items():
        sections[name] = _coerce(cls, merged.get(name, {}) or {}, name)
    return Config(**sections)

from pathlib import Path

import pytest

from contra.config.loader import ConfigError, load_config


def test_loads_defaults(tmp_path: Path):
    (tmp_path / "default.yaml").write_text(
        "llm:\n"
        "  base_url: 'http://127.0.0.1:8080/v1'\n"
        "  model: 'qwen3.5-9b'\n"
        "  timeout_s: 30\n"
        "  max_response_tokens: 220\n"
        "  enable_thinking: false\n"
        "  sampling: {temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0,"
        " presence_penalty: 1.5, repeat_penalty: 1.0}\n"
        "ui: {host: '127.0.0.1', port: 8000}\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.llm.sampling.temperature == 0.7
    assert cfg.llm.sampling.presence_penalty == 1.5
    assert cfg.llm.max_response_tokens == 220
    assert cfg.llm.enable_thinking is False
    assert cfg.ui.port == 8000


def test_rejects_non_loopback_host(tmp_path: Path):
    (tmp_path / "default.yaml").write_text("ui: {host: '0.0.0.0', port: 8000}\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)
    assert "loopback" in str(exc.value).lower()


def test_rejects_out_of_range_temperature(tmp_path: Path):
    (tmp_path / "default.yaml").write_text(
        "llm:\n  sampling: {temperature: 3.5}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)
    assert "temperature" in str(exc.value)


def test_user_yaml_overrides_default(tmp_path: Path):
    (tmp_path / "default.yaml").write_text(
        "llm:\n  sampling: {temperature: 0.7}\nui: {port: 8000}\n", encoding="utf-8"
    )
    (tmp_path / "user.yaml").write_text("llm:\n  sampling: {temperature: 0.9}\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.llm.sampling.temperature == 0.9
    assert cfg.ui.port == 8000  # untouched key survives the merge


def test_missing_files_yield_defaults(tmp_path: Path):
    cfg = load_config(tmp_path)
    assert cfg.llm.sampling.presence_penalty == 1.5
    assert cfg.ui.host == "127.0.0.1"

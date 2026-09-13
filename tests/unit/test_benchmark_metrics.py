from __future__ import annotations

import pytest

from benchmarks.bm02_prefix_cache import build_payload, parse_sse_data
from benchmarks.bm03_cpu_speech_rtf import repeated_median
from benchmarks.bm05_echo_cancellation import evaluate
from benchmarks.metrics import (
    PrefixCacheVerdict,
    classify_prefix_cache,
    real_time_factor,
    word_error_rate,
)


def test_prefix_cache_requires_material_cached_advantage() -> None:
    verdict = classify_prefix_cache(
        cached_ttft_ms=[300.0, 320.0, 310.0],
        perturbed_ttft_ms=[700.0, 720.0, 710.0],
    )

    assert verdict is PrefixCacheVerdict.PASS


def test_prefix_cache_is_marginal_when_advantage_is_below_two_times() -> None:
    verdict = classify_prefix_cache(
        cached_ttft_ms=[300.0, 320.0, 310.0],
        perturbed_ttft_ms=[500.0, 520.0, 510.0],
    )

    assert verdict is PrefixCacheVerdict.MARGINAL


def test_real_time_factor_rejects_zero_audio_duration() -> None:
    with pytest.raises(ValueError, match="positive"):
        real_time_factor(wall_seconds=0.2, audio_seconds=0.0)


def test_word_error_rate_uses_word_level_edit_distance() -> None:
    assert word_error_rate("we should tax carbon", "we should tax") == pytest.approx(0.25)


def test_word_error_rate_treats_matching_empty_text_as_zero() -> None:
    assert word_error_rate("", "") == 0.0


def test_sse_parser_ignores_done_and_decodes_json_payloads() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"content":"hello"}}]}',
        b"",
        b"data: [DONE]",
    ]

    assert list(parse_sse_data(lines)) == [
        {"choices": [{"delta": {"content": "hello"}}]},
    ]


def test_bm02_disables_qwen_thinking_mode() -> None:
    payload = build_payload(
        model="qwen3.5-9b",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=50,
    )

    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_bm02_can_build_non_streaming_zero_token_prefill() -> None:
    payload = build_payload(
        model="qwen3.5-9b",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=0,
        stream=False,
    )

    assert payload["max_tokens"] == 0
    assert payload["stream"] is False


def test_bm03_discards_warmup_and_reports_repeated_median() -> None:
    values = iter([99.0, 3.0, 1.0, 2.0])

    measured = repeated_median(lambda: next(values), repeats=3)

    assert measured == 2.0


def test_bm05_requires_eighteen_preserved_double_talk_trials() -> None:
    trials = [
        {"reference": "address my actual argument", "hypothesis": "address my actual argument"}
        for _ in range(17)
    ]
    trials.extend({"reference": "address my actual argument", "hypothesis": ""} for _ in range(3))

    result = evaluate(
        {
            "self_triggers_typical": 0,
            "self_triggers_high": 0,
            "webrtc_rtt_ms": 40,
            "double_talk_trials": trials,
        }
    )

    assert result["preserved_trials"] == 17
    assert result["verdict"] == "FAIL"

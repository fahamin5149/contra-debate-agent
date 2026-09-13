from __future__ import annotations

import math
import re
import statistics
from collections.abc import Sequence
from enum import Enum

_NON_WORD = re.compile(r"[^\w']+", re.UNICODE)


class PrefixCacheVerdict(Enum):
    PASS = "PASS"
    MARGINAL = "MARGINAL"
    FAIL = "FAIL"


def _positive_finite(values: Sequence[float], name: str) -> list[float]:
    result = [float(value) for value in values]
    if not result or any(value <= 0 or not math.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain positive finite measurements")
    return result


def classify_prefix_cache(
    cached_ttft_ms: Sequence[float], perturbed_ttft_ms: Sequence[float]
) -> PrefixCacheVerdict:
    """Classify BM-02 using the documented two-times advantage threshold.

    A material advantage is a PASS only when the cached series is also stable:
    its last measurement may not exceed the first by more than 50 percent.
    """

    cached = _positive_finite(cached_ttft_ms, "cached_ttft_ms")
    perturbed = _positive_finite(perturbed_ttft_ms, "perturbed_ttft_ms")
    advantage = statistics.median(perturbed) / statistics.median(cached)
    growth = cached[-1] / cached[0]
    if advantage > 2.0 and growth <= 1.5:
        return PrefixCacheVerdict.PASS
    if advantage > 1.0 and growth <= 2.0:
        return PrefixCacheVerdict.MARGINAL
    return PrefixCacheVerdict.FAIL


def real_time_factor(wall_seconds: float, audio_seconds: float) -> float:
    if not math.isfinite(audio_seconds) or audio_seconds <= 0:
        raise ValueError("audio_seconds must be positive and finite")
    if not math.isfinite(wall_seconds) or wall_seconds < 0:
        raise ValueError("wall_seconds must be non-negative and finite")
    return wall_seconds / audio_seconds


def missed_service_windows(lateness_seconds: float, period_seconds: float) -> int:
    """Count complete service periods lost after a fixed scheduling deadline."""
    if not math.isfinite(period_seconds) or period_seconds <= 0:
        raise ValueError("period_seconds must be positive and finite")
    if not math.isfinite(lateness_seconds):
        raise ValueError("lateness_seconds must be finite")
    return max(0, math.floor(lateness_seconds / period_seconds))


def _words(text: str) -> list[str]:
    return [word for word in _NON_WORD.sub(" ", text.casefold()).split() if word]


def word_error_rate(reference: str, hypothesis: str) -> float:
    expected = _words(reference)
    actual = _words(hypothesis)
    if not expected:
        return 0.0 if not actual else 1.0

    previous = list(range(len(actual) + 1))
    for row, expected_word in enumerate(expected, start=1):
        current = [row]
        for column, actual_word in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected_word != actual_word),
                )
            )
        previous = current
    return previous[-1] / len(expected)

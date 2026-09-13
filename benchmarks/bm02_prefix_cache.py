"""BM-02: measure hybrid-attention prefix-cache effectiveness.

This script talks only to the loopback OpenAI-compatible llama.cpp endpoint and
does not import Contra application code. Start ``llama serve`` with the exact
BM-01 model/backend settings before running it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from benchmarks.metrics import classify_prefix_cache


@dataclass(frozen=True)
class Sample:
    turn: int
    prompt_chars: int
    ttft_ms: float
    wall_ms: float
    output_chars: int


def parse_sse_data(lines: Iterable[bytes]) -> Iterator[dict[str, Any]]:
    for raw in lines:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload or payload == "[DONE]":
            continue
        yield json.loads(payload)


def build_payload(
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    *,
    stream: bool = True,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": stream,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def _stream_completion(
    url: str, model: str, messages: list[dict[str, str]], max_tokens: int
) -> tuple[float, float, str]:
    body = json.dumps(build_payload(model, messages, max_tokens)).encode("utf-8")
    request = urllib.request.Request(
        f"{url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first = None
    pieces: list[str] = []
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            for event in parse_sse_data(response):
                choices = event.get("choices") or []
                if not choices:
                    continue
                text = choices[0].get("delta", {}).get("content") or ""
                if text and first is None:
                    first = time.perf_counter()
                pieces.append(text)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"llama.cpp endpoint unavailable at {url}: {exc}") from exc
    ended = time.perf_counter()
    if first is None:
        raise RuntimeError("completion returned no content; cannot measure TTFT")
    return (first - started) * 1000.0, (ended - started) * 1000.0, "".join(pieces)


def _conversation(system_prompt: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system_prompt}]


def _prefill(url: str, model: str, messages: list[dict[str, str]]) -> float:
    body = json.dumps(build_payload(model, messages, 0, stream=False)).encode("utf-8")
    request = urllib.request.Request(
        f"{url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            json.load(response)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"llama.cpp endpoint unavailable at {url}: {exc}") from exc
    return (time.perf_counter() - started) * 1000.0


def _prefill_probe(url: str, model: str) -> dict[str, float]:
    nonce = time.time_ns()
    common: list[dict[str, str]] = []
    for turn in range(1, 21):
        common.extend(
            [
                {"role": "user", "content": f"Turn {turn}: challenge congestion pricing."},
                {
                    "role": "assistant",
                    "content": "It can burden workers without practical transit alternatives.",
                },
            ]
        )
    baseline = [
        {"role": "system", "content": f"baseline-{nonce} concise debate partner"},
        *common,
        {"role": "user", "content": "Give one final objection."},
    ]
    prepared = [
        {"role": "system", "content": f"prefill-{nonce} concise debate partner"},
        *common,
        {"role": "user", "content": "Give one final objection."},
    ]
    baseline_ttft_ms, _, _ = _stream_completion(url, model, baseline, 10)
    prefill_wall_ms = _prefill(url, model, prepared)
    prefilled_ttft_ms, _, _ = _stream_completion(url, model, prepared, 10)
    return {
        "baseline_ttft_ms": baseline_ttft_ms,
        "prefill_wall_ms": prefill_wall_ms,
        "prefilled_ttft_ms": prefilled_ttft_ms,
        "ttft_speedup_ratio": baseline_ttft_ms / prefilled_ttft_ms,
    }


def _run_series(url: str, model: str, *, perturbed: bool, turns: int) -> list[Sample]:
    base_system = (
        "You are a concise offline debate partner. Challenge the user's reasoning, "
        "state uncertainty honestly, and answer in no more than three sentences."
    )
    messages = _conversation(base_system)
    samples: list[Sample] = []
    for turn in range(1, turns + 1):
        user = (
            f"Turn {turn}: defend the strongest objection to my proposal that cities "
            "should make all central streets car-free, while preserving prior context."
        )
        messages.append({"role": "user", "content": user})
        request_messages = [dict(message) for message in messages]
        if perturbed:
            request_messages[0]["content"] = f"{base_system} perturbation-{turn}"
        ttft_ms, wall_ms, reply = _stream_completion(url, model, request_messages, 50)
        samples.append(
            Sample(
                turn=turn,
                prompt_chars=sum(len(message["content"]) for message in request_messages),
                ttft_ms=ttft_ms,
                wall_ms=wall_ms,
                output_chars=len(reply),
            )
        )
        messages.append({"role": "assistant", "content": reply})
        print(
            f"{'perturbed' if perturbed else 'cached':9} turn={turn:02d} "
            f"ttft={ttft_ms:7.1f} ms wall={wall_ms:7.1f} ms",
            flush=True,
        )
    return samples


def run(url: str, model: str, turns: int) -> dict[str, Any]:
    cached = _run_series(url, model, perturbed=False, turns=turns)
    perturbed = _run_series(url, model, perturbed=True, turns=turns)
    cached_ttft = [sample.ttft_ms for sample in cached]
    perturbed_ttft = [sample.ttft_ms for sample in perturbed]
    verdict = classify_prefix_cache(cached_ttft, perturbed_ttft)
    return {
        "url": url,
        "model": model,
        "turns": turns,
        "cached": [asdict(sample) for sample in cached],
        "perturbed": [asdict(sample) for sample in perturbed],
        "cached_median_ttft_ms": statistics.median(cached_ttft),
        "perturbed_median_ttft_ms": statistics.median(perturbed_ttft),
        "advantage_ratio": statistics.median(perturbed_ttft) / statistics.median(cached_ttft),
        "speculative_prefill": _prefill_probe(url, model),
        "verdict": verdict.value,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model", default="qwen3.5-9b")
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if args.turns < 3:
        parser.error("--turns must be at least 3")

    result = run(args.url, args.model, args.turns)
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""BM-03: measure CPU speech stages while llama.cpp keeps the GPU busy."""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import statistics
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import onnx_asr
import onnxruntime as ort
import soundfile as sf
from kokoro_onnx import Kokoro

from benchmarks.metrics import real_time_factor


def repeated_median(measure: Callable[[], float], repeats: int = 3) -> float:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    measure()
    return statistics.median(measure() for _ in range(repeats))


def _llm_load(url: str, stop: threading.Event) -> None:
    endpoint = f"{url.rstrip('/')}/chat/completions"
    while not stop.is_set():
        payload = json.dumps(
            {
                "model": "qwen3.5-9b",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "List detailed objections to congestion pricing without stopping."
                        ),
                    }
                ],
                "max_tokens": 500,
                "stream": True,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode()
        request = urllib.request.Request(
            endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
                while not stop.is_set() and response.readline():
                    pass
        except Exception as exc:  # benchmark must surface load failures in its report
            print(f"GPU load request failed: {exc}", flush=True)
            stop.set()


async def _measure_with_ticker(operation: Any) -> tuple[float, int]:
    intervals: list[float] = []
    done = asyncio.Event()

    async def ticker() -> None:
        previous = time.perf_counter()
        while not done.is_set():
            await asyncio.sleep(0.02)
            now = time.perf_counter()
            intervals.append(now - previous)
            previous = now

    task = asyncio.create_task(ticker())
    started = time.perf_counter()
    try:
        await asyncio.to_thread(operation)
    finally:
        elapsed = time.perf_counter() - started
        done.set()
        await task
    dropped = sum(max(0, round(interval / 0.02) - 1) for interval in intervals if interval > 0.03)
    return elapsed, dropped


def _session_options(threads: int) -> ort.SessionOptions:
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    return options


def _load_stt(model_dir: Path, threads: int) -> Any:
    return onnx_asr.load_model(
        "nemo-conformer-tdt",
        str(model_dir),
        quantization="int8",
        sess_options=_session_options(threads),
        providers=["CPUExecutionProvider"],
    )


def _load_kokoro(model_path: Path, voices_path: Path, threads: int) -> Kokoro:
    kokoro = Kokoro(str(model_path), str(voices_path))
    kokoro.sess = ort.InferenceSession(
        str(model_path),
        sess_options=_session_options(threads),
        providers=["CPUExecutionProvider"],
    )
    return kokoro


def _speech_fixture(kokoro: Kokoro, seconds: float) -> np.ndarray:
    text = (
        "Cities should price scarce road space because congestion imposes costs on everyone. "
        "However, any policy must protect low income workers and people with limited alternatives."
    )
    samples, rate = kokoro.create(text, "af_heart", 1.0, "en-us")
    waveform = np.asarray(samples, dtype=np.float32)
    required = round(seconds * rate)
    tiled = np.resize(waveform, required)
    if rate != 16_000:
        positions = np.linspace(0, len(tiled) - 1, round(len(tiled) * 16_000 / rate))
        tiled = np.interp(positions, np.arange(len(tiled)), tiled).astype(np.float32)
    return tiled


async def run(args: argparse.Namespace) -> dict[str, Any]:
    fixture_kokoro = Kokoro(str(args.kokoro_model), str(args.voices))
    speech = {seconds: _speech_fixture(fixture_kokoro, seconds) for seconds in (5.0, 20.0)}
    del fixture_kokoro
    gc.collect()
    silence, silence_rate = sf.read(args.silence, dtype="float32")
    if silence_rate != 16_000:
        raise RuntimeError(f"silence fixture must be 16 kHz, got {silence_rate}")

    stop = threading.Event()
    load_thread = threading.Thread(target=_llm_load, args=(args.url, stop), daemon=True)
    load_thread.start()
    await asyncio.sleep(0.5)
    results: dict[str, Any] = {"threads": {}, "llm_url": args.url}
    try:
        for threads in args.threads:
            print(f"Loading Parakeet with {threads} threads...", flush=True)
            stt = await asyncio.to_thread(_load_stt, args.parakeet, threads)
            kokoro = await asyncio.to_thread(_load_kokoro, args.kokoro_model, args.voices, threads)
            thread_result: dict[str, Any] = {"stt": {}, "tts": {}, "dropped_frames": 0}
            await asyncio.to_thread(stt.recognize, speech[5.0])
            await asyncio.to_thread(
                kokoro.create,
                "That argument ignores the cost imposed here.",
                "af_heart",
                1.0,
                "en-us",
            )
            for seconds, waveform in speech.items():
                measurements = [
                    await _measure_with_ticker(lambda w=waveform, model=stt: model.recognize(w))
                    for _ in range(args.repeats)
                ]
                elapsed = statistics.median(item[0] for item in measurements)
                dropped = max(item[1] for item in measurements)
                thread_result["stt"][f"{int(seconds)}s"] = {
                    "wall_ms": elapsed * 1000,
                    "rtf": real_time_factor(elapsed, seconds),
                }
                thread_result["dropped_frames"] += dropped

            holder: dict[str, str] = {}

            def recognize_silence(model: Any = stt, target: dict[str, str] = holder) -> None:
                target["text"] = (
                    model.recognize(np.asarray(silence, dtype=np.float32)) or ""
                ).strip()

            measurements = [
                await _measure_with_ticker(recognize_silence) for _ in range(args.repeats)
            ]
            elapsed = statistics.median(item[0] for item in measurements)
            dropped = max(item[1] for item in measurements)
            thread_result["silence"] = {
                "wall_ms": elapsed * 1000,
                "words": len(holder["text"].split()),
            }
            thread_result["dropped_frames"] += dropped

            for label, text in {
                "15_chars": "That misses costs",
                "40_chars": "That argument ignores the cost imposed here.",
                "120_chars": (
                    "That proposal sounds fair at first, but it shifts hidden costs onto people "
                    "with the fewest practical alternatives."
                ),
            }.items():
                generated: dict[str, Any] = {}

                def synthesize(
                    value: str = text,
                    output: dict[str, Any] = generated,
                    engine: Kokoro = kokoro,
                ) -> None:
                    output["samples"], output["rate"] = engine.create(
                        value, "af_heart", 1.0, "en-us"
                    )

                measurements = [await _measure_with_ticker(synthesize) for _ in range(args.repeats)]
                elapsed = statistics.median(item[0] for item in measurements)
                dropped = max(item[1] for item in measurements)
                duration = len(generated["samples"]) / generated["rate"]
                thread_result["tts"][label] = {
                    "wall_ms": elapsed * 1000,
                    "audio_ms": duration * 1000,
                    "rtf": real_time_factor(elapsed, duration),
                }
                thread_result["dropped_frames"] += dropped

            if args.smart_turn.exists():
                session = ort.InferenceSession(
                    str(args.smart_turn),
                    sess_options=_session_options(threads),
                    providers=["CPUExecutionProvider"],
                )
                feature = np.zeros((1, 80, 800), dtype=np.float32)
                input_name = session.get_inputs()[0].name

                def measure_turn(
                    model: ort.InferenceSession = session,
                    name: str = input_name,
                    inputs: np.ndarray = feature,
                ) -> float:
                    started = time.perf_counter()
                    model.run(None, {name: inputs})
                    return (time.perf_counter() - started) * 1000

                thread_result["turn_detection_ms"] = repeated_median(
                    measure_turn, repeats=args.repeats
                )
            results["threads"][str(threads)] = thread_result
            del stt, kokoro
            if args.smart_turn.exists():
                del session
            gc.collect()
    finally:
        stop.set()
        load_thread.join(timeout=5)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--parakeet", type=Path, default=Path("models/parakeet-tdt-0.6b-v3-onnx"))
    parser.add_argument("--kokoro-model", type=Path, default=Path("models/kokoro-v1.0.onnx"))
    parser.add_argument("--voices", type=Path, default=Path("models/voices-v1.0.bin"))
    parser.add_argument("--smart-turn", type=Path, default=Path("models/smart-turn-v3.2-cpu.onnx"))
    parser.add_argument("--silence", type=Path, default=Path("tests/fixtures/audio/silence.wav"))
    parser.add_argument("--threads", type=int, nargs="+", default=[4, 6, 8])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

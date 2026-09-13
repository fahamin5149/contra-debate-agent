"""BM-03: measure CPU speech stages while llama.cpp keeps the GPU busy."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import os
import statistics
import threading
import time
import urllib.request
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import onnx_asr
import onnxruntime as ort
import soundfile as sf
from kokoro_onnx import Kokoro

from benchmarks.metrics import missed_service_windows, real_time_factor
from benchmarks.subprocess_worker import BenchmarkProcess, build_affinity_mask


@contextmanager
def _windows_timer_resolution(period_ms: int) -> Any:
    if os.name != "nt" or period_ms == 0:
        yield
        return
    winmm = ctypes.WinDLL("winmm", use_last_error=True)
    if winmm.timeBeginPeriod(period_ms) != 0:
        raise RuntimeError(f"could not request {period_ms} ms Windows timer resolution")
    try:
        yield
    finally:
        winmm.timeEndPeriod(period_ms)


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


async def _measure_awaitable_with_ticker(
    operation: Callable[[], Awaitable[Any]],
) -> tuple[float, int, Any]:
    done = asyncio.Event()
    missed = 0

    async def ticker() -> None:
        nonlocal missed
        period = 0.02
        deadline = time.perf_counter() + period
        while not done.is_set():
            await asyncio.sleep(max(0.0, deadline - time.perf_counter()))
            now = time.perf_counter()
            lost = missed_service_windows(now - deadline, period)
            missed += lost
            deadline += (lost + 1) * period

    task = asyncio.create_task(ticker())
    started = time.perf_counter()
    try:
        result = await operation()
    finally:
        elapsed = time.perf_counter() - started
        done.set()
        await task
    return elapsed, missed, result


async def _measure_with_ticker(operation: Any) -> tuple[float, int]:
    elapsed, dropped, _ = await _measure_awaitable_with_ticker(lambda: asyncio.to_thread(operation))
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


async def _measure_subprocesses(
    args: argparse.Namespace,
    threads: int,
    speech: dict[float, np.ndarray[Any, Any]],
    silence: np.ndarray[Any, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {"stt": {}, "tts": {}, "dropped_frames": 0}
    affinity_mask = None
    if args.reserve_logical_cpus:
        affinity_mask = build_affinity_mask(os.cpu_count() or 1, tuple(args.reserve_logical_cpus))

    stt = BenchmarkProcess(
        "stt",
        {
            "model_dir": str(args.parakeet),
            "threads": threads,
            "affinity_mask": affinity_mask,
        },
    )
    await stt.start()
    try:
        await stt.call("recognize", speech[5.0].astype(np.float32, copy=False).tobytes())
        for seconds, waveform in speech.items():
            payload = waveform.astype(np.float32, copy=False).tobytes()
            measurements = [
                await _measure_awaitable_with_ticker(partial(stt.call, "recognize", payload))
                for _ in range(args.repeats)
            ]
            elapsed = statistics.median(item[0] for item in measurements)
            dropped = max(item[1] for item in measurements)
            result["stt"][f"{int(seconds)}s"] = {
                "wall_ms": elapsed * 1000,
                "rtf": real_time_factor(elapsed, seconds),
                "missed_service_windows": dropped,
            }
            result["dropped_frames"] += dropped

        silence_payload = np.asarray(silence, dtype=np.float32).tobytes()
        measurements = [
            await _measure_awaitable_with_ticker(lambda: stt.call("recognize", silence_payload))
            for _ in range(args.repeats)
        ]
        elapsed = statistics.median(item[0] for item in measurements)
        dropped = max(item[1] for item in measurements)
        transcript = str(measurements[-1][2])
        result["silence"] = {
            "wall_ms": elapsed * 1000,
            "words": len(transcript.split()),
            "missed_service_windows": dropped,
        }
        result["dropped_frames"] += dropped
    finally:
        await stt.aclose()

    tts_kind = args.tts_engine
    tts_config: dict[str, Any] = {
        "threads": threads,
        "affinity_mask": affinity_mask,
    }
    if tts_kind == "kokoro":
        tts_config.update(
            {
                "model_path": str(args.kokoro_model),
                "voices_path": str(args.voices),
                "voice": "af_heart",
                "speed": 1.0,
            }
        )
        worker_kind = "tts"
    else:
        tts_config["model_path"] = str(args.piper_model)
        worker_kind = "piper"
    tts = BenchmarkProcess(worker_kind, tts_config)
    await tts.start()
    try:
        await tts.call("synthesize", b"That argument ignores the cost imposed here.")
        for label, text_value in {
            "15_chars": "That misses it.",
            "40_chars": "That argument ignores the cost imposed here.",
            "120_chars": (
                "That proposal sounds fair at first, but it shifts hidden costs onto people "
                "with the fewest practical alternatives."
            ),
        }.items():
            payload = text_value.encode("utf-8")
            measurements = [
                await _measure_awaitable_with_ticker(partial(tts.call, "synthesize", payload))
                for _ in range(args.repeats)
            ]
            elapsed = statistics.median(item[0] for item in measurements)
            dropped = max(item[1] for item in measurements)
            pcm, rate = measurements[-1][2]
            duration = len(pcm) / np.dtype(np.int16).itemsize / rate
            result["tts"][label] = {
                "wall_ms": elapsed * 1000,
                "audio_ms": duration * 1000,
                "rtf": real_time_factor(elapsed, duration),
                "missed_service_windows": dropped,
            }
            result["dropped_frames"] += dropped
    finally:
        await tts.aclose()

    if args.smart_turn.exists():
        turn = BenchmarkProcess(
            "turn",
            {
                "model_path": str(args.smart_turn),
                "threads": threads,
                "affinity_mask": affinity_mask,
            },
        )
        await turn.start()
        try:
            feature = np.zeros((1, 80, 800), dtype=np.float32).tobytes()
            await turn.call("evaluate", feature)
            measurements = [
                await _measure_awaitable_with_ticker(lambda: turn.call("evaluate", feature))
                for _ in range(args.repeats)
            ]
            dropped = max(item[1] for item in measurements)
            result["turn_detection_ms"] = statistics.median(item[0] * 1000 for item in measurements)
            result["turn_detection_missed_service_windows"] = dropped
            result["dropped_frames"] += dropped
        finally:
            await turn.aclose()
    return result


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
    results: dict[str, Any] = {
        "threads": {},
        "llm_url": args.url,
        "isolation": args.isolation,
        "reserved_logical_cpus": args.reserve_logical_cpus,
        "tts_engine": args.tts_engine,
        "windows_timer_resolution_ms": args.windows_timer_resolution_ms,
    }
    try:
        for threads in args.threads:
            if args.isolation == "subprocess":
                print(f"Measuring spawned workers with {threads} threads...", flush=True)
                results["threads"][str(threads)] = await _measure_subprocesses(
                    args, threads, speech, np.asarray(silence, dtype=np.float32)
                )
                gc.collect()
                continue
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
                    "missed_service_windows": dropped,
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
                "missed_service_windows": dropped,
            }
            thread_result["dropped_frames"] += dropped

            for label, text in {
                "15_chars": "That misses it.",
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
                    "missed_service_windows": dropped,
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
    parser.add_argument(
        "--piper-model",
        type=Path,
        default=Path("models/piper/en_US-lessac-medium.onnx"),
    )
    parser.add_argument("--smart-turn", type=Path, default=Path("models/smart-turn-v3.2-cpu.onnx"))
    parser.add_argument("--silence", type=Path, default=Path("tests/fixtures/audio/silence.wav"))
    parser.add_argument("--threads", type=int, nargs="+", default=[4, 6, 8])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--isolation", choices=["thread", "subprocess"], default="thread")
    parser.add_argument("--tts-engine", choices=["kokoro", "piper"], default="kokoro")
    parser.add_argument("--reserve-logical-cpus", type=int, nargs="*", default=[])
    parser.add_argument("--windows-timer-resolution-ms", type=int, choices=[0, 1], default=1)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if args.tts_engine == "piper" and args.isolation != "subprocess":
        parser.error("Piper is available only with --isolation subprocess")
    with _windows_timer_resolution(args.windows_timer_resolution_ms):
        result = asyncio.run(run(args))
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

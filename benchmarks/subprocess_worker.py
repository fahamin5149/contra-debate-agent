"""Spawned, model-owning workers used to validate the BM-03 mitigation."""

from __future__ import annotations

import asyncio
import ctypes
import multiprocessing
import os
import queue
from ctypes import wintypes
from dataclasses import dataclass
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from typing import Any


class WorkerFailure(RuntimeError):
    """A benchmark worker could not load a model or complete an operation."""


def build_affinity_mask(logical_cpu_count: int, reserved: tuple[int, ...]) -> int:
    if logical_cpu_count < 1 or logical_cpu_count > 64:
        raise ValueError("logical_cpu_count must be between 1 and 64")
    if any(cpu < 0 or cpu >= logical_cpu_count for cpu in reserved):
        raise ValueError("reserved CPU index is out of range")
    mask = (1 << logical_cpu_count) - 1
    for cpu in reserved:
        mask &= ~(1 << cpu)
    if mask == 0:
        raise ValueError("at least one logical CPU must remain available")
    return mask


def _apply_affinity(mask: int | None) -> None:
    if mask is None:
        return
    if os.name != "nt":
        raise RuntimeError("processor affinity probe is implemented for Windows only")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    kernel32.SetProcessAffinityMask.restype = wintypes.BOOL
    current_process = kernel32.GetCurrentProcess()
    if not kernel32.SetProcessAffinityMask(current_process, ctypes.c_size_t(mask)):
        raise ctypes.WinError(ctypes.get_last_error())


@dataclass(frozen=True)
class Request:
    request_id: int
    operation: str
    payload: bytes


@dataclass(frozen=True)
class Response:
    request_id: int
    ok: bool
    payload: Any


def _session_options(threads: int) -> Any:
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    return options


def _load_model(kind: str, config: dict[str, Any]) -> Any:
    if kind == "echo":
        return None
    if kind == "stt":
        import onnx_asr

        return onnx_asr.load_model(
            "nemo-conformer-tdt",
            config["model_dir"],
            quantization="int8",
            sess_options=_session_options(config["threads"]),
            providers=["CPUExecutionProvider"],
        )
    if kind == "tts":
        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        engine = Kokoro(config["model_path"], config["voices_path"])
        engine.sess = ort.InferenceSession(
            config["model_path"],
            sess_options=_session_options(config["threads"]),
            providers=["CPUExecutionProvider"],
        )
        return engine
    if kind == "piper":
        from piper import PiperVoice

        return PiperVoice.load(config["model_path"], use_cuda=False)
    if kind == "turn":
        import onnxruntime as ort

        return ort.InferenceSession(
            config["model_path"],
            sess_options=_session_options(config["threads"]),
            providers=["CPUExecutionProvider"],
        )
    raise ValueError(f"unsupported worker kind: {kind}")


def _execute(kind: str, model: Any, request: Request, config: dict[str, Any]) -> Any:
    if kind == "echo":
        if request.operation != "echo":
            raise ValueError(f"unsupported echo operation: {request.operation}")
        return request.payload
    if kind == "stt":
        import numpy as np

        if request.operation != "recognize":
            raise ValueError(f"unsupported STT operation: {request.operation}")
        waveform = np.frombuffer(request.payload, dtype=np.float32)
        return (model.recognize(waveform) or "").strip()
    if kind == "tts":
        import numpy as np

        if request.operation != "synthesize":
            raise ValueError(f"unsupported TTS operation: {request.operation}")
        samples, rate = model.create(
            request.payload.decode("utf-8"),
            config["voice"],
            config["speed"],
            "en-us",
        )
        waveform = (np.clip(np.asarray(samples), -1.0, 1.0) * 32767).astype(np.int16)
        return waveform.tobytes(), int(rate)
    if kind == "piper":
        if request.operation != "synthesize":
            raise ValueError(f"unsupported Piper operation: {request.operation}")
        chunks = list(model.synthesize(request.payload.decode("utf-8")))
        if not chunks:
            return b"", int(model.config.sample_rate)
        rate = int(chunks[0].sample_rate)
        if any(int(chunk.sample_rate) != rate for chunk in chunks):
            raise ValueError("Piper returned inconsistent sample rates")
        return b"".join(chunk.audio_int16_bytes for chunk in chunks), rate
    if kind == "turn":
        import numpy as np

        if request.operation != "evaluate":
            raise ValueError(f"unsupported turn operation: {request.operation}")
        feature = np.frombuffer(request.payload, dtype=np.float32).reshape(1, 80, 800)
        input_name = model.get_inputs()[0].name
        output = model.run(None, {input_name: feature})
        return np.asarray(output[0]).tobytes()
    raise ValueError(f"unsupported worker kind: {kind}")


def _worker_main(
    kind: str,
    config: dict[str, Any],
    requests: Any,
    responses: Any,
) -> None:
    try:
        _apply_affinity(config.get("affinity_mask"))
        model = _load_model(kind, config)
    except Exception as exc:
        responses.put(Response(-1, False, f"model load failed: {type(exc).__name__}: {exc}"))
        return
    responses.put(Response(-1, True, "ready"))
    while True:
        request = requests.get()
        if request is None:
            return
        try:
            payload = _execute(kind, model, request, config)
            responses.put(Response(request.request_id, True, payload))
        except Exception as exc:
            responses.put(Response(request.request_id, False, f"{type(exc).__name__}: {exc}"))


class BenchmarkProcess:
    """A serial spawned worker used only by the standalone benchmark harness."""

    def __init__(self, kind: str, config: dict[str, Any], timeout_s: float = 300.0) -> None:
        self._kind = kind
        self._config = dict(config)
        self._timeout_s = timeout_s
        self._context: SpawnContext = multiprocessing.get_context("spawn")
        self._requests = self._context.Queue(maxsize=1)
        self._responses = self._context.Queue(maxsize=1)
        self._process: BaseProcess | None = None
        self._lock = asyncio.Lock()
        self._next_id = 0
        self._closed = False

    @property
    def process(self) -> BaseProcess | None:
        return self._process

    @property
    def start_method(self) -> str:
        return self._context.get_start_method()

    async def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("worker already started")
        self._process = self._context.Process(
            target=_worker_main,
            args=(self._kind, self._config, self._requests, self._responses),
            daemon=True,
        )
        self._process.start()
        response = await self._receive()
        if not response.ok:
            await self.aclose()
            raise WorkerFailure(str(response.payload))

    async def call(self, operation: str, payload: bytes) -> Any:
        if self._closed or self._process is None:
            raise RuntimeError("worker is not running")
        async with self._lock:
            request_id = self._next_id
            self._next_id += 1
            request = Request(request_id, operation, bytes(payload))
            await asyncio.to_thread(self._requests.put, request, True, self._timeout_s)
            response = await self._receive()
            if response.request_id != request_id:
                raise WorkerFailure(
                    f"response ID {response.request_id} did not match request {request_id}"
                )
            if not response.ok:
                raise WorkerFailure(str(response.payload))
            return response.payload

    async def _receive(self) -> Response:
        try:
            return await asyncio.to_thread(self._responses.get, True, self._timeout_s)
        except queue.Empty as exc:
            raise WorkerFailure(f"worker timed out after {self._timeout_s:g}s") from exc

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is None:
            return
        if process.is_alive():
            try:
                await asyncio.to_thread(self._requests.put, None, True, 1.0)
            except queue.Full:
                pass
            await asyncio.to_thread(process.join, 5.0)
        if process.is_alive():
            process.terminate()
            await asyncio.to_thread(process.join, 5.0)
        self._requests.close()
        self._responses.close()
        self._requests.join_thread()
        self._responses.join_thread()

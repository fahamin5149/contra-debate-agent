from __future__ import annotations

import asyncio
import os

import pytest

from benchmarks.subprocess_worker import BenchmarkProcess, WorkerFailure, build_affinity_mask


def test_affinity_mask_reserves_capture_processors() -> None:
    assert build_affinity_mask(logical_cpu_count=8, reserved=(0, 1)) == 0b11111100


async def test_echo_worker_returns_bytes_across_spawn_boundary() -> None:
    worker = BenchmarkProcess("echo", {})
    await worker.start()
    try:
        assert await worker.call("echo", b"payload") == b"payload"
    finally:
        await worker.aclose()


@pytest.mark.skipif(os.name != "nt", reason="Windows affinity contract")
async def test_echo_worker_applies_windows_affinity() -> None:
    mask = build_affinity_mask(os.cpu_count() or 1, (0, 1))
    worker = BenchmarkProcess("echo", {"affinity_mask": mask})
    await worker.start()
    try:
        assert await worker.call("echo", b"affined") == b"affined"
    finally:
        await worker.aclose()


async def test_worker_surfaces_child_errors_without_hanging() -> None:
    worker = BenchmarkProcess("echo", {})
    await worker.start()
    try:
        with pytest.raises(WorkerFailure, match="unsupported echo operation"):
            await worker.call("unknown", b"")
    finally:
        await worker.aclose()


async def test_worker_shutdown_joins_spawned_process() -> None:
    worker = BenchmarkProcess("echo", {})
    await worker.start()
    process = worker.process

    await worker.aclose()

    assert process is not None
    assert not await asyncio.to_thread(process.is_alive)
    assert worker.start_method == "spawn"

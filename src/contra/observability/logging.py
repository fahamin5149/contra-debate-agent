from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

__all__ = ["setup_logging", "get_logger"]


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging.

    Never log transcript content above DEBUG (NFR-S-01): log files are less
    protected than the database and are the thing most likely to be pasted
    into a bug report. Log lengths, confidences, and IDs — not text.
    """
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)

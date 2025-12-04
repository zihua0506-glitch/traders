"""Centralized configuration for logging, constants, env keys, and perf sampling.

Implements cross-module config per Tasks 23-25:
- Unified logging level/format
- Centralized model/concurrency/timeout constants
- Environment variable reading for `OPENAI_API_KEY` (safe skip when missing)
- Lightweight performance sampling at 300-scale (average LLM latency, total time)

All code, identifiers, and strings are in English per repo guidelines.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, Optional


# -----------------------------
# Logging configuration (Task 23)
# -----------------------------

LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    """Configure root logger once with unified level and format."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)


# -----------------------------
# Constants (Task 23)
# -----------------------------

# LLM model + runtime parameters
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMPERATURE = 0.0
MAX_TOKENS = 120
TIMEOUT_S = 10
MAX_INPUT_CHARS = 1200

# Concurrency for LLM analysis
MAX_PARALLEL_LLM = int(os.getenv("MAX_PARALLEL_LLM", "8"))


# -----------------------------
# Env keys (Task 24)
# -----------------------------

OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY") or None


# -----------------------------
# Performance sampling (Task 25)
# -----------------------------

_perf_lock = threading.Lock()
_perf_sample_started = False
_perf_sample_limit = 0
_perf_attempts = 0
_perf_failures = 0
_perf_latencies: list[float] = []
_perf_t0 = 0.0
_perf_t1 = 0.0


def perf_start_sample(limit: int = 300) -> None:
    """Start a performance sampling window for up to `limit` LLM attempts.

    Records wall-clock start time and resets counters.
    """
    global _perf_sample_started, _perf_sample_limit, _perf_attempts, _perf_failures
    global _perf_latencies, _perf_t0, _perf_t1
    with _perf_lock:
        _perf_sample_started = True
        _perf_sample_limit = max(0, int(limit))
        _perf_attempts = 0
        _perf_failures = 0
        _perf_latencies = []
        _perf_t0 = time.perf_counter()
        _perf_t1 = 0.0


def record_llm_latency(seconds: float, succeeded: bool) -> None:
    """Record one LLM attempt latency and success status.

    Stops the sampling window automatically once attempts reach the limit.
    Thread-safe for calls from worker threads.
    """
    global _perf_attempts, _perf_failures, _perf_t1
    if seconds < 0:
        seconds = 0.0
    with _perf_lock:
        if not _perf_sample_started:
            return
        if _perf_sample_limit and _perf_attempts >= _perf_sample_limit:
            return
        _perf_attempts += 1
        if not succeeded:
            _perf_failures += 1
        _perf_latencies.append(float(seconds))
        if _perf_sample_limit and _perf_attempts >= _perf_sample_limit:
            _perf_t1 = time.perf_counter()


def get_perf_stats() -> Dict[str, float]:
    """Return current performance stats as a dictionary.

    Includes average latency (seconds), total wall time (seconds) for the
    sampling window, total attempts, and failure ratio.
    """
    with _perf_lock:
        attempts = _perf_attempts
        failures = _perf_failures
        avg_latency = sum(_perf_latencies) / attempts if attempts > 0 else 0.0
        if _perf_t1 and _perf_t0 and _perf_t1 >= _perf_t0:
            wall_time = _perf_t1 - _perf_t0
        else:
            wall_time = 0.0
        failure_ratio = (failures / attempts) if attempts > 0 else 0.0
        return {
            "avg_latency_s": round(avg_latency, 4),
            "total_wall_time_s": round(wall_time, 4),
            "attempts": float(attempts),
            "failure_ratio": round(failure_ratio, 4),
        }


__all__ = [
    # logging
    "configure_logging",
    # constants
    "OPENAI_MODEL",
    "TEMPERATURE",
    "MAX_TOKENS",
    "TIMEOUT_S",
    "MAX_INPUT_CHARS",
    "MAX_PARALLEL_LLM",
    # env
    "OPENAI_API_KEY",
    # perf
    "perf_start_sample",
    "record_llm_latency",
    "get_perf_stats",
]

"""Logging: one log line per source call with time taken and success/failure."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from config.settings import LOG_DIR

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s")
    root = logging.getLogger("dashboard")
    root.setLevel(level)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    file_handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(console)
    root.addHandler(file_handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"dashboard.{name}")


_call_log = get_logger("calls")


@contextmanager
def log_call(source: str, what: str):
    """Usage: `with log_call("SEC EDGAR", "submissions AAPL"): ...`"""
    start = time.perf_counter()
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - we re-raise after logging
        ms = (time.perf_counter() - start) * 1000
        _call_log.warning("%s | %s | FAIL in %.0f ms | %s: %s",
                          source, what, ms, type(exc).__name__, exc)
        raise
    else:
        ms = (time.perf_counter() - start) * 1000
        _call_log.info("%s | %s | OK in %.0f ms", source, what, ms)

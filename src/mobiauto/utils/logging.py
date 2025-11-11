from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

_LOG_DIR = Path("artifacts/logs")
_FRAMEWORK_LOG = _LOG_DIR / "framework.log"

# Context keys that will be automatically included into log records
_CONTEXT_KEYS = ("platform", "device", "test", "session_id")


def _ensure_log_dir() -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _level_from_env() -> int:
    """Get log level from MOBIAUTO_LOG_LEVEL (TRACE|DEBUG|INFO|WARNING|ERROR)."""
    import logging

    raw = os.getenv("MOBIAUTO_LOG_LEVEL", "INFO").upper()
    if raw == "TRACE":
        # Level below DEBUG — use numeric value less than DEBUG
        return 5
    return getattr(logging, raw, logging.INFO)


_file_lock = threading.RLock()


def _copy_event_to_message(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    # For consistency add "message" field as a copy of standard "event" field
    if "event" in event_dict and "message" not in event_dict:
        event_dict["message"] = event_dict["event"]
    return event_dict


def _drop_none_values(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    return {k: v for k, v in event_dict.items() if v is not None}


def _file_sink_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """
    Processor that duplicates log records into files:
    - artifacts/logs/framework.log      — all events
    - artifacts/logs/test_<name>.log    — events for the current test (if test context is present)
    """
    _ensure_log_dir()

    # Prepare JSON line once so we can write the same data to both files
    line = json.dumps(event_dict, ensure_ascii=False)

    test_name = event_dict.get("test") or event_dict.get("test_name")
    test_path = None
    if isinstance(test_name, str) and test_name:
        safe = test_name.replace(os.sep, "_").replace("/", "_").replace(" ", "_").replace(":", "_")
        test_path = _LOG_DIR / f"test_{safe}.log"

    try:
        with _file_lock:
            with _FRAMEWORK_LOG.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            if test_path is not None:
                with Path(test_path).open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
    except Exception:
        # Never break execution because of log write issues
        pass

    return event_dict


def current_test_log_path(test_name: str | None = None) -> Path:
    """
    Return path to the current test log file (or the expected one), if its name is known.

    If test_name is not provided, returns the common framework log file path.
    """
    _ensure_log_dir()
    if not test_name:
        return _FRAMEWORK_LOG

    safe = str(test_name).replace(os.sep, "_").replace("/", "_").replace(" ", "_").replace(":", "_")
    return _LOG_DIR / f"test_{safe}.log"


def bind_context(
    *,
    settings: Any | None = None,
    driver: Any | None = None,
    test_name: str | None = None,
) -> None:
    """
    Bind platform/device/test/session info into the logging context.

    This data is then automatically included in all structured log records.
    """
    platform = None
    device = None
    session_id = None

    try:
        if settings is not None:
            platform = getattr(settings, "platform", None)
            if platform == "android" and getattr(settings, "android", None):
                device = getattr(settings.android, "device_name", None)
            elif platform == "ios" and getattr(settings, "ios", None):
                device = getattr(settings.ios, "device_name", None)
    except Exception:
        pass

    try:
        if driver is not None:
            session_id = getattr(driver, "session_id", None)
    except Exception:
        pass

    bind_contextvars(platform=platform, device=device, test=test_name, session_id=session_id)


_CONFIGURED = False


def setup_logging() -> None:
    """
    Centralized setup of structured logging with JSON output and file duplication.

    Includes:
    - Log level from MOBIAUTO_LOG_LEVEL
    - ISO 8601 timestamp (key: "timestamp")
    - Context (platform, device, test, session_id) via contextvars
    - Duplication of each record into:
        artifacts/logs/framework.log
        artifacts/logs/test_<name>.log
    - Unified JSON format printed to stdout (compatible with existing unit tests)
    """
    import logging

    global _CONFIGURED
    if _CONFIGURED:
        return

    _ensure_log_dir()

    level = _level_from_env()

    structlog.configure(
        processors=[
            merge_contextvars,  # Automatically include bound context
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.CallsiteParameterAdder(
                [structlog.processors.CallsiteParameter.MODULE]
            ),
            _copy_event_to_message,
            _drop_none_values,
            _file_sink_processor,  # Duplicate record into log file(s)
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),  # output to stdout (test-friendly)
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    # Sync root logging level (for third-party libraries)
    logging.getLogger().setLevel(level)

    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    """
    Get a structlog logger instance.

    Ensures logging is configured even in plain unit-test runs without the pytest plugin.
    """
    if not globals().get("_CONFIGURED", False):
        try:
            setup_logging()
        except Exception:
            # Do not interfere with execution if configuration fails
            pass
    return structlog.get_logger(name or __name__)


__all__ = [
    "setup_logging",
    "bind_context",
    "current_test_log_path",
    "get_logger",
    "clear_contextvars",
]

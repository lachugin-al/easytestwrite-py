from __future__ import annotations

import json

import pytest
import structlog

from mobiauto.utils.logging import setup_logging


def test_setup_logging_produces_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Configure logging and verify that structlog outputs JSON via JSONRenderer."""
    setup_logging()
    log = structlog.get_logger()
    log.info("hello", foo=123)

    out = capsys.readouterr().out.strip()
    # structlog.PrintLoggerFactory writes a JSON string to stdout
    data = json.loads(out)
    # Verify keys added by processors
    assert data["event"] == "hello"
    assert data["level"] in ("info", "INFO")
    # TimeStamper adds a timestamp by default
    assert "timestamp" in data or "time" in data
    assert data["foo"] == 123

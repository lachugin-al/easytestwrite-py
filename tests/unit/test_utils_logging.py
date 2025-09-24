from __future__ import annotations

import json

import pytest
import structlog

from mobiauto.utils.logging import setup_logging


def test_setup_logging_produces_json(capsys: pytest.CaptureFixture[str]) -> None:
    # Настроим логирование и проверим, что вывод - JSON от JSONRenderer
    setup_logging()
    log = structlog.get_logger()
    log.info("hello", foo=123)

    out = capsys.readouterr().out.strip()
    # structlog.PrintLoggerFactory пишет строку json в stdout
    data = json.loads(out)
    # Проверяем ключи, выставленные процессорами
    assert data["event"] == "hello"
    assert data["level"] in ("info", "INFO")
    # TimeStamper добавляет timestamp по умолчанию
    assert "timestamp" in data or "time" in data
    assert data["foo"] == 123

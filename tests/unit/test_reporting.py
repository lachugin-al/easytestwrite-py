from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from appium.webdriver.webdriver import WebDriver as AppiumWebDriver

from mobiauto.reporting.manager import ReportManager


def test_attach_screenshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ReportManager.attach_screenshot should read PNG bytes from driver and pass them to allure.attach."""
    # mock allure.attach
    attached: dict[str, Any] = {}

    def fake_attach(data: bytes, name: str, attachment_type: Any) -> None:
        attached["name"] = name
        attached["data"] = data

    monkeypatch.setattr("mobiauto.reporting.manager.allure.attach", fake_attach)

    class D:
        def get_screenshot_as_png(self) -> bytes:
            return b"\x89PNG..."

    rm = ReportManager(str(tmp_path / "allure"))
    rm.attach_screenshot(cast(AppiumWebDriver, D()), name="snap")

    assert attached["name"] == "snap"
    assert isinstance(attached["data"], bytes)
    assert attached["data"].startswith(b"\x89PNG")

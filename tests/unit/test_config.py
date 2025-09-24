from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from mobiauto.config.loader import load_settings
from mobiauto.config.models import Settings


def test_load_settings_yaml_and_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        dedent(
            """
            platform: android
            appium:
              url: http://127.0.0.1:4723/
            android:
              device_name: Pixel_XL
              platform_version: "16"
            reporting:
              allure_dir: artifacts/allure
            """
        ),
        encoding="utf-8",
    )

    # env override: сменим платформу и девайс через pydantic-settings
    monkeypatch.setenv("MOBIAUTO_PLATFORM", "ios")
    monkeypatch.setenv("MOBIAUTO_IOS__DEVICE_NAME", "iPhone 16 Plus")
    monkeypatch.setenv("MOBIAUTO_IOS__PLATFORM_VERSION", "18.5")

    s: Settings = load_settings(str(cfg))

    assert s.platform == "ios"  # env перекрыл yaml
    assert str(s.appium.url).endswith(":4723/")  # из yaml
    assert s.ios and s.ios.device_name == "iPhone 16 Plus"
    assert s.reporting.allure_dir == "artifacts/allure"

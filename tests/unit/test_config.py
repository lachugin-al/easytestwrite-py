from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from mobiauto.config.loader import load_settings
from mobiauto.config.models import Settings


def test_load_settings_yaml_and_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Test that settings are correctly loaded from a YAML file
    and that environment variables override YAML values.

    Steps:
    1. Create a temporary YAML configuration file with Android settings.
    2. Override platform and device values via environment variables.
    3. Verify that environment variables take precedence over YAML.
    """
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

    # Override platform and device via environment variables
    monkeypatch.setenv("MOBIAUTO_PLATFORM", "ios")
    monkeypatch.setenv("MOBIAUTO_IOS__DEVICE_NAME", "iPhone 16 Plus")
    monkeypatch.setenv("MOBIAUTO_IOS__PLATFORM_VERSION", "18.5")

    # Load settings with overrides applied
    s: Settings = load_settings(str(cfg))

    # Assertions
    assert s.platform == "ios"  # env variable overrides YAML value
    assert str(s.appium.url).endswith(":4723/")  # comes from YAML
    assert s.ios and s.ios.device_name == "iPhone 16 Plus"
    assert s.reporting.allure_dir == "artifacts/allure"

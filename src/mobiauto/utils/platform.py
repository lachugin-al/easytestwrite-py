from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def detect_platform(caps: Mapping[str, Any] | None) -> str:
    """
    Return the platform name in lowercase ("android" or "ios") from capabilities.

    Prefers the "platformName" key, then "appium:platformName".
    If not found, returns an empty string.
    """
    caps = caps or {}
    return (caps.get("platformName") or caps.get("appium:platformName") or "").lower()


def get_platform_from_driver(driver: Any) -> str:
    """
    Extract the platform name from the Appium/Selenium driver capabilities in lowercase.
    """
    caps = getattr(driver, "capabilities", None)
    return detect_platform(caps)

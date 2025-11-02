from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
from appium.webdriver.webdriver import WebDriver
from pydantic import HttpUrl

from mobiauto.config.models import AndroidConfig, AppiumServer, IOSConfig, Settings
from mobiauto.drivers.base import DriverFactory


def test_driverfactory_is_abstract() -> None:
    """You cannot instantiate an abstract class without implementing `build`."""
    with pytest.raises(TypeError):
        DriverFactory()  # type: ignore[abstract]


class DummyWebDriver:
    """Minimal stub exposing only quit(), to satisfy the abstract contract."""

    def quit(self) -> None:
        pass


class DummyFactory(DriverFactory):
    """Concrete test factory that records received capabilities and returns a dummy driver."""

    def __init__(self) -> None:
        self.received_caps: Mapping[str, Any] | None = None

    def build(self, capabilities: Mapping[str, Any]) -> WebDriver:
        # Record the passed capabilities and return a stub cast to WebDriver
        self.received_caps = capabilities
        return cast(WebDriver, DummyWebDriver())


def test_dummyfactory_build_returns_driver_and_receives_caps() -> None:
    """Ensure DummyFactory.build returns a driver and receives the exact Mapping of capabilities."""
    f = DummyFactory()
    caps: Mapping[str, Any] = {"appium:newCommandTimeout": 120, "platformName": "Android"}

    drv = f.build(caps)

    # Contract: the driver has quit()
    assert hasattr(drv, "quit")
    # The capabilities object is passed through intact
    assert f.received_caps is caps
    # And it's a Mapping, as the abstract contract requires
    assert isinstance(f.received_caps, Mapping)


def test_android_driver_factory_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """AndroidDriverFactory should configure options and call webdriver.Remote with proper URL/caps."""
    # Stub webdriver.Remote to avoid opening a real session
    called: dict[str, Any] = {}

    def fake_remote(command_executor: str, options: Any) -> Any:
        called["executor"] = command_executor
        called["caps"] = (
            options.to_capabilities()
            if hasattr(options, "to_capabilities")
            else getattr(options, "capabilities", {})
        )

        class Dummy:
            def quit(self) -> None:
                pass

        return Dummy()

    monkeypatch.setattr("mobiauto.drivers.android.webdriver.Remote", fake_remote)

    s = Settings(
        platform="android",
        appium=AppiumServer(url=cast(HttpUrl, "http://127.0.0.1:4723/")),
        android=AndroidConfig(
            device_name="Pixel_XL",
            platform_version="16",
            app_path="/tmp/app.apk",
            app_activity="MainActivity",
            app_package="com.example",
            no_reset=False,
            new_command_timeout=77,
            dont_stop_app_on_reset=False,
            unicode_keyboard=True,
            adb_exec_timeout_ms=40000,
            auto_grant_permissions=True,
            auto_launch=True,
        ),
    )

    from mobiauto.drivers.android import AndroidDriverFactory

    AndroidDriverFactory(s).build({"appium:newCommandTimeout": 120})
    # Ensure URL does not end with a trailing slash duplication
    assert isinstance(called.get("executor"), str)
    assert str(called["executor"]).endswith(":4723")
    caps = called["caps"]
    # Core keys
    assert caps.get("platformName") == "Android" or caps.get("appium:platformName") == "Android"
    assert caps.get("appium:automationName") == "UIAutomator2"
    assert caps.get("appium:appActivity") == "MainActivity"
    assert caps.get("appium:appPackage") == "com.example"
    # Raw capability override should take precedence
    assert caps.get("appium:newCommandTimeout") == 120


def test_ios_driver_factory_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """IOSDriverFactory should configure options and call webdriver.Remote with proper URL/caps."""
    called: dict[str, Any] = {}

    def fake_remote(command_executor: str, options: Any) -> Any:
        called["executor"] = command_executor
        called["caps"] = (
            options.to_capabilities()
            if hasattr(options, "to_capabilities")
            else getattr(options, "capabilities", {})
        )

        class Dummy:
            def quit(self) -> None:
                pass

        return Dummy()

    monkeypatch.setattr("mobiauto.drivers.ios.webdriver.Remote", fake_remote)

    s = Settings(
        platform="ios",
        appium=AppiumServer(url=cast(HttpUrl, "http://127.0.0.1:4723/")),
        ios=IOSConfig(
            device_name="iPhone 16 Plus",
            platform_version="18.5",
            app_path="/tmp/app.app",
            bundle_id="COM.DEV",
            connect_hardware_keyboard=False,
            auto_accept_alerts=False,
            auto_dismiss_alerts=False,
            show_ios_log=False,
            auto_launch=True,
            custom_snapshot_timeout=3,
        ),
    )
    from mobiauto.drivers.ios import IOSDriverFactory

    IOSDriverFactory(s).build({})
    assert isinstance(called.get("executor"), str)
    assert str(called["executor"]).endswith(":4723")
    caps = called["caps"]
    assert caps.get("appium:automationName") == "XCUITest"
    assert caps.get("platformName") == "iOS" or caps.get("appium:platformName") == "iOS"
    assert caps.get("appium:bundleId") == "COM.DEV"

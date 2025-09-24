from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
from appium.webdriver.webdriver import WebDriver
from pydantic import HttpUrl

from mobiauto.config.models import AndroidConfig, AppiumServer, IOSConfig, Settings
from mobiauto.drivers.base import DriverFactory


def test_driverfactory_is_abstract() -> None:
    # Нельзя инстанцировать абстрактный класс без реализации build
    with pytest.raises(TypeError):
        DriverFactory()  # type: ignore[abstract]


class DummyWebDriver:
    # имитируем минимальный интерфейс
    def quit(self) -> None:
        pass


class DummyFactory(DriverFactory):
    def __init__(self) -> None:
        self.received_caps: Mapping[str, Any] | None = None

    def build(self, capabilities: Mapping[str, Any]) -> WebDriver:
        # Сохраняем, что нам передали, и возвращаем заглушку драйвера,
        # приведя тип к WebDriver для соответствия абстрактному контракту
        self.received_caps = capabilities
        return cast(WebDriver, DummyWebDriver())


def test_dummyfactory_build_returns_driver_and_receives_caps() -> None:
    f = DummyFactory()
    caps: Mapping[str, Any] = {"appium:newCommandTimeout": 120, "platformName": "Android"}

    drv = f.build(caps)

    # Проверяем контракт: у драйвера есть quit()
    assert hasattr(drv, "quit")
    # Убеждаемся, что капы дошли до реализации
    assert f.received_caps is caps
    # и что это Mapping, как требует абстрактный контракт
    assert isinstance(f.received_caps, Mapping)


def test_android_driver_factory_build(monkeypatch: pytest.MonkeyPatch) -> None:
    # Заглушим webdriver.Remote, чтобы не открывать сессию
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
    # Проверяем URL без двойного слэша
    assert isinstance(called.get("executor"), str)
    assert str(called["executor"]).endswith(":4723")
    caps = called["caps"]
    # Базовые ключи
    assert caps.get("platformName") == "Android" or caps.get("appium:platformName") == "Android"
    assert caps.get("appium:automationName") == "UIAutomator2"
    assert caps.get("appium:appActivity") == "MainActivity"
    assert caps.get("appium:appPackage") == "com.example"
    # Перезапись raw капой
    assert caps.get("appium:newCommandTimeout") == 120


def test_ios_driver_factory_build(monkeypatch: pytest.MonkeyPatch) -> None:
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
            bundle_id="RU.WILDBERRIES.MOBILEAPP.DEV",
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
    assert caps.get("appium:bundleId") == "RU.WILDBERRIES.MOBILEAPP.DEV"

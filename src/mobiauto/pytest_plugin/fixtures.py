from __future__ import annotations

from collections.abc import Generator

import pytest
from appium.webdriver.webdriver import WebDriver

from ..config.loader import load_settings
from ..config.models import Settings
from ..core.controller import MobileController
from ..drivers.android import AndroidDriverFactory
from ..drivers.ios import IOSDriverFactory
from ..network.events import EventStore
from ..network.proxy import MitmProxyProcess
from ..reporting.manager import ReportManager


@pytest.fixture(scope="session")
def settings(pytestconfig: pytest.Config) -> Settings:
    """
    Load test configuration once per test session.

    Supports overriding configuration file path and platform from CLI options:
    --config <path> and --platform <android|ios>.
    """
    cfg_path: str | None = pytestconfig.getoption("--config")
    s: Settings = load_settings(cfg_path)

    # Allow overriding the platform via CLI argument (useful for CI pipelines)
    override_platform: str | None = pytestconfig.getoption("--platform")
    if override_platform:
        s.platform = override_platform

    return s


@pytest.fixture(scope="session")
def proxy(settings: Settings) -> Generator[MitmProxyProcess, None, None]:
    """
    Start a mitmproxy process if enabled in settings.

    Yields:
        MitmProxyProcess: Running proxy process object for use in tests.
    """
    p = MitmProxyProcess(settings)
    p.start()
    try:
        yield p
    finally:
        p.stop()


@pytest.fixture(scope="session")
def report_manager(settings: Settings) -> ReportManager:
    """
    Create a report manager for collecting test artifacts (e.g. Allure results).
    """
    return ReportManager(settings.reporting.allure_dir)


@pytest.fixture(scope="function")
def driver(settings: Settings, proxy: MitmProxyProcess) -> Generator[WebDriver, None, None]:
    """
    Create a WebDriver instance for the specified platform.

    - Merges default capabilities from settings.
    - Adds proxy configuration if enabled.
    - Chooses Android or iOS driver factory based on platform.
    """
    caps = settings.capabilities.raw.copy()

    # Inject proxy capabilities if proxy is enabled
    if settings.proxy.enabled:
        caps.update(
            {
                "proxy": {
                    "proxyType": "manual",
                    "httpProxy": f"{settings.proxy.host}:{settings.proxy.port}",
                    "sslProxy": f"{settings.proxy.host}:{settings.proxy.port}",
                }
            }
        )

    if settings.platform == "android":
        drv: WebDriver = AndroidDriverFactory(settings).build(caps)
    else:
        drv = IOSDriverFactory(settings).build(caps)

    try:
        yield drv
    finally:
        drv.quit()


@pytest.fixture(scope="function")
def controller(driver: WebDriver) -> MobileController:
    """
    Create a MobileController helper for interacting with elements via WebDriver.
    """
    return MobileController(driver)


@pytest.fixture(scope="function")
def events() -> EventStore:
    """
    Provide a fresh in-memory EventStore for each test function.
    """
    return EventStore()

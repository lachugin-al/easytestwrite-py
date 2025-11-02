from __future__ import annotations

from collections.abc import Generator

import allure
import pytest
from appium.webdriver.webdriver import WebDriver

from ..config.loader import load_settings
from ..config.models import Settings
from ..core.controller import MobileController
from ..device.android_emulator import AndroidEmulatorManager
from ..device.appium_server_manager import manager as appium_manager
from ..device.base import EmulatorManager
from ..device.ios_simulator import IOSSimulatorManager, find_simulator_udid_by_name
from ..drivers.android import AndroidDriverFactory
from ..drivers.ios import IOSDriverFactory
from ..reporting.manager import ReportManager
from ..utils.logging import bind_context, clear_contextvars, setup_logging


@pytest.fixture(scope="session")
def settings(pytestconfig: pytest.Config) -> Settings:
    """
    Loads the test configuration once per pytest session.

    Supports overriding the configuration file path and platform
    via command line arguments:
    --config <path> and --platform <android|ios>.
    """
    with allure.step("Load test configuration"):
        cfg_path: str | None = pytestconfig.getoption("--config")
        s: Settings = load_settings(cfg_path)

        # Allow overriding the platform via CLI argument (useful for CI pipelines)
        override_platform: str | None = pytestconfig.getoption("--platform")
        if override_platform:
            s.platform = override_platform

        return s


@pytest.fixture(scope="session")
def appium_server(settings: Settings) -> Generator[None, None, None]:
    """
    Manages the lifecycle of the local Appium server at the pytest session level.

    - Detects if the server is already running at the configured URL; in that case, it only monitors it.
    - If the server is not available, starts a local Appium process, waits for readiness, and monitors it.
    - Gracefully shuts down the process at session end, but only if it was started by the framework.
    """
    with allure.step("Start Appium"):
        appium_manager.ensure_started_and_monitored(settings)
    try:
        yield
    finally:
        with allure.step("Stop Appium"):
            appium_manager.shutdown()


@pytest.fixture(scope="session", autouse=True)
def virtual_device(
    settings: Settings, request: pytest.FixtureRequest
) -> Generator[None, None, None]:
    """
    Automatically manages the lifecycle of a virtual device at the pytest session level.

    - Determines the platform from the settings (supports CLI override --platform).
    - For Android: starts an AVD if no physical device UDID is specified.
    - For iOS: starts a simulator by UDID; if UDID is missing, attempts to find one by simulator name.
    - Gracefully stops the device after the test session.

    Does nothing if the platform configuration is missing (android/ios = None),
    or if a physical device UDID is specified — in that case, device management is considered external.
    """
    # Unit tests don't require auto-start of virtual devices.
    # If pytest is explicitly run for the tests/unit directory, skip device management.
    try:
        args = getattr(request.config, "args", [])
        if any("tests/unit" in str(a) for a in args):
            yield
            return
    except Exception:
        # Never block test execution due to detection errors
        pass

    # Respect the autostart flag from configuration
    if hasattr(settings, "virtual_device") and not settings.virtual_device.autostart:
        yield
        return

    mgr: EmulatorManager | None = None

    if settings.platform == "android" and settings.android:
        # If UDID is specified, assume a connected physical device — skip emulator startup
        if settings.android.udid:
            yield
            return
        # Prefer explicit AVD name, otherwise use device_name from configuration
        avd = settings.android.avd or settings.android.device_name
        if avd:
            port = settings.android.emulator_port or 5554
            mgr = AndroidEmulatorManager(avd=avd, port=port)

    elif settings.platform == "ios" and settings.ios:
        # If UDID is specified, use it (may be simulator or physical device)
        udid = settings.ios.udid
        if not udid:
            # Attempt to find UDID by simulator name from configuration
            udid = find_simulator_udid_by_name(
                settings.ios.device_name, settings.ios.platform_version
            )
        if udid:
            mgr = IOSSimulatorManager(udid=udid)
        else:
            # No UDID or matching simulator found — do nothing
            yield
            return

    if mgr is None:
        # No virtual device to manage
        yield
        return

    # Start device and wait for readiness
    if isinstance(mgr, AndroidEmulatorManager):
        with allure.step(f"Start emulator {getattr(mgr, 'avd', '')}"):
            mgr.start()
        try:
            with allure.step("Wait for emulator to be ready"):
                mgr.wait_until_ready()
            yield
        finally:
            try:
                if not hasattr(settings, "virtual_device") or settings.virtual_device.autoshutdown:
                    with allure.step("Stop emulator"):
                        mgr.stop()
            except Exception:
                # Never interrupt session teardown due to shutdown errors
                pass
    elif isinstance(mgr, IOSSimulatorManager):
        with allure.step(f"Start simulator {getattr(mgr, 'udid', '')}"):
            mgr.start()
        try:
            with allure.step("Wait for simulator to be ready"):
                mgr.wait_until_ready()
            yield
        finally:
            try:
                if not hasattr(settings, "virtual_device") or settings.virtual_device.autoshutdown:
                    with allure.step("Stop simulator"):
                        mgr.stop()
            except Exception:
                # Never interrupt session teardown due to shutdown errors
                pass
    else:
        with allure.step("Start virtual device"):
            mgr.start()
        try:
            with allure.step("Wait for virtual device to be ready"):
                mgr.wait_until_ready()
            yield
        finally:
            try:
                if not hasattr(settings, "virtual_device") or settings.virtual_device.autoshutdown:
                    with allure.step("Stop virtual device"):
                        mgr.stop()
            except Exception:
                pass


@pytest.fixture(scope="session")
def report_manager(settings: Settings) -> ReportManager:
    """
    Creates a report manager for collecting test artifacts (e.g., Allure results).
    """
    rm = ReportManager(settings.reporting)
    # Make the instance globally available for internal components (Waits, controllers, etc.)
    ReportManager.set_default(rm)
    return rm


@pytest.fixture(scope="function")
def driver(
    settings: Settings, appium_server: None, request: pytest.FixtureRequest
) -> Generator[WebDriver, None, None]:
    """
    Creates a WebDriver instance for the specified platform.

    - Merges base capabilities from settings.
    - Chooses Android or iOS driver depending on the platform.
    """
    caps = settings.capabilities.raw.copy()

    with allure.step(f"Create WebDriver: {settings.platform}"):
        if settings.platform == "android":
            drv: WebDriver = AndroidDriverFactory(settings).build(caps)
        else:
            drv = IOSDriverFactory(settings).build(caps)

    # Update logging context with driver session_id
    try:
        bind_context(settings=settings, driver=drv, test_name=request.node.name)
    except Exception:
        pass

    try:
        yield drv
    finally:
        with allure.step("Close WebDriver"):
            drv.quit()


@pytest.fixture(scope="function")
def controller(driver: WebDriver, report_manager: ReportManager) -> MobileController:
    """
    Creates a helper MobileController instance for interacting with elements via WebDriver.
    """
    with allure.step("Create MobileController for interacting with elements via WebDriver"):
        return MobileController(driver, report_manager=report_manager)


# ----- Logging: initialization and context -----
@pytest.fixture(scope="session", autouse=True)
def _setup_structlog() -> None:
    """One-time setup of structured logging for the entire session."""
    setup_logging()


@pytest.fixture(autouse=True)
def _bind_test_logging_context(
    settings: Settings, request: pytest.FixtureRequest
) -> Generator[None, None, None]:
    """
    Bind the test name and platform/device parameters to the logging context.

    Updates contextvars at the start of each test and clears them after completion.
    """
    try:
        bind_context(settings=settings, test_name=request.node.name)
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            clear_contextvars()
        except Exception:
            pass

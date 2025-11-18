from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

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
from ..network.event_server import BatchHttpServer
from ..network.event_verifier import EventVerifier
from ..network.events import EventStore
from ..proxy.mitmproxy import MitmProxyInstance
from ..reporting.manager import ReportManager
from ..utils.logging import bind_context, clear_contextvars, get_logger, setup_logging
from ..utils.net import get_free_port, is_listening

_logger = get_logger(__name__)


@pytest.fixture(scope="session")
def settings(pytestconfig: pytest.Config) -> Settings:
    """
    Load test configuration once per session.

    Supports overriding the configuration file path and platform
    via command-line options:
      --config <path>
      --platform <android|ios>.
    """
    with allure.step("Load test configuration"):
        cfg_path: str | None = pytestconfig.getoption("--config")
        s: Settings = load_settings(cfg_path)

        # Allow overriding platform via CLI (useful for CI pipelines)
        override_platform: str | None = pytestconfig.getoption("--platform")
        if override_platform:
            s.platform = override_platform

        return s


@pytest.fixture(scope="session")
def appium_server(
    settings: Settings,
) -> Generator[None, None, None]:
    """
    Manage lifecycle of a local Appium server at pytest session level.

    - If a server is already running at the configured URL, only monitor it.
    - If not available, start a local Appium process, wait until healthy, and monitor it.
    - On session end, gracefully stop the process only if it was started by this framework.
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
    Automatically manage lifecycle of a virtual device at pytest session level.

    - Detect platform from settings (supports CLI override via --platform).
    - For Android: start an AVD if no physical device UDID is provided.
    - For iOS: start a simulator by UDID; if UDID is not set, try to find it by simulator name.
    - Gracefully stop the device when the session finishes.

    Does nothing if:
    - platform configuration is missing (android/ios is None), or
    - a physical device UDID is provided - in that case device management is considered external.
    """
    # For unit tests we don't need to auto-start a virtual device.
    # If pytest is explicitly run against tests/unit, skip device management.
    try:
        args = getattr(request.config, "args", [])
        if any("tests/unit" in str(a) for a in args):
            yield
            return
    except Exception:
        # Never break tests because of errors while checking arguments
        pass

    # Respect autostart flag from configuration
    if hasattr(settings, "virtual_device") and not settings.virtual_device.autostart:
        yield
        return

    mgr: EmulatorManager | None = None

    if settings.platform == "android" and settings.android:
        # If UDID is provided, assume a physical device is connected - do not start emulator
        if settings.android.udid:
            yield
            return
        # Prefer explicit AVD name, otherwise use device_name from configuration
        avd = settings.android.avd or settings.android.device_name
        if avd:
            port = settings.android.emulator_port or 5554
            mgr = AndroidEmulatorManager(avd=avd, port=port)

    elif settings.platform == "ios" and settings.ios:
        # If UDID is provided, use it (may be simulator or physical device)
        udid = settings.ios.udid
        if not udid:
            # Try to find UDID by simulator name from settings
            udid = find_simulator_udid_by_name(
                settings.ios.device_name, settings.ios.platform_version
            )
        if udid:
            mgr = IOSSimulatorManager(udid=udid)
        else:
            # No UDID and no matching simulator name - do nothing
            yield
            return

    if mgr is None:
        # No virtual device management required
        yield
        return

    # Start device and wait for readiness: Android Emulator
    if isinstance(mgr, AndroidEmulatorManager):
        with allure.step(f"Start Android emulator {getattr(mgr, 'avd', '')}"):
            mgr.start()

        try:
            with allure.step("Wait for emulator to become ready"):
                mgr.wait_until_ready()
            yield
        finally:
            try:
                if not hasattr(settings, "virtual_device") or settings.virtual_device.autoshutdown:
                    with allure.step("Stop emulator"):
                        mgr.stop()
                        _logger.info("Android emulator stopped")
            except Exception:
                pass

    # Start device and wait for readiness: iOS Simulator
    elif isinstance(mgr, IOSSimulatorManager):
        with allure.step(f"Start iOS simulator {getattr(mgr, 'udid', '')}"):
            mgr.start()

        try:
            with allure.step("Wait for simulator to become ready"):
                mgr.wait_until_ready()
            yield
        finally:
            try:
                if not hasattr(settings, "virtual_device") or settings.virtual_device.autoshutdown:
                    with allure.step("Stop simulator"):
                        mgr.stop()
                        _logger.info("iOS simulator stopped")
            except Exception:
                pass

    else:
        # Generic EmulatorManager fallback
        with allure.step("Start virtual device"):
            mgr.start()
        try:
            with allure.step("Wait for virtual device to become ready"):
                mgr.wait_until_ready()
            yield
        finally:
            try:
                if not hasattr(settings, "virtual_device") or settings.virtual_device.autoshutdown:
                    with allure.step("Stop virtual device"):
                        mgr.stop()
            except Exception:
                # Do not break session teardown due to stop errors
                pass


@pytest.fixture(scope="function")
def mitm_proxy(
    settings: Settings,
    event_server: str,
) -> Generator[dict[str, object] | None, None, None]:
    """
    Functional mitmproxy: runs on 127.0.0.1:<free_port> separately for each test.

    - Independent from appium_server and virtual_device lifecycles.
    - Each test gets its own mitm port and device proxy configuration.
    - For Android emulator, device_host=10.0.2.2; for iOS Simulator, 127.0.0.1.
    - TARGET_HOST/TARGET_PORT for wba_mobile_events addon are taken from event_server.

    Yields a dict:
    {
        "host": <address to configure on Android device / iOS system>,
        "bind_host": <host bind address> (always 127.0.0.1),
        "port": <mitmproxy port>,
        "url": "http://<host>:<port>",
        "log_dir": "<logs directory>",
        "pid": <mitm process pid>
    }
    """
    # If proxy is disabled in config - do not start it
    if not getattr(settings, "proxy", None) or not settings.proxy.enabled:
        yield None
        return

    # Parse local event_server URL
    u = urlparse(event_server)
    target_host = u.hostname or "127.0.0.1"
    target_port = u.port or 8000

    # Update environment for mitmproxy addon before starting process
    os.environ["TARGET_HOST"] = str(target_host)
    os.environ["TARGET_PORT"] = str(target_port)

    # Choose bind_host/port for mitmproxy from settings; fallback to defaults
    try:
        bind_host = (getattr(settings.proxy, "host", None) or "127.0.0.1").strip()
    except Exception:
        bind_host = "127.0.0.1"

    cfg_port = getattr(settings.proxy, "port", None)
    selected_port = None
    try:
        # If port is explicitly set in config - use it. Otherwise, pick a free one.
        if cfg_port:
            selected_port = int(cfg_port)
            # If already in use - pick a free port and log warning
            if is_listening(bind_host, selected_port):
                _logger.warning(
                    "settings.proxy.port %d is already in use - picking a free port",
                    selected_port,
                )
                selected_port = get_free_port()
        else:
            selected_port = get_free_port()
    except Exception:
        selected_port = get_free_port()

    # Host to be configured on the device
    device_host = bind_host
    try:
        if settings.platform == "android" and settings.android and not settings.android.udid:
            device_host = "10.0.2.2"
        elif settings.platform == "ios":
            device_host = "127.0.0.1"
    except Exception:
        pass

    # Prepare logs directory (separate folder per test)
    base_log_dir = Path(settings.proxy.log_dir or "artifacts/proxy")
    test_subdir = base_log_dir / f"test_{datetime.utcnow():%Y%m%d_%H%M%S_%f}"
    test_subdir.mkdir(parents=True, exist_ok=True)

    inst = MitmProxyInstance(
        host=bind_host,
        port=selected_port,
        addons=list(settings.proxy.addons or []),
        mitm_args=list(settings.proxy.mitm_args or []),
        health_port=0,
        log_dir=test_subdir,
    )

    # Start mitmproxy
    try:
        _logger.info(
            "Starting function-scoped mitmproxy at %s:%d; logs -> %s",
            bind_host,
            selected_port,
            test_subdir,
        )
        inst.start()
    except Exception as e:
        import pytest as _pytest

        _logger.exception("Failed to start mitmproxy (function-scoped): %s", e)
        if getattr(settings.proxy, "strict", True):
            _pytest.exit(f"Failed to start mitmproxy (function-scoped): {e}", returncode=2)
        else:
            yield None
            return

    # Apply proxy to device at test level, if possible and enabled
    proxy_applied = False
    try:
        if settings.platform == "android" and settings.android and not settings.android.udid:
            # Try applying proxy to Android emulator using known emulator_port
            try:
                port = settings.android.emulator_port or 5554
                mgr = AndroidEmulatorManager(
                    avd=settings.android.avd or settings.android.device_name,
                    port=port,
                )
                mgr.apply_proxy(device_host, int(selected_port))
                proxy_applied = True
                if getattr(settings.proxy, "install_ca", False):
                    mgr.install_mitm_ca_if_available(str(test_subdir))
            except Exception:
                _logger.exception("Failed to apply proxy/CA to Android emulator (per-test)")
        elif settings.platform == "ios" and settings.ios:
            try:
                udid = settings.ios.udid
                if not udid:
                    udid = find_simulator_udid_by_name(
                        settings.ios.device_name, settings.ios.platform_version
                    )
                mgr2 = IOSSimulatorManager(udid=udid or "unknown")
                mgr2.apply_proxy(device_host, int(selected_port))
                proxy_applied = True
                if getattr(settings.proxy, "install_ca", False):
                    mgr2.install_mitm_ca_if_available(str(test_subdir))
            except Exception:
                _logger.exception("Failed to apply proxy/CA to iOS simulator (per-test)")
    except Exception:
        pass

    try:
        yield {
            "host": device_host,
            "bind_host": bind_host,
            "port": selected_port,
            "url": f"http://{device_host}:{selected_port}",
            "log_dir": str(test_subdir),
            "pid": inst.pid,
        }
    finally:
        # Remove proxy from device (best-effort)
        try:
            if proxy_applied:
                if (
                    settings.platform == "android"
                    and settings.android
                    and not settings.android.udid
                ):
                    try:
                        port = settings.android.emulator_port or 5554
                        mgr = AndroidEmulatorManager(
                            avd=settings.android.avd or settings.android.device_name,
                            port=port,
                        )
                        mgr.remove_proxy()
                    except Exception:
                        _logger.exception(
                            "Error while removing proxy from Android emulator (per-test)"
                        )
                elif settings.platform == "ios" and settings.ios:
                    try:
                        udid = settings.ios.udid
                        if not udid:
                            udid = find_simulator_udid_by_name(
                                settings.ios.device_name,
                                settings.ios.platform_version,
                            )
                        mgr2 = IOSSimulatorManager(udid=udid or "unknown")
                        mgr2.remove_proxy()
                    except Exception:
                        _logger.exception(
                            "Error while removing proxy from iOS simulator (per-test)"
                        )
        except Exception:
            pass
        # Stop mitmproxy
        try:
            inst.stop()
        except Exception as e:
            _logger.exception("Error while stopping mitmproxy (function-scoped): %s", e)


@pytest.fixture(scope="session")
def report_manager(settings: Settings) -> ReportManager:
    """
    Create a ReportManager for collecting test artifacts (e.g. Allure results).
    """
    rm = ReportManager(settings.reporting)
    # Make instance globally available for internal calls (Waits, controllers, etc.)
    ReportManager.set_default(rm)
    return rm


@pytest.fixture(scope="function")
def driver(
    settings: Settings,
    appium_server: None,
    request: pytest.FixtureRequest,
    mitm_proxy: dict[str, object] | None,
) -> Generator[WebDriver, None, None]:
    """
    Create a WebDriver instance for the configured platform.

    - Merges base capabilities from settings.
    - Adds proxy configuration if enabled.
    - Selects Android or iOS driver based on platform.
    """
    caps = settings.capabilities.raw.copy()

    # Whether to inject proxy into capabilities (relevant for web/hybrid)
    inject_into_caps = bool(getattr(getattr(settings, "proxy", None), "inject_into_caps", True))

    if getattr(settings, "proxy", None) and settings.proxy.enabled and inject_into_caps:
        # Determine host/port for capabilities
        if mitm_proxy:
            proxy_host = (
                mitm_proxy.get("bind_host") or mitm_proxy.get("host") or settings.proxy.host
            )
            proxy_port = mitm_proxy.get("port") or settings.proxy.port
        else:
            proxy_host = settings.proxy.host
            proxy_port = settings.proxy.port

        if proxy_host and proxy_port:
            caps.update(
                {
                    "proxy": {
                        "proxyType": "manual",
                        "httpProxy": f"{proxy_host}:{proxy_port}",
                        "sslProxy": f"{proxy_host}:{proxy_port}",
                    }
                }
            )

    with allure.step(f"Create WebDriver: {settings.platform}"):
        if settings.platform == "android":
            drv: WebDriver = AndroidDriverFactory(settings).build(caps)
        else:
            drv = IOSDriverFactory(settings).build(caps)

    try:
        bind_context(settings=settings, driver=drv, test_name=request.node.name)
    except Exception:
        pass

    try:
        yield drv
    finally:
        with allure.step("Quit WebDriver"):
            drv.quit()


@pytest.fixture(scope="function")
def controller(driver: WebDriver, report_manager: ReportManager) -> MobileController:
    """
    Create a MobileController helper for WebDriver-based element interactions.
    """
    with allure.step("Create MobileController for WebDriver interactions"):
        return MobileController(driver, report_manager=report_manager)


@pytest.fixture(scope="function")
def events() -> EventStore:
    """
    Provide a fresh EventStore instance for each test function.
    """
    return EventStore()


@pytest.fixture(scope="function")
def event_verifier(events: EventStore, driver: WebDriver) -> EventVerifier:
    """
    Provide an EventVerifier bound to the same EventStore and WebDriver as event_server.

    This ensures that event checks are performed against the same store
    where event_server writes events.
    """
    return EventVerifier(store=events, driver=driver)


@pytest.fixture(scope="function", autouse=True)
def _await_background_event_checks(event_verifier: EventVerifier) -> Generator[None, None, None]:
    """
    Automatically wait for completion of all background event checks after each test.

    Why:
    - All tests will automatically wait for background checks (`check_has_event_async`).
    - If something fails, it will be properly reflected in reports (AssertionError in test).
    - No thread leaks or hangs: waiting is limited by a timeout.

    Implementation:
    - Wrap `event_verifier.await_all_event_checks()` in a yield-fixture.
    - On teardown, run the wait in a separate thread with a hard timeout.
    """
    # Before test: do nothing
    yield

    # After test: wait for background checks
    import concurrent.futures as _cf

    timeout_sec: float = 30.0  # safety timeout against hanging waits

    with allure.step("Wait for background event checks to finish"):
        with _cf.ThreadPoolExecutor(max_workers=1) as _executor:
            future = _executor.submit(event_verifier.await_all_event_checks)
            try:
                future.result(timeout=timeout_sec)
            except _cf.TimeoutError:
                import pytest as _pytest

                _pytest.fail(
                    f"Waiting for background event checks exceeded timeout of {timeout_sec} seconds "
                    f"- possible leak or hang.",
                    pytrace=True,
                )
            except AssertionError:
                # Re-raise to fail test with original assertion info
                raise
            except Exception as e:
                import pytest as _pytest

                _pytest.fail(f"Error while waiting for background event checks: {e}")


@pytest.fixture(scope="function", autouse=True)
def event_server(events: EventStore) -> Generator[str, None, None]:
    """
    Simple HTTP server for receiving event batches at http://<host>:<port>/event.

    - Started before each test and stopped afterwards.
    - Each element from the "events" array is stored in the provided EventStore
      as a separate Event. Event.data.body contains JSON of shape {"meta":..., "event":...}.

    Yields base server URL as string, e.g. "http://127.0.0.1:<port>".
    """
    host = "127.0.0.1"
    port = get_free_port()
    srv = BatchHttpServer(host, port, events)
    srv.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        srv.stop()


# ----- Logging: initialization and context -----
@pytest.fixture(scope="session", autouse=True)
def _setup_structlog() -> None:
    """One-time structured logging setup for the entire test session."""
    setup_logging()


@pytest.fixture(autouse=True)
def _bind_test_logging_context(
    settings: Settings, request: pytest.FixtureRequest
) -> Generator[None, None, None]:
    """
    Bind test name and platform/device parameters to the logging context.

    Updates contextvars at the start of each test and clears them afterwards.
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

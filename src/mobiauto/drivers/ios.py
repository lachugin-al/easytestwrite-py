from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from appium import webdriver
from appium.options.ios import XCUITestOptions

from ..config.models import Settings
from ..utils.logging import get_logger


class IOSDriverFactory:
    """
    Factory class for creating and configuring Appium iOS WebDriver instances.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the factory with project settings.

        Args:
            settings (Settings): Global configuration with iOS-related parameters.
        """
        self.settings = settings
        self._log = get_logger(__name__)

    def build(self, capabilities: Mapping[str, Any]) -> webdriver.Remote:
        """
        Create and return a configured Appium Remote WebDriver instance for iOS.

        Args:
            capabilities (Mapping[str, Any]): Extra capabilities to be merged with base ones.

        Returns:
            webdriver.Remote: Configured Appium WebDriver ready to run tests.
        """
        s = self.settings
        opts = XCUITestOptions()

        # --- Core iOS capabilities ---
        if s.ios and s.ios.app_path:
            opts.app = s.ios.app_path
        if s.ios and s.ios.bundle_id:
            opts.set_capability("appium:bundleId", s.ios.bundle_id)
        if s.ios and s.ios.udid:
            opts.udid = s.ios.udid
        if s.ios and s.ios.device_name:
            opts.device_name = s.ios.device_name
        if s.ios and s.ios.platform_version:
            opts.platform_version = s.ios.platform_version

        # --- Appium-specific settings ---
        if s.ios:
            opts.set_capability("appium:automationName", "XCUITest")
            opts.set_capability("platformName", "iOS")
            opts.set_capability("appium:connectHardwareKeyboard", s.ios.connect_hardware_keyboard)
            opts.set_capability("appium:autoAcceptAlerts", s.ios.auto_accept_alerts)
            opts.set_capability("appium:autoDismissAlerts", s.ios.auto_dismiss_alerts)
            opts.set_capability("showIOSLog", s.ios.show_ios_log)
            opts.set_capability("appium:autoLaunch", s.ios.auto_launch)

            if s.ios.process_arguments:
                opts.set_capability("processArguments", s.ios.process_arguments)

            # Custom timeout for speeding up or slowing down XCTest snapshots
            opts.set_capability("settings[customSnapshotTimeout]", s.ios.custom_snapshot_timeout)

        # --- Merge runtime-provided capabilities ---
        for k, v in capabilities.items():
            opts.set_capability(k, v)

        # --- Create and return the driver instance ---
        executor = str(self.settings.appium.url).rstrip("/")
        self._log.info("Creating iOS WebDriver", action="driver_start", executor=executor)
        drv = webdriver.Remote(command_executor=executor, options=opts)
        try:
            self._log.info(
                "iOS WebDriver created",
                action="driver_ready",
                session_id=getattr(drv, "session_id", None),
            )
        except Exception:
            pass
        return drv

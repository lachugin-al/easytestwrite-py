from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from appium import webdriver
from appium.options.ios import XCUITestOptions

from ..config.models import Settings


class IOSDriverFactory:
    """
    Factory class for building and configuring an Appium iOS WebDriver instance.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the factory with project settings.

        Args:
            settings (Settings): Application-wide configuration with iOS-specific settings.
        """
        self.settings = settings

    def build(self, capabilities: Mapping[str, Any]) -> webdriver.Remote:
        """
        Build and return a configured Appium Remote WebDriver instance for iOS.

        Args:
            capabilities (Mapping[str, Any]): Additional capabilities to merge with defaults.

        Returns:
            webdriver.Remote: Configured Appium driver ready for test execution.
        """
        s = self.settings
        opts = XCUITestOptions()

        # --- Configure core iOS capabilities ---
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

        # --- Set Appium-specific options ---
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

            # Custom snapshot timeout to speed up or slow down XCTest snapshots
            opts.set_capability("settings[customSnapshotTimeout]", s.ios.custom_snapshot_timeout)

        # --- Merge additional capabilities provided at runtime ---
        for k, v in capabilities.items():
            opts.set_capability(k, v)

        # --- Create and return driver instance ---
        executor = str(self.settings.appium.url).rstrip("/")
        return webdriver.Remote(command_executor=executor, options=opts)

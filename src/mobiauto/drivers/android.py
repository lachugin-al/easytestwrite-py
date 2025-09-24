from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from appium import webdriver
from appium.options.android import UiAutomator2Options

from ..config.models import Settings


class AndroidDriverFactory:
    """
    Factory class for building and configuring an Appium Android WebDriver instance.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the factory with project settings.

        Args:
            settings (Settings): Application-wide configuration with Android-specific settings.
        """
        self.settings = settings

    def build(self, capabilities: Mapping[str, Any]) -> webdriver.Remote:
        """
        Build and return a configured Appium Remote WebDriver instance.

        Args:
            capabilities (Mapping[str, Any]): Additional capabilities to merge with defaults.

        Returns:
            webdriver.Remote: Configured Appium driver ready for test execution.
        """
        s = self.settings
        opts = UiAutomator2Options()

        # --- Configure core Android capabilities ---
        if s.android and s.android.app_path:
            opts.app = s.android.app_path
        if s.android and s.android.udid:
            opts.udid = s.android.udid
        if s.android and s.android.device_name:
            opts.device_name = s.android.device_name
        if s.android and s.android.platform_version:
            opts.platform_version = s.android.platform_version

        # --- Set Appium-specific options ---
        if s.android:
            opts.set_capability("appium:automationName", "UIAutomator2")
            opts.set_capability("platformName", "Android")
            opts.set_capability("appium:noReset", s.android.no_reset)
            opts.set_capability("appium:newCommandTimeout", s.android.new_command_timeout)
            opts.set_capability("appium:dontStopAppOnReset", s.android.dont_stop_app_on_reset)
            opts.set_capability("appium:unicodeKeyboard", s.android.unicode_keyboard)
            opts.set_capability("appium:adbExecTimeout", s.android.adb_exec_timeout_ms)
            opts.set_capability("appium:autoGrantPermissions", s.android.auto_grant_permissions)
            opts.set_capability("appium:autoLaunch", s.android.auto_launch)
            if s.android.app_activity:
                opts.set_capability("appium:appActivity", s.android.app_activity)
            if s.android.app_package:
                opts.set_capability("appium:appPackage", s.android.app_package)

        # --- Merge additional capabilities provided at runtime ---
        for k, v in capabilities.items():
            opts.set_capability(k, v)

        # --- Create and return driver instance ---
        executor = str(self.settings.appium.url).rstrip("/")
        return webdriver.Remote(command_executor=executor, options=opts)

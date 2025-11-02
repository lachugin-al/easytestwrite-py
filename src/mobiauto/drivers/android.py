from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from appium import webdriver
from appium.options.android import UiAutomator2Options

from ..config.models import Settings
from ..utils.logging import get_logger


class AndroidDriverFactory:
    """
    Factory class responsible for creating and configuring an instance of the Appium Android WebDriver.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the factory with project settings.

        Args:
            settings (Settings): Global application configuration containing Android parameters.
        """
        self.settings = settings
        self._log = get_logger(__name__)

    def build(self, capabilities: Mapping[str, Any]) -> webdriver.Remote:
        """
        Create and return a configured instance of the Appium Remote WebDriver.

        Args:
            capabilities (Mapping[str, Any]): Additional capabilities to be merged with the base ones.

        Returns:
            webdriver.Remote: Configured Appium driver ready for test execution.
        """
        s = self.settings
        opts = UiAutomator2Options()

        # --- Configure base Android capabilities ---
        if s.android and s.android.app_path:
            opts.app = s.android.app_path
        if s.android and s.android.udid:
            opts.udid = s.android.udid
        if s.android and s.android.device_name:
            opts.device_name = s.android.device_name
        if s.android and s.android.platform_version:
            opts.platform_version = s.android.platform_version

        # --- Set Appium-specific parameters ---
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

        # --- Merge additional runtime capabilities ---
        for k, v in capabilities.items():
            opts.set_capability(k, v)

        # --- Create and return the WebDriver instance ---
        executor = str(self.settings.appium.url).rstrip("/")
        self._log.info("Creating Android WebDriver", action="driver_start", executor=executor)
        drv = webdriver.Remote(command_executor=executor, options=opts)
        try:
            self._log.info(
                "Android WebDriver created",
                action="driver_ready",
                session_id=getattr(drv, "session_id", None),
            )
        except Exception:
            pass
        return drv

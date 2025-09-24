from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from appium.webdriver.webdriver import WebDriver


class DriverFactory(ABC):
    """
    Abstract base class for driver factories.

    Defines the interface for building and returning a configured Appium WebDriver.
    """

    @abstractmethod
    def build(self, capabilities: Mapping[str, Any]) -> WebDriver:
        """
        Build and return a configured WebDriver instance.

        Args:
            capabilities (Mapping[str, Any]): Additional capabilities to apply.

        Returns:
            WebDriver: A fully configured Appium WebDriver ready for test execution.
        """
        ...

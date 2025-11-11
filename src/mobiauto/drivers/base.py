from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from appium.webdriver.webdriver import WebDriver


class DriverFactory(ABC):
    """
    Abstract base class for driver factories.

    Defines an interface for creating and returning a configured Appium WebDriver instance.
    """

    @abstractmethod
    def build(self, capabilities: Mapping[str, Any]) -> WebDriver:
        """
        Create and return a configured WebDriver instance.

        Args:
            capabilities (Mapping[str, Any]): Additional capabilities to apply.

        Returns:
            WebDriver: Fully configured Appium WebDriver instance ready for test execution.
        """
        ...

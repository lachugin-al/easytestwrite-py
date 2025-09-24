from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from appium.webdriver.webdriver import WebDriver


class DriverFactory(ABC):
    @abstractmethod
    def build(self, capabilities: Mapping[str, Any]) -> WebDriver: ...

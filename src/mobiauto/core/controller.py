from __future__ import annotations

from typing import Any

from appium.webdriver.webdriver import WebDriver

from .locators import PageElement, StrategyValue
from .waits import Waits


class MobileController:
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    def click(self, target: PageElement | StrategyValue, **params: Any) -> None:
        el = Waits.wait_for_elements(self.driver, target, **params)
        el.click()

    def type(
        self, target: PageElement | StrategyValue, text: str, clear: bool = True, **params: Any
    ) -> None:
        el = Waits.wait_for_elements(self.driver, target, **params)
        if clear:
            el.clear()
        el.send_keys(text)

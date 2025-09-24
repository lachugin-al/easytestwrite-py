from __future__ import annotations

from typing import Any

from appium.webdriver.webdriver import WebDriver

from .locators import PageElement, StrategyValue
from .waits import Waits


class MobileController:
    """
    A helper class to interact with mobile elements using Appium.

    Provides common actions like clicking and typing with built-in waiting logic.
    """

    def __init__(self, driver: WebDriver) -> None:
        """
        Initialize the MobileController with an active Appium WebDriver.

        Args:
            driver (WebDriver): The active Appium driver instance.
        """
        self.driver = driver

    def click(self, target: PageElement | StrategyValue, **params: Any) -> None:
        """
        Wait for the element to be present and perform a click action.

        Args:
            target (PageElement | StrategyValue): Locator or strategy to find the element.
            **params: Additional parameters passed to the wait function.
        """
        el = Waits.wait_for_elements(self.driver, target, **params)
        el.click()

    def type(
            self,
            target: PageElement | StrategyValue,
            text: str,
            clear: bool = True,
            **params: Any,
    ) -> None:
        """
        Wait for the element and type the given text into it.

        Args:
            target (PageElement | StrategyValue): Locator or strategy to find the element.
            text (str): The text to input.
            clear (bool): Whether to clear the existing text before typing. Defaults to True.
            **params: Additional parameters passed to the wait function.
        """
        el = Waits.wait_for_elements(self.driver, target, **params)
        if clear:
            el.clear()
        el.send_keys(text)

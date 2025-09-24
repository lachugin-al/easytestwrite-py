from __future__ import annotations

from pathlib import Path

import allure
from appium.webdriver.webdriver import WebDriver


class ReportManager:
    """
    Utility class for managing test reporting artifacts (e.g., screenshots).

    Creates the Allure results directory (if it does not exist)
    and provides helper methods for attaching artifacts.
    """

    def __init__(self, allure_dir: str) -> None:
        """
        Initialize the ReportManager and ensure the Allure directory exists.

        Args:
            allure_dir (str): Path to the Allure results directory.
        """
        self.dir = Path(allure_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def attach_screenshot(self, driver: WebDriver, name: str = "screenshot") -> None:
        """
        Capture a screenshot from the current WebDriver session
        and attach it to the Allure report.

        Args:
            driver (WebDriver): The Appium WebDriver instance.
            name (str): Name to display in the report for the attachment.
        """
        png = driver.get_screenshot_as_png()
        allure.attach(png, name=name, attachment_type=allure.attachment_type.PNG)

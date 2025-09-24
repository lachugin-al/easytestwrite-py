from __future__ import annotations

from pathlib import Path

import allure
from appium.webdriver.webdriver import WebDriver


class ReportManager:
    def __init__(self, allure_dir: str) -> None:
        self.dir = Path(allure_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def attach_screenshot(self, driver: WebDriver, name: str = "screenshot") -> None:
        png = driver.get_screenshot_as_png()
        allure.attach(png, name=name, attachment_type=allure.attachment_type.PNG)

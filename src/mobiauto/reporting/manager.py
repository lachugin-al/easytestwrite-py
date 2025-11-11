from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal

import allure

from ..config.loader import load_settings
from ..config.models import ReportingSettings


class ReportManager:
    """
    Helper class for managing test report artifacts (screenshots, page source, etc.).

    Ensures the Allure results directory exists and provides
    methods to attach artifacts according to reporting settings policy.
    """

    _default: ClassVar[ReportManager | None] = None

    def __init__(self, reporting: ReportingSettings | str) -> None:
        """
        Initialize ReportManager and ensure the Allure results directory exists.

        Args:
            reporting (ReportingSettings | str): Either a ReportingSettings object
                or a path to the Allure results directory (for backward compatibility).
        """
        if isinstance(reporting, ReportingSettings):
            self.settings = reporting
            allure_dir = reporting.allure_dir
        else:
            # Backward compatibility with existing tests
            self.settings = ReportingSettings(allure_dir=str(reporting))
            allure_dir = str(reporting)

        self.dir = Path(allure_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # ----- Singleton management -----
    @classmethod
    def get_default(cls) -> ReportManager:
        """Return the global ReportManager instance, creating it if necessary."""
        if cls._default is None:
            # Lazy initialization from default configuration
            try:
                s = load_settings()
                cls._default = ReportManager(s.reporting)
            except Exception:
                # As a fallback, create with default settings
                cls._default = ReportManager(ReportingSettings())
        return cls._default

    @classmethod
    def set_default(cls, manager: ReportManager) -> None:
        """Set the global ReportManager instance (used by fixtures)."""
        cls._default = manager

    # ----- Low-level safe methods -----
    @staticmethod
    def _safe_attach_screenshot(driver: Any, *, name: str) -> None:
        try:
            png = driver.get_screenshot_as_png()
            allure.attach(png, name=name, attachment_type=allure.attachment_type.PNG)
        except Exception:
            # Ignore any errors during screenshot capture or report attachment
            pass

    @staticmethod
    def _safe_attach_page_source(driver: Any, *, name: str) -> None:
        try:
            src = getattr(driver, "page_source", None)
            if src:
                allure.attach(src, name=name, attachment_type=allure.attachment_type.XML)
        except Exception:
            pass

    # ----- Public methods -----
    def attach_screenshot(self, driver: Any, name: str = "screenshot") -> None:
        """
        Capture a screenshot of the current WebDriver session and attach it to the Allure report.
        Preserves backward compatibility with existing calls.
        """
        # Keep default behavior without flag checks for unit test compatibility
        ReportManager._safe_attach_screenshot(driver, name=name)

    def attach_screenshot_if_allowed(
        self, driver: Any, *, when: Literal["success", "failure"]
    ) -> None:
        """Attach a screenshot if allowed by settings policy for the given event."""
        name = self.settings.screenshot_name
        if when == "failure" and self.settings.screenshots_on_fail:
            ReportManager._safe_attach_screenshot(driver, name=name)
        elif when == "success" and self.settings.screenshots_on_success:
            ReportManager._safe_attach_screenshot(driver, name=name)

    def attach_page_source_if_allowed(
        self, driver: Any, *, when: Literal["success", "failure"]
    ) -> None:
        """Attach page source if allowed by settings policy for the given event."""
        name = self.settings.page_source_name
        if when == "failure" and self.settings.page_source_on_fail:
            ReportManager._safe_attach_page_source(driver, name=name)
        elif when == "success" and self.settings.page_source_on_success:
            ReportManager._safe_attach_page_source(driver, name=name)

    def attach_artifacts_on_failure(self, driver: Any) -> None:
        """Typical scenario: attach artifacts when a step or test fails."""
        self.attach_screenshot_if_allowed(driver, when="failure")
        self.attach_page_source_if_allowed(driver, when="failure")

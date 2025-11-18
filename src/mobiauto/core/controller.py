from __future__ import annotations

# Extra imports for deeplink
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Literal
from urllib.parse import quote as _url_quote

import allure
from selenium.common.exceptions import NoAlertPresentException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from ..config.loader import load_settings
from ..reporting.manager import ReportManager
from ..utils.logging import get_logger
from ..utils.number_parser import NumberParser
from ..utils.platform import get_platform_from_driver
from .locators import (
    PageElement,
    StrategyValue,
    by_accessibility_id,
    by_contains,
    by_exact_match,
    pretty_locator,
)
from .waits import (
    DEFAULT_SCROLL_CAPACITY,
    DEFAULT_SCROLL_DIRECTION,
    DEFAULT_TIMEOUT_BEFORE_EXPECTATION,
    DEFAULT_TIMEOUT_EXPECTATION,
    Waits,
)


class MobileController:
    """
    Helper class for interacting with mobile elements using Appium.

    Provides common actions such as click and text input,
    with built-in waiting logic.
    """

    def __init__(self, driver: WebDriver, report_manager: ReportManager | None = None) -> None:
        """
        Initialize MobileController with an active Appium WebDriver instance.

        Args:
            driver (WebDriver): Active Appium driver instance.
            report_manager (ReportManager | None): Reporting manager. If not provided,
                the global ReportManager instance will be used.
        """

        self.driver = driver
        self.report_manager = report_manager or ReportManager.get_default()
        self._log = get_logger(__name__)

    # ====== System alerts handling ======
    def _wait_for_alert(self, timeout: float = DEFAULT_TIMEOUT_EXPECTATION) -> Alert:
        """Waits for a system alert to appear and returns its object."""
        return WebDriverWait(self.driver, timeout).until(ec.alert_is_present())

    def has_alert(self, timeout: float = DEFAULT_TIMEOUT_EXPECTATION) -> bool:
        """
        Checks for a system alert within the given timeout.

        Returns True if an alert appears; otherwise False (by timeout).
        """
        with allure.step(f"Check for system alert (timeout={timeout}s)"):
            self._log.info("Checking for a system alert", action="has_alert", timeout=timeout)
            try:
                self._wait_for_alert(timeout)
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return True
            except TimeoutException:
                # Absence of an alert is not an error; just return False
                self._log.info("System alert not detected by timeout", action="has_alert")
                return False
            except Exception:
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def accept_alert(self, timeout: float = DEFAULT_TIMEOUT_EXPECTATION) -> None:
        """
        Waits for a system alert and accepts it.
        """
        with allure.step("Accept system alert"):
            self._log.info("Accepting system alert", action="accept_alert", timeout=timeout)
            try:
                alert = self._wait_for_alert(timeout)
                try:
                    alert.accept()
                except NoAlertPresentException:
                    # Rare race: alert disappeared between wait and action - retry briefly
                    alert = self._wait_for_alert(1)
                    alert.accept()
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def dismiss_alert(self, timeout: float = DEFAULT_TIMEOUT_EXPECTATION) -> None:
        """
        Waits for a system alert and dismisses it.
        """
        with allure.step("Dismiss system alert"):
            self._log.info("Dismissing system alert", action="dismiss_alert", timeout=timeout)
            try:
                alert = self._wait_for_alert(timeout)
                try:
                    alert.dismiss()
                except NoAlertPresentException:
                    # Rare race - retry with a short wait
                    alert = self._wait_for_alert(1)
                    alert.dismiss()
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def get_alert_text(self, timeout: float = DEFAULT_TIMEOUT_EXPECTATION) -> str:
        """
        Waits for a system alert and returns its text.
        """
        with allure.step("Get system alert text"):
            self._log.info("Getting system alert text", action="get_alert_text", timeout=timeout)
            try:
                alert = self._wait_for_alert(timeout)
                text = alert.text
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return str(text) if text is not None else ""
            except Exception:
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def click(
        self,
        target: PageElement | StrategyValue | str | None = None,
        **params: Any,
    ) -> None:
        """
        Waits for an element and performs a click.

        Modes:
        - click(target=..., **waits): click on the provided locator/element.
        - click(text="..."): build a locator by exact text match and click it.
        - click(contains_text="..."): build a locator by text containment and click it.
        - click("Text"): the first string positional argument is treated as exact text.

        ONLY canonical waiting parameters are supported (passed through to Waits.wait_for_elements):
          index, settle_for, timeout, polling_ms, max_scrolls, scroll_percent, scroll_direction.
        """
        # Optional custom step title
        step_title = params.pop("step", None) or params.pop("step_title", None)

        # Text modes
        text_value = params.pop("text", None)
        contains_value = params.pop("contains_text", None)

        # If the first positional arg is a string and modes are not provided: treat it as text
        if isinstance(target, str) and text_value is None and contains_value is None:
            text_value, target = target, None

        # Mutually exclusive text/contains_text
        if text_value is not None and contains_value is not None:
            raise ValueError("Cannot use both 'text' and 'contains_text' at the same time")

        # Build the effective locator
        if text_value is not None:
            effective_target: PageElement | StrategyValue = by_exact_match(str(text_value))
            locator_kind = "exact"
        elif contains_value is not None:
            effective_target = by_contains(str(contains_value))
            locator_kind = "contains"
        else:
            if target is None:
                raise ValueError("Provide 'target' or one of: 'text' | 'contains_text'")
            # If target is a string (e.g., target="Text" with other params)
            # treat it as an exact text match for consistent behavior.
            if isinstance(target, str):
                effective_target = by_exact_match(target)
                locator_kind = "exact"
            else:
                effective_target = target
                locator_kind = "locator"

        # Step title
        if step_title is not None:
            title = step_title
        elif locator_kind == "exact":
            title = f'Click element with text: "{text_value}"'
        elif locator_kind == "contains":
            title = f'Click element containing: "{contains_value}"'
        else:
            title = f"Click element: {pretty_locator(self.driver, effective_target)}"

        # Execute step + artifacts/logs
        with allure.step(title):
            loc_str = pretty_locator(self.driver, effective_target)
            self._log.info(
                "Click on element",
                action="click",
                locator=str(loc_str),
                locator_kind=locator_kind,
                # Log only key wait params (others are passed through as-is)
                **{
                    k: v
                    for k, v in params.items()
                    if k in ("timeout", "index", "max_scrolls", "polling_ms")
                },
            )
            try:
                el = Waits.wait_for_elements(self.driver, effective_target, **params)
                try:
                    # First try the standard WebElement.click() which our tests stub and most drivers support
                    el.click()
                except Exception:
                    # Fallback to native gesture for tricky cases
                    self.driver.execute_script("mobile: clickGesture", {"elementId": el.id})
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("Error during click", action="click", locator=str(loc_str))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def type(
        self,
        target: PageElement | StrategyValue,
        text: str,
        clear: bool = True,
        **params: Any,
    ) -> None:
        """
        Waits for an element and types the given text into it.

        Args:
            target (PageElement | StrategyValue): Locator or strategy to find the element.
            text (str): Text to input.
            clear (bool): Whether to clear existing text before typing. Defaults to True.
            **params: Additional parameters forwarded to the wait function.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f'Type text: "{text}" into element: {loc}'
        with allure.step(title):
            # Reflect step in logs synchronously
            self._log.info(
                "Text input",
                action="type",
                locator=str(loc),
                text=text,
                clear=clear,
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                if clear:
                    el.clear()
                el.send_keys(text)
                # Artifacts on successful step (if allowed by config)
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("Error during text input", action="type", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def double_click(self, target: PageElement | StrategyValue, **params: Any) -> None:
        """
        Waits for an element and performs a double tap (double click gesture).

        Args:
            target (PageElement | StrategyValue): Locator or strategy to find the element.
            **params: Wait parameters (timeout, index, max_scrolls, etc.) and optional step.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Double click element: {loc}"
        with allure.step(title):
            self._log.info(
                "Double click on element",
                action="double_click",
                locator=str(loc),
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                try:
                    # Prefer native Appium gesture if available
                    self.driver.execute_script("mobile: doubleClickGesture", {"elementId": el.id})
                except Exception:
                    # Fallback - two quick standard clicks
                    el.click()
                    el.click()
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error(
                    "Error during double click", action="double_click", locator=str(loc)
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def long_click(
        self,
        target: PageElement | StrategyValue,
        duration_ms: int = 800,
        **params: Any,
    ) -> None:
        """
        Waits for an element and performs a long tap (long click gesture).

        Args:
            target (PageElement | StrategyValue): Locator or strategy to find the element.
            duration_ms (int): Hold duration in milliseconds. Defaults to 800 ms.
            **params: Wait parameters (timeout, index, max_scrolls, etc.) and optional step.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Long tap on element: {loc} ({duration_ms} ms)"
        with allure.step(title):
            self._log.info(
                "Long tap on element",
                action="long_click",
                locator=str(loc),
                duration_ms=duration_ms,
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                self.driver.execute_script(
                    "mobile: longClickGesture",
                    {"elementId": el.id, "duration": int(duration_ms)},
                )
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("Error during long tap", action="long_click", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def tap_at(
        self,
        x: int,
        y: int,
        *,
        step: str | None = None,
        settle_for: float = DEFAULT_TIMEOUT_BEFORE_EXPECTATION,
    ) -> None:
        """
        Tap at absolute screen coordinates.

        Args:
            x (int): X coordinate in the viewport.
            y (int): Y coordinate in the viewport.
            step (str | None): Step name for Allure.
            settle_for (float): UI stabilization wait before the gesture (sec). Defaults to Waits value.
        """
        title = step or f"Tap at coordinates: ({x}, {y})"
        with allure.step(title):
            self._log.info("Tap at coordinates", action="tap_at", x=x, y=y, settle_for=settle_for)
            try:
                if settle_for and settle_for > 0:
                    # Light wait for page stability
                    from selenium.webdriver.support.ui import WebDriverWait as _WebDriverWait

                    prev: str = self.driver.page_source

                    def _stable(drv: Any) -> bool:
                        nonlocal prev
                        from typing import cast as _cast

                        cur = _cast(str, drv.page_source)
                        ok: bool = cur == prev
                        prev = cur
                        return ok

                    _WebDriverWait(self.driver, settle_for).until(_stable)

                self.driver.execute_script("mobile: clickGesture", {"x": int(x), "y": int(y)})
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("Error tapping at coordinates", action="tap_at", x=x, y=y)
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def tap_center(self, target: PageElement | StrategyValue, **params: Any) -> None:
        """
        Waits for an element and taps its center.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Tap center of element: {loc}"
        with allure.step(title):
            self._log.info(
                "Tap center of element",
                action="tap_center",
                locator=str(loc),
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                # Native gesture: click at the center of the element
                self.driver.execute_script("mobile: clickGesture", {"elementId": el.id})
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("Error tapping center", action="tap_center", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def tap_offset(
        self,
        target: PageElement | StrategyValue,
        dx: int,
        dy: int,
        **params: Any,
    ) -> None:
        """
        Waits for an element and taps with an offset from its top-left corner.

        Args:
            target: Element used to compute the base point.
            dx (int): X offset from the element's top-left corner.
            dy (int): Y offset from the element's top-left corner.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Tap with offset ({dx},{dy}) from element: {loc}"
        with allure.step(title):
            self._log.info(
                "Tap with offset",
                action="tap_offset",
                locator=str(loc),
                dx=dx,
                dy=dy,
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                rect = getattr(el, "rect", None) or {}
                x0 = int(rect.get("x") or getattr(el, "location", {}).get("x", 0))
                y0 = int(rect.get("y") or getattr(el, "location", {}).get("y", 0))
                x = x0 + int(dx)
                y = y0 + int(dy)
                self.driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("Error during offset tap", action="tap_offset", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    # ===== Additional native gestures and system actions =====
    def _w3c_swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 500,
        steps: int = 1,
    ) -> None:
        """
        Universal smooth swipe via W3C actions.
        Instead of a single sharp movement we perform several small steps with pauses
        so that the gesture is perceived as a "drag" rather than a "flick".
        """
        finger = PointerInput("touch", "finger")

        actions = ActionChains(self.driver)
        actions.w3c_actions = ActionBuilder(self.driver, mouse=finger)
        a = actions.w3c_actions.pointer_action

        start_x = int(start_x)
        start_y = int(start_y)
        end_x = int(end_x)
        end_y = int(end_y)

        dx = end_x - start_x
        dy = end_y - start_y

        step_dx = dx / steps
        step_dy = dy / steps
        step_pause = (duration_ms / 1000.0) / steps

        # put finger at the starting point
        a.move_to_location(start_x, start_y)
        a.pointer_down()

        # move finger in small steps
        for i in range(1, steps + 1):
            x = int(start_x + step_dx * i)
            y = int(start_y + step_dy * i)
            a.pause(step_pause)
            a.move_to_location(x, y)

        a.release()
        actions.perform()

    def swipe_element(
        self,
        target: PageElement | StrategyValue,
        *,
        direction: Literal["up", "down", "left", "right"],
        duration_ms: int = 500,
        steps: int = 1,
        percent: float = 0.7,
        **params: Any,
    ) -> None:
        """Swipe on the element in the given direction by percent (0..1)."""
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Swipe on element: {loc} ({direction}, {int(percent*100)}%)"
        platform = (get_platform_from_driver(self.driver) or "").lower()

        with allure.step(title):
            self._log.info(
                "Swipe on element",
                action="swipe_element",
                locator=str(loc),
                direction=direction,
                percent=percent,
                platform=platform,
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                percent = max(0.01, min(1.0, float(percent)))

                if platform == "android":
                    # Keep native Android gesture
                    self.driver.execute_script(
                        "mobile: swipeGesture",
                        {
                            "elementId": el.id,
                            "direction": direction,
                            "percent": percent,
                        },
                    )
                else:
                    # iOS (and everything else) - W3C actions
                    rect = getattr(el, "rect", {}) or {}
                    x = rect.get("x", 0)
                    y = rect.get("y", 0)
                    w = rect.get("width", 0)
                    h = rect.get("height", 0)

                    start_x = end_x = int(x + w / 2)
                    start_y = end_y = int(y + h / 2)

                    if direction == "up":
                        start_y = int(y + h * 0.8)
                        end_y = int(start_y - h * percent)
                    elif direction == "down":
                        start_y = int(y + h * 0.2)
                        end_y = int(start_y + h * percent)
                    elif direction == "left":
                        start_x = int(x + w * 0.8)
                        end_x = int(start_x - w * percent)
                    elif direction == "right":
                        start_x = int(x + w * 0.2)
                        end_x = int(start_x + w * percent)
                    else:
                        raise ValueError(f"Unknown direction: {direction}")

                    self._w3c_swipe(start_x, start_y, end_x, end_y, duration_ms, steps)

                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error(
                    "Swipe error",
                    action="swipe_element",
                    locator=str(loc),
                    direction=direction,
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def swipe_screen(
        self,
        *,
        direction: Literal["up", "down", "left", "right"],
        duration_ms: int = 500,
        steps: int = 1,
        percent: float = 0.7,
        step: str | None = None,
    ) -> None:
        """Swipe on the screen in the given direction by percent (0..1)."""
        title = step or f"Swipe on screen: {direction}, {int(percent*100)}%"
        platform = (get_platform_from_driver(self.driver) or "").lower()

        with allure.step(title):
            self._log.info(
                "Screen swipe",
                action="swipe_screen",
                direction=direction,
                percent=percent,
                platform=platform,
            )
            try:
                size = self.driver.get_window_size()
                w, h = size.get("width", 0) or 0, size.get("height", 0) or 0
                percent = max(0.01, min(1.0, float(percent)))

                if platform == "android":
                    # Legacy behavior - via mobile: swipeGesture
                    left, top = max(int(w * 0.01), 1), max(int(h * 0.01), 1)
                    width, height = max(int(w * 0.7), 1), max(int(h * 0.7), 1)
                    self.driver.execute_script(
                        "mobile: swipeGesture",
                        {
                            "left": left,
                            "top": top,
                            "width": width,
                            "height": height,
                            "direction": direction,
                            "percent": percent,
                        },
                    )
                else:
                    # iOS - W3C swipe
                    center_x = int(w / 2)
                    center_y = int(h / 2)

                    start_x = end_x = center_x
                    start_y = end_y = center_y

                    if direction == "up":
                        start_y = int(h * 0.7)
                        end_y = int(start_y - h * percent)
                    elif direction == "down":
                        start_y = int(h * 0.3)
                        end_y = int(start_y + h * percent)
                    elif direction == "left":
                        start_x = int(w * 0.7)
                        end_x = int(start_x - w * percent)
                    elif direction == "right":
                        start_x = int(w * 0.3)
                        end_x = int(start_x + w * percent)
                    else:
                        raise ValueError(f"Unknown direction: {direction}")

                    self._w3c_swipe(start_x, start_y, end_x, end_y, duration_ms, steps)

                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error(
                    "Screen swipe error",
                    action="swipe_screen",
                    direction=direction,
                    platform=platform,
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def perform_scroll(
        self,
        count: int = 1,
        capacity: float = DEFAULT_SCROLL_CAPACITY,
        direction: Literal["up", "down", "left", "right"] = DEFAULT_SCROLL_DIRECTION,
        duration_ms: int = 1500,
        *,
        step: str | None = None,
    ) -> None:
        """Perform a full-screen scroll gesture."""

        capacity = min(max(capacity, 0.01), 1.0)
        percent_int = int(round(capacity * 100))
        title = step or f"Scroll {direction} by {percent_int}%"
        platform = (get_platform_from_driver(self.driver) or "").lower()

        with allure.step(title):
            self._log.info(
                "Screen scroll",
                action="perform_scroll",
                direction=direction,
                capacity=capacity,
                count=count,
                platform=platform,
            )
            try:
                try:
                    size = self.driver.get_window_size()
                    w, h = size.get("width", 0) or 0, size.get("height", 0) or 0
                except Exception:
                    w, h = 0, 0

                left = max(int(w * 0.01), 1)
                top = max(int(h * 0.01), 1)
                width = max(int(w * 0.7), 1)
                height = max(int(h * 0.7), 1)

                # for iOS - invert the direction, because swipe_screen operates
                # on the gesture direction, not the logical "screen scrolling"
                if platform == "ios":
                    invert = {
                        "up": "down",
                        "down": "up",
                        "left": "right",
                        "right": "left",
                    }

                    inv = invert.get(direction, direction)

                    if inv not in ("up", "down", "left", "right"):
                        raise ValueError(f"Invalid inverted direction: {inv}")

                    ios_swipe_direction: Literal["up", "down", "left", "right"] = inv  # type: ignore

                for _ in range(max(int(count), 1)):
                    if platform == "android":
                        # Android: keep mobile: scrollGesture with "logical" direction
                        try:
                            self.driver.execute_script(
                                "mobile: scrollGesture",
                                {
                                    "left": left,
                                    "top": top,
                                    "width": width,
                                    "height": height,
                                    "direction": direction,
                                    "percent": capacity,
                                },
                            )
                        except Exception:
                            # swallow single gesture errors
                            pass
                    else:
                        # iOS: W3C swipe in gesture direction (inversion of logical direction)
                        try:
                            # how many steps to do per gesture
                            # 10–20 steps are usually enough for smoothness
                            steps = max(5, min(25, duration_ms // 40))  # ~40ms per step
                            self.swipe_screen(
                                direction=ios_swipe_direction, steps=steps, percent=capacity
                            )
                        except Exception:
                            pass

                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error(
                    "Error while performing scroll",
                    action="perform_scroll",
                    direction=direction,
                    capacity=capacity,
                    platform=platform,
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def scroll_until_visible(
        self,
        target: PageElement | StrategyValue,
        *,
        direction: Literal["up", "down", "left", "right"] = "down",
        max_scrolls: int = 5,
        percent: float = 0.7,
        **params: Any,
    ) -> None:
        """Scroll the screen until the element becomes visible, or we exhaust attempts.

        Uses perform_scroll, which already contains platform-specific logic inside
        (Android - via mobile: scrollGesture, iOS - via W3C swipe).
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Scroll to element: {loc} (≤{max_scrolls} times)"
        percent = max(0.01, min(1.0, float(percent)))

        with allure.step(title):
            self._log.info(
                "Scroll until visible",
                action="scroll_until_visible",
                locator=str(loc),
                direction=direction,
                max_scrolls=max_scrolls,
                percent=percent,
            )
            try:
                for _ in range(max(1, int(max_scrolls))):
                    el = Waits.wait_for_element_or_none(self.driver, target, **params)
                    if el:
                        self.report_manager.attach_screenshot_if_allowed(
                            self.driver, when="success"
                        )
                        return

                    # Scroll the screen by the specified percent in the desired direction
                    self.perform_scroll(
                        count=1,
                        capacity=percent,
                        direction=direction,
                    )

                # If the element still did not appear
                raise RuntimeError(
                    f"Element did not become visible after {max_scrolls} scrolls: {loc}"
                )
            except Exception:
                self._log.error(
                    "Failed to scroll to element",
                    action="scroll_until_visible",
                    locator=str(loc),
                    direction=direction,
                    max_scrolls=max_scrolls,
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def drag_and_drop(
        self,
        source: PageElement | StrategyValue,
        target: PageElement | StrategyValue,
        **params: Any,
    ) -> None:
        """Drag source element to the center of the target element via mobile: dragGesture."""
        step_title = params.pop("step", None) or params.pop("step_title", None)
        src_s = pretty_locator(self.driver, source)
        dst_s = pretty_locator(self.driver, target)
        title = step_title or f"Drag {src_s} → {dst_s}"
        with allure.step(title):
            self._log.info(
                "Drag&Drop",
                action="drag_and_drop",
                source=str(src_s),
                target=str(dst_s),
            )
            try:
                src_el = Waits.wait_for_elements(self.driver, source, **params)
                dst_el = Waits.wait_for_elements(self.driver, target, **params)
                rect = getattr(dst_el, "rect", {})
                end_x = int((rect.get("x", 0)) + (rect.get("width", 0)) / 2)
                end_y = int((rect.get("y", 0)) + (rect.get("height", 0)) / 2)
                self.driver.execute_script(
                    "mobile: dragGesture",
                    {"elementId": src_el.id, "endX": end_x, "endY": end_y, "speed": 800},
                )
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error(
                    "Drag&Drop error", action="drag_and_drop", source=str(src_s), target=str(dst_s)
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def pinch_open(
        self, target: PageElement | StrategyValue, percent: float = 0.8, **params: Any
    ) -> None:
        """Zoom in (pinch open) on an element - iOS `pinchOpenGesture`."""
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Pinch Open (zoom in) on element: {loc}"
        with allure.step(title):
            self._log.info("PinchOpen", action="pinch_open", locator=str(loc), percent=percent)
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                self.driver.execute_script(
                    "mobile: pinchOpenGesture",
                    {"elementId": el.id, "percent": max(0.01, min(1.0, float(percent)))},
                )
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("PinchOpen error", action="pinch_open", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def pinch_close(
        self, target: PageElement | StrategyValue, percent: float = 0.8, **params: Any
    ) -> None:
        """Zoom out (pinch close) on an element - iOS `pinchCloseGesture`."""
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Pinch Close (zoom out) on element: {loc}"
        with allure.step(title):
            self._log.info("PinchClose", action="pinch_close", locator=str(loc), percent=percent)
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                self.driver.execute_script(
                    "mobile: pinchCloseGesture",
                    {"elementId": el.id, "percent": max(0.01, min(1.0, float(percent)))},
                )
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("PinchClose error", action="pinch_close", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    # ---- System actions ----
    def hide_keyboard(self, step: str | None = None) -> None:
        title = step or "Hide keyboard"
        with allure.step(title):
            self._log.info("Hide keyboard", action="hide_keyboard")
            try:
                hide_fn = getattr(self.driver, "hide_keyboard", None)
                if not callable(hide_fn):
                    raise RuntimeError("Method hide_keyboard not implemented in this driver")
                hide_fn()
            except Exception:
                # Not always critical, but artifacts may help
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def open_notifications(self, step: str | None = None) -> None:
        """Android: open the notifications shade."""
        title = step or "Open notification panel"
        with allure.step(title):
            self._log.info("Open notifications", action="open_notifications")
            try:
                if hasattr(self.driver, "open_notifications"):
                    self.driver.open_notifications()
                else:
                    raise RuntimeError("open_notifications method is not available on the driver")
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def android_press_keycode(
        self, keycode: int, metastate: int | None = None, step: str | None = None
    ) -> None:
        """Android: send a KeyEvent (e.g., BACK=4, ENTER=66, etc.)."""
        title = step or f"Press Android keycode: {keycode}"
        with allure.step(title):
            self._log.info(
                "Android keycode",
                action="android_press_keycode",
                keycode=keycode,
                metastate=metastate,
            )
            try:
                if hasattr(self.driver, "press_keycode"):
                    if metastate is None:
                        self.driver.press_keycode(keycode)
                    else:
                        self.driver.press_keycode(keycode, metastate)
                else:
                    raise RuntimeError("press_keycode method is not available on this driver")
            except Exception:
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def perform_native_action(
        self,
        android_key: int | None = None,
        ios_key: str | None = None,
        step: str | None = None,
    ) -> None:
        """
        Generic method for sending native commands (e.g., key presses) to the mobile device.

        Use this method to send platform-dependent commands within test scenarios.

        Args:
            android_key: Android key code (e.g., BACK=4, ENTER=66).
                         Used for Android; ignored on other platforms.
            ios_key: String key for iOS (e.g., "\n" for Enter/Return).
                     Used for iOS; ignored on other platforms.

        Exceptions:
            ValueError: if the required parameter for the platform is not provided.
            RuntimeError: if called for an unsupported platform or the driver is not initialized.
        """
        platform = (get_platform_from_driver(self.driver) or "").lower()
        title = step or "Send native command"
        with allure.step(title):
            self._log.info(
                "Native action",
                action="perform_native_action",
                platform=platform,
                android_key=android_key,
                ios_key=ios_key,
            )
            try:
                if platform == "android":
                    if android_key is None:
                        raise ValueError(
                            "Parameter android_key is required for the Android platform"
                        )
                    # Reuse the existing method
                    self.android_press_keycode(android_key)
                    self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                    return

                if platform == "ios":
                    if ios_key is None:
                        raise ValueError("Parameter ios_key is required for the iOS platform")
                    # Try via mobile: type (recommended way for iOS)
                    sent = False
                    try:
                        self.driver.execute_script("mobile: type", {"text": ios_key})
                        sent = True
                    except Exception:
                        # Fallback: send to the active field
                        try:
                            el = self.driver.switch_to.active_element
                            el.send_keys(ios_key)
                            sent = True
                        except Exception:
                            sent = False
                    if not sent:
                        raise RuntimeError("Failed to send native key on iOS")
                    self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                    return

                # Platform not recognized
                raise RuntimeError("perform_native_action supports only Android and iOS")
            except Exception:
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def tap_enter(self) -> None:
        """
        Performs a native Enter (or Return) key press on the mobile device.

        Uses platform-dependent keys for Android and iOS:
        - Android: 66 (KEYCODE_ENTER)
        - iOS: "\n"
        """
        self.perform_native_action(android_key=66, ios_key="\n", step="Press Enter/Return")

    def get_attribute_value(
        self,
        target: PageElement | StrategyValue,
        attr: str,
        **params: Any,
    ) -> str | None:
        """
        Waits for an element and returns the value of the specified attribute.

        Example step: “Get the value of the content-desc attribute from element <locator>”.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Get attribute {attr} from element: {loc}"
        with allure.step(title):
            self._log.info(
                "Get attribute value",
                action="get_attribute_value",
                locator=str(loc),
                attribute=attr,
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                value = el.get_attribute(attr)
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return value
            except Exception:
                self._log.error(
                    "Error getting attribute value",
                    action="get_attribute_value",
                    locator=str(loc),
                    attribute=attr,
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def get_text(self, target: PageElement | StrategyValue, **params: Any) -> str:
        """
        Waits for an element and returns its text (element.text), adding a step and logging.

        On error attaches artifacts (screenshot, page_source).
        Example step: “Get text from element: <locator>”.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Get text from element: {loc}"
        with allure.step(title):
            self._log.info(
                "Get element text",
                action="get_text",
                locator=str(loc),
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                text = getattr(el, "text", None)
                # In Appium `.text` is a property; cast to str for consistency
                text_str = str(text) if text is not None else ""
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return text_str
            except Exception:
                self._log.error("Error getting text", action="get_text", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def get_number(self, target: PageElement | StrategyValue, **params: Any) -> float:
        """
        Based on get_text(): reads the element text and tries to extract a number.

        - Parses integers/floats considering locales and separators (via NumberParser).
        - If conversion is not possible, raises ValueError with the original text.
        Example step: “Read numeric value from element: <locator>”.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Read numeric value from element: {loc}"
        with allure.step(title):
            try:
                raw = self.get_text(target, **params)
                value = NumberParser.extract_first_number(raw)
                if value is None:
                    self._log.error(
                        "Failed to parse number",
                        action="get_number",
                        locator=str(loc),
                        original_text=raw,
                    )
                    # On error, attach artifacts as with other actions
                    self.report_manager.attach_artifacts_on_failure(self.driver)
                    raise ValueError(f"Failed to parse a number from string: '{raw}'")
                # Successful step - log and attach screenshot if needed
                self._log.info(
                    "Numeric value read",
                    action="get_number",
                    locator=str(loc),
                    value=value,
                    original_text=raw,
                )
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return float(value)
            except Exception:
                # Any unexpected errors should also be accompanied by artifacts
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def get_dom_attribute(
        self,
        target: PageElement | StrategyValue,
        attr: str,
        **params: Any,
    ) -> str | None:
        """
        Waits for an element and returns a DOM attribute value (via `element.get_dom_attribute`).

        If the element lacks `get_dom_attribute`, falls back to `get_attribute`.
        Example step: “Get DOM attribute id from element <locator>”.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Get DOM attribute {attr} from element: {loc}"
        with allure.step(title):
            self._log.info(
                "Get DOM attribute",
                action="get_dom_attribute",
                locator=str(loc),
                attribute=attr,
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                getter = getattr(el, "get_dom_attribute", None)
                value = getter(attr) if callable(getter) else el.get_attribute(attr)
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return value
            except Exception:
                self._log.error(
                    "Error getting DOM attribute",
                    action="get_dom_attribute",
                    locator=str(loc),
                    attribute=attr,
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def value_of_css_property(
        self,
        target: PageElement | StrategyValue,
        name: str,
        **params: Any,
    ) -> str:
        """
        Waits for an element and returns the value of CSS property `name`
        (via `element.value_of_css_property`).

        Example step: “Get CSS property 'color' from element <locator>”.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f'Get CSS property "{name}" from element: {loc}'
        with allure.step(title):
            self._log.info(
                "Get CSS property",
                action="value_of_css_property",
                locator=str(loc),
                property=name,
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                getter = getattr(el, "value_of_css_property", None)
                value = getter(name) if callable(getter) else None
                value_str = str(value) if value is not None else ""
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return value_str
            except Exception:
                self._log.error(
                    "Error getting CSS property",
                    action="value_of_css_property",
                    locator=str(loc),
                    property=name,
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def is_enabled(self, target: PageElement | StrategyValue, **params: Any) -> bool:
        """
        Waits for an element and returns its "enabled" state.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Verify element is enabled: {loc}"
        with allure.step(title):
            self._log.info(
                "Check element enabled",
                action="is_enabled",
                locator=str(loc),
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                value = bool(el.is_enabled())
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return value
            except Exception:
                self._log.error("Error checking enabled", action="is_enabled", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def is_selected(self, target: PageElement | StrategyValue, **params: Any) -> bool:
        """
        Waits for an element and returns its "selected" state.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Verify element is selected: {loc}"
        with allure.step(title):
            self._log.info(
                "Check element selected",
                action="is_selected",
                locator=str(loc),
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                value = bool(el.is_selected())
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return value
            except Exception:
                self._log.error("Error checking selected", action="is_selected", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def is_displayed(self, target: PageElement | StrategyValue, **params: Any) -> bool:
        """
        Waits for an element and returns the result of is_displayed().
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Verify element is displayed: {loc}"
        with allure.step(title):
            self._log.info(
                "Check element visibility",
                action="is_displayed",
                locator=str(loc),
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                value = bool(el.is_displayed())
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                return value
            except Exception:
                self._log.error(
                    "Error checking visibility", action="is_displayed", locator=str(loc)
                )
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    def submit(self, target: PageElement | StrategyValue, **params: Any) -> None:
        """
        Waits for an element and submits a form via it (`element.submit()`).

        If submit is unavailable, a fallback is performed by sending the Enter key to the element.
        Example step: “Submit form via element: <locator>”.
        """
        step_title = params.pop("step", None) or params.pop("step_title", None)
        loc = pretty_locator(self.driver, target)
        title = step_title or f"Submit form via element: {loc}"
        with allure.step(title):
            self._log.info(
                "Submit form",
                action="submit",
                locator=str(loc),
                **{k: v for k, v in params.items() if k in ("timeout", "index", "max_scrolls")},
            )
            try:
                el = Waits.wait_for_elements(self.driver, target, **params)
                try:
                    submit_method = getattr(el, "submit", None)
                    if callable(submit_method):
                        submit_method()
                    else:
                        raise AttributeError("Element has no submit() method")
                except Exception:
                    # Fallback: send Enter to the element
                    try:
                        el.send_keys("\n")
                    except Exception:
                        raise
                self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
            except Exception:
                self._log.error("Error during form submit", action="submit", locator=str(loc))
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    # ======== Deeplink handling ========
    def open_deeplink(self, deeplink: str) -> None:
        """
        Open a deeplink on the mobile device depending on the platform.

        Android:
         - Uses Appium Mobile Command `mobile: deepLink` with url + package parameters.
        iOS:
         - First, try `mobile: deepLink` with bundleId (if provided in config).
         - On error/absence of bundleId - fallback via simulator: `xcrun simctl openurl` to a local
           page that contains a link with id=deeplink.
        """
        platform = (get_platform_from_driver(self.driver) or "").lower()
        settings = load_settings()

        with allure.step(f"Open deeplink: {deeplink}"):
            self._log.info("Open deeplink", action="open_deeplink", platform=platform, url=deeplink)
            try:
                if platform == "android":
                    app_package: str | None = getattr(
                        getattr(settings, "android", None), "app_package", None
                    )
                    if not app_package:
                        raise ValueError("Android configuration lacks app_package for deepLink")
                    self.driver.execute_script(
                        "mobile: deepLink", {"url": str(deeplink), "package": str(app_package)}
                    )
                    self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                    return

                if platform == "ios":
                    bundle_id: str = (
                        getattr(getattr(settings, "ios", None), "bundle_id", None) or ""
                    ).strip()
                    if bundle_id:
                        try:
                            self.driver.execute_script(
                                "mobile: deepLink", {"url": str(deeplink), "bundleId": bundle_id}
                            )
                            self.report_manager.attach_screenshot_if_allowed(
                                self.driver, when="success"
                            )
                            return
                        except Exception as e:
                            self._log.warning(
                                f"iOS deepLink via Appium failed, falling back to simulator: {e}",
                                action="open_deeplink",
                                platform=platform,
                            )
                    # Fallback via simulator
                    self._ios_deeplink_via_simulator(deeplink, settings)
                    self.report_manager.attach_screenshot_if_allowed(self.driver, when="success")
                    return

                raise ValueError("Unsupported platform for deeplink. Expected android or ios")
            except Exception:
                self.report_manager.attach_artifacts_on_failure(self.driver)
                raise

    # --- Helper methods for iOS deeplink ---
    def _ios_deeplink_via_simulator(self, deeplink: str, settings: Any) -> None:
        # 1) Spin up a simple local HTTP server serving deeplink.html
        html = (
            '<html><head><meta name="viewport" content="initial-scale=2"></head>'
            '<body><a id="deeplink">deeplink</a>'
            '<script type="text/javascript">'
            "const params = new URLSearchParams(window.location.search);"
            'var deeplink = document.getElementById("deeplink");'
            "deeplink.href = params.get('url');"
            "</script></body></html>"
        )

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - method name defined by the base class
                if self.path.startswith("/deeplink.html"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, fmt: str, *args: Any) -> None:
                # Suppress logs from the built-in server
                return

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            encoded = _url_quote(deeplink, safe="")
            url = f"http://127.0.0.1:{port}/deeplink.html?url={encoded}"

            # 2) Open the URL in the simulator via xcrun simctl openurl
            caps = getattr(self.driver, "capabilities", {}) or {}
            udid = (
                getattr(getattr(settings, "ios", None), "udid", None)
                or caps.get("udid")
                or caps.get("appium:udid")
                or "booted"
            )
            cmd = ["xcrun", "simctl", "openurl", str(udid), url]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except Exception as e:
                self._log.error(
                    "Failed to execute simctl openurl", action="open_deeplink", error=str(e)
                )
                raise RuntimeError("Unable to open deeplink via simulator") from e

            # 3) Wait for the deeplink element (iOS) and click it
            self.click(
                PageElement(ios=by_accessibility_id("deeplink")),
                timeout=15,
                step="Tap deeplink link on the page",
            )
        finally:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Literal, cast

import allure
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from ..reporting.manager import ReportManager
from ..utils.logging import get_logger
from .locators import PageElement, StrategyValue, pretty_locator, resolve_to_selenium

# ---- Default values ----
DEFAULT_TIMEOUT_BEFORE_EXPECTATION = 0
DEFAULT_TIMEOUT_EXPECTATION = 5
DEFAULT_TIMEOUT_EVENT_EXPECTATION = 10
DEFAULT_POLLING_INTERVAL_MS = 500
DEFAULT_SCROLL_COUNT = 0
DEFAULT_SCROLL_CAPACITY = 1.0  # Value in range 0..1
DEFAULT_SCROLL_DIRECTION: Literal["up", "down", "left", "right"] = "down"

_log = get_logger(__name__)


class Waits:
    """
    Helper class providing waiting mechanisms for UI elements.

    Supports waiting with scrolling, configurable polling,
    and validation that a certain set of elements is visible.
    """

    @staticmethod
    def wait_for_elements(
        driver: WebDriver,
        target: PageElement | StrategyValue,
        *,
        index: int | None = None,
        settle_for: float = DEFAULT_TIMEOUT_BEFORE_EXPECTATION,
        timeout: float = DEFAULT_TIMEOUT_EXPECTATION,
        polling_ms: int = DEFAULT_POLLING_INTERVAL_MS,
        max_scrolls: int = DEFAULT_SCROLL_COUNT,
        scroll_percent: float = DEFAULT_SCROLL_CAPACITY,
        scroll_direction: Literal["up", "down", "left", "right"] = DEFAULT_SCROLL_DIRECTION,
    ) -> WebElement:
        """
        Wait for a visible element and return the N-th visible one (1-based index).

        Args:
            driver (WebDriver): Selenium/Appium driver instance.
            target (PageElement | StrategyValue): Locator to search for.
            index (int, optional): Index of the element to return (1-based). Defaults to 1.
            settle_for (float): Wait before starting the search (to stabilize UI).
            timeout (float): Maximum wait time.
            polling_ms (int): Polling interval in milliseconds.
            max_scrolls (int): Maximum number of scroll attempts if element is not found.
            scroll_percent (float): Portion of the screen to scroll (0..1).
            scroll_direction (Literal): Scroll direction (default "down").

        Returns:
            WebElement: The found element.

        Raises:
            NoSuchElementException: If the element is not found within timeout and after scrolling.
        """
        loc = pretty_locator(driver, target)
        title = (
            f"Wait for element: {loc} "
            f"(timeout={timeout}s, polling={polling_ms}ms, scrolls={max_scrolls})"
        )
        with allure.step(title):
            # Technical logging of wait parameters
            _log.debug(
                "Waiting for element",
                action="wait",
                locator=str(loc),
                timeout=timeout,
                polling_ms=polling_ms,
                max_scrolls=max_scrolls,
                settle_for=settle_for,
                index=index,
                scroll_percent=scroll_percent,
                scroll_direction=scroll_direction,
            )
            try:
                if settle_for and settle_for > 0:
                    _wait_for_ui_stability(driver, settle_for, polling_ms)

                wait = WebDriverWait(driver, timeout, poll_frequency=polling_ms / 1000.0)

                # Initialize the controller once for potential scroll actions
                from .controller import MobileController

                controller = MobileController(driver, ReportManager.get_default())

                current_scroll = 0
                while True:
                    tuples: list[StrategyValue] = resolve_to_selenium(driver, target)

                    last_exc: Exception | None = None
                    attempted: list[StrategyValue] = []
                    failed: list[StrategyValue] = []

                    safe_index = index or 1
                    if safe_index < 1:
                        raise IndexError(f"Index must be >= 1, got {safe_index}")

                    # Try all locators until one succeeds
                    for t in tuples:
                        try:
                            attempted.append(t)
                            visible_list = cast(
                                list[WebElement], wait.until(_nth_visible_condition(t, safe_index))
                            )
                            _log.debug(
                                "Element found",
                                action="wait",
                                locator=str(loc),
                                index=safe_index,
                                used_locator=str(t),
                            )
                            return visible_list[safe_index - 1]
                        except Exception as e:
                            last_exc = e
                            failed.append(t)
                            continue

                    # If allowed - perform scroll and retry
                    if max_scrolls > 0 and current_scroll < max_scrolls:
                        controller.perform_scroll(
                            count=1,
                            capacity=scroll_percent,
                            direction=scroll_direction,
                        )
                        current_scroll += 1
                        _log.debug(
                            "Scroll performed",
                            action="scroll",
                            locator=str(loc),
                            current_scroll=current_scroll,
                            capacity=scroll_percent,
                            direction=scroll_direction,
                        )
                        continue

                    # Build debug info for error message
                    locators_info = (
                        f"The following locators {failed} from {attempted} were not found."
                        if failed
                        else (
                            f"Attempts were made to find the following locators: {attempted}"
                            if attempted
                            else "No locator search attempts were made"
                        )
                    )
                    if last_exc is not None:
                        _log.error(
                            "Element not found",
                            action="wait",
                            locator=str(loc),
                            timeout=timeout,
                            scrolls=current_scroll,
                            attempted=len(attempted) or 0,
                            last_error=str(last_exc),
                        )
                        raise NoSuchElementException(
                            f"Elements were not found within '{timeout}' seconds after "
                            f"'{current_scroll}' scroll(s). {locators_info}. "
                            f"Original error: {last_exc}"
                        ) from last_exc
                    _log.error(
                        "Element not found",
                        action="wait",
                        locator=str(loc),
                        timeout=timeout,
                        scrolls=current_scroll,
                        attempted=len(attempted) or 0,
                    )
                    raise NoSuchElementException(
                        f"Elements were not found within '{timeout}' seconds after "
                        f"'{current_scroll}' scroll(s). {locators_info}"
                    )
            except Exception:
                # On wait step failure - attach artifacts centrally
                ReportManager.get_default().attach_artifacts_on_failure(driver)
                raise

    @staticmethod
    def wait_for_element_or_none(
        driver: WebDriver,
        target: PageElement | StrategyValue,
        *,
        index: int | None = None,
        settle_for: float = DEFAULT_TIMEOUT_BEFORE_EXPECTATION,
        timeout: float = DEFAULT_TIMEOUT_EXPECTATION,
        polling_ms: int = DEFAULT_POLLING_INTERVAL_MS,
        max_scrolls: int = DEFAULT_SCROLL_COUNT,
        scroll_percent: float = DEFAULT_SCROLL_CAPACITY,
        scroll_direction: Literal["up", "down", "left", "right"] = DEFAULT_SCROLL_DIRECTION,
    ) -> WebElement | None:
        """
        Same as wait_for_elements, but returns None instead of raising.

        Useful for optional elements whose absence is non-critical.

        Returns:
            WebElement | None: Found element or None if not found.
        """
        try:
            return Waits.wait_for_elements(
                driver=driver,
                target=target,
                index=index,
                settle_for=settle_for,
                timeout=timeout,
                polling_ms=polling_ms,
                max_scrolls=max_scrolls,
                scroll_percent=scroll_percent,
                scroll_direction=scroll_direction,
            )
        except NoSuchElementException:
            return None


# ---- Internal helper functions ----
def _nth_visible_condition(
    t: StrategyValue, n: int
) -> Callable[[WebDriver], list[WebElement] | bool]:
    """
    Create a WebDriverWait.until predicate that returns the list of visible elements
    when at least `n` are visible; otherwise returns False.
    """

    def _predicate(drv: WebDriver) -> list[WebElement] | bool:
        try:
            els: list[WebElement] = drv.find_elements(*t)
        except Exception:
            return False
        visible = [e for e in els if _is_displayed_safe(e)]
        return visible if len(visible) >= n else False

    return _predicate


def _is_displayed_safe(el: WebElement) -> bool:
    """Safely check if element is displayed, ignoring exceptions."""
    try:
        return bool(el.is_displayed())
    except Exception:
        return False


def _any_visible(tuples: Sequence[StrategyValue]) -> Callable[[WebDriver], WebElement | bool]:
    """
    Return a predicate that finds and returns the first visible element
    among the given locators, or False if none are visible.
    """

    def _predicate(driver: WebDriver) -> WebElement | bool:
        for by, value in tuples:
            try:
                el: WebElement = driver.find_element(by, value)
                if el and el.is_displayed():
                    return el
            except Exception:
                continue
        return False

    return _predicate


def _wait_for_ui_stability(driver: WebDriver, timeout_seconds: float, polling_ms: int) -> None:
    """
    Wait until the UI stabilizes (page source stops changing), or timeout elapses.

    Useful to avoid race conditions after navigation or animations.
    """
    end = time.monotonic() + timeout_seconds
    previous: str | None = None
    while time.monotonic() < end:
        try:
            current = driver.page_source
        except Exception:
            return
        if previous is not None and current == previous:
            return
        previous = current
        time.sleep(max(polling_ms, 50) / 1000.0)

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Literal, cast

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from .locators import PageElement, StrategyValue, resolve_to_selenium

# ---- Default values ----
DEFAULT_TIMEOUT_BEFORE_EXPECTATION = 0
DEFAULT_TIMEOUT_EXPECTATION = 20
DEFAULT_POLLING_INTERVAL_MS = 500
DEFAULT_SCROLL_COUNT = 0
DEFAULT_SCROLL_CAPACITY = 0.7  # Value between 0..1
DEFAULT_SCROLL_DIRECTION: Literal["up", "down", "left", "right"] = "down"


class Waits:
    """
    Utility class that provides waiting mechanisms for UI elements.

    Includes support for waiting with scrolling, custom polling,
    and ensuring that a certain number of elements are visible.
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
            index (int, optional): 1-based index of element to return. Defaults to 1.
            settle_for (float): Wait time before starting element search (for UI stabilization).
            timeout (float): Maximum time to wait for the element.
            polling_ms (int): Polling interval in milliseconds.
            max_scrolls (int): Maximum number of scroll attempts if element not found.
            scroll_percent (float): How far to scroll (0..1).
            scroll_direction (Literal): Direction to scroll ("down" by default).

        Returns:
            WebElement: The found element.

        Raises:
            NoSuchElementException: If element cannot be found after timeout and scroll attempts.
        """
        if settle_for and settle_for > 0:
            _wait_for_ui_stability(driver, settle_for, polling_ms)

        wait = WebDriverWait(driver, timeout, poll_frequency=polling_ms / 1000.0)

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
                    return visible_list[safe_index - 1]
                except Exception as e:
                    last_exc = e
                    failed.append(t)
                    continue

            # Scroll if allowed, then try again
            if max_scrolls > 0 and current_scroll < max_scrolls:
                _perform_scroll(
                    driver, count=1, capacity=scroll_percent, direction=scroll_direction
                )
                current_scroll += 1
                continue

            # Build debug info for exception message
            locators_info = (
                f"The following locators {failed} from {attempted} were not found."
                if failed
                else (
                    f"Attempted to find the following elements: {attempted}"
                    if attempted
                    else "No elements were found"
                )
            )
            if last_exc is not None:
                raise NoSuchElementException(
                    f"Elements were not found within '{timeout}' seconds after "
                    f"'{current_scroll}' scrolls. {locators_info}. Cause: {last_exc}"
                ) from last_exc
            raise NoSuchElementException(
                f"Elements were not found within '{timeout}' seconds after "
                f"'{current_scroll}' scrolls. {locators_info}"
            )

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
        Same as wait_for_elements, but returns None instead of raising an exception.

        Useful for optional elements where failure is not critical.

        Returns:
            WebElement | None: Found element, or None if not found.
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
    Create a function for WebDriverWait.until that returns a list of visible elements
    when at least `n` elements are visible; otherwise returns False.
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
    """Safely check if an element is displayed, ignoring exceptions."""
    try:
        return bool(el.is_displayed())
    except Exception:
        return False


def _any_visible(tuples: Sequence[StrategyValue]) -> Callable[[WebDriver], WebElement | bool]:
    """
    Return a predicate function that finds and returns the first visible element
    among the provided locators, or False if none are visible.
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
    Wait until the UI stabilizes (page source stops changing) or timeout is reached.
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


def _perform_scroll(
    driver: WebDriver,
    count: int = 1,
    capacity: float = DEFAULT_SCROLL_CAPACITY,
    direction: Literal["up", "down", "left", "right"] = DEFAULT_SCROLL_DIRECTION,
) -> None:
    """
    Perform a scroll gesture using Appium's `mobile: scrollGesture` endpoint.

    Args:
        driver (WebDriver): Appium driver.
        count (int): Number of scroll attempts to perform.
        capacity (float): Percentage of the screen to scroll (0..1).
        direction (Literal): Scroll direction.
    """
    capacity = min(max(capacity, 0.01), 1.0)
    try:
        size = driver.get_window_size()
        w, h = size.get("width", 0) or 0, size.get("height", 0) or 0
    except Exception:
        w, h = 0, 0

    left = max(int(w * 0.1), 1)
    top = max(int(h * 0.1), 1)
    width = max(int(w * 0.8), 1)
    height = max(int(h * 0.8), 1)

    for _ in range(max(count, 1)):
        try:
            driver.execute_script(
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
            pass

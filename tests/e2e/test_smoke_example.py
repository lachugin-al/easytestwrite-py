from __future__ import annotations

import allure
import pytest

from mobiauto.core.controller import MobileController
from mobiauto.core.locators import PageElement, by_name, by_text
from mobiauto.core.optional import (
    only_android,
    only_ios,
    optional,
    optional_android,
    optional_for,
    optional_ios,
)
from mobiauto.network import EventVerifier

# --- Page elements definitions ---
# Example selector (cross-platform)
EXAMPLE = PageElement(
    android=by_text("android_locator"),
    ios=by_name("ios_locator"),
)
# Special non-existing element to demonstrate error suppression
NOTHING = PageElement(
    android=by_text("__no_such__"),
    ios=by_name("__no_such__"),
)


@allure.epic("Mobile application")
@allure.feature("Initialization and app launch")
@allure.story("User can open the app and select a example")
@allure.title("Verify app launch and example selection")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("smoke", "ui", "ios", "android", "demo")
@allure.description(
    """
This test verifies the basic availability of the mobile application on both Android and iOS.

**Steps:**
1. Open the application.
2. Ensure the app does not crash and the element is interactive.
"""
)
@pytest.mark.smoke
@pytest.mark.android
@pytest.mark.ios
def test_open_app(controller: MobileController, event_verifier: EventVerifier) -> None:
    """
    Basic smoke test + mini examples of using MobileController and EventVerifier.
    """

    # ---- Example 1. MobileController: visibility check + click ----
    controller.is_displayed(
        target=EXAMPLE,
        step="Check visibility of example selector element",
    )
    controller.click(
        target=EXAMPLE,
        step='Select example "Example"',
    )

    # Wait for the event by subset of data in the JSON body (no name filtering)
    event_verifier.check_has_event(
        event_data={"rich": 1},  # search key/value inside body.event.data
        timeout_sec=3,
    )

    # ---- Example 2.1. Passing locator from page_element_matched_event directly into click ----
    # As a demo: get a PageElement from event data and pass it to click directly.
    controller.click(
        target=event_verifier.page_element_matched_event(
            event_data={"items": [{"id": "42"}]},  # search item in data
            timeout_event_expectation=3,
            consume=False,
        ),
        timeout=0.5,
        step="click: element from page_element_matched_event (demo)",
    )

    # ---- Example 2.2. Locator by two key/value pairs in event_data (id=42 and rich=1) ----
    # Demonstrates searching for an item when data contains multiple key-value pairs.
    # Also passes result directly into click and wraps it with optional.
    controller.click(
        target=event_verifier.page_element_matched_event(
            event_data={"items": [{"id": "42"}], "rich": 1},  # search id and rich in data
            timeout_event_expectation=3,
            consume=False,
        ),
        timeout=0.5,
        step="click: element from page_element_matched_event (id=42, rich=1, demo)",
    )

    # ---- Example 2.3. Unknown nesting: search by keys without specifying levels ----
    # If nesting levels in event.data are unknown, you can pass a "flat" dict.
    controller.click(
        target=event_verifier.page_element_matched_event(
            # Search for elements where both id=42 and rich=1 appear anywhere in data
            event_data={"id": "42", "rich": 1},
            timeout_event_expectation=3,
            consume=False,
        ),
        timeout=0.5,
        step=("click: element from page_element_matched_event " "(flat dict, unknown nesting)"),
    )

    # ---- Example 2.4. Same, but event_data as a JSON string ----
    # If the data source already provides JSON as a string, it can be passed directly.
    controller.click(
        target=event_verifier.page_element_matched_event(
            event_data='{"id": "42", "rich": 1}',  # JSON string, nesting not specified
            timeout_event_expectation=3,
            consume=False,
        ),
        timeout=0.5,
        step=("click: element from page_element_matched_event " "(JSON string, unknown nesting)"),
    )

    # ---- Example 3. DSL optional: steps for all helper methods ----
    # Helper no-op step to demonstrate syntax without depending on UI
    def _noop_step(title: str) -> None:
        with allure.step(title):
            pass

    # 3.1 optional: executes all steps; errors are suppressed (suppress=True by default)
    optional(
        lambda: _noop_step("optional: simple no-op step"),
        # Demonstration of error suppression: click a guaranteed-missing element
        lambda: controller.click(
            target=NOTHING,
            timeout=0.1,
            step=("optional: click on missing element " "(error will be suppressed)"),
        ),
    )

    # 3.2 optional_for: executes steps only for the given platform
    optional_for(
        "ios",
        lambda: _noop_step("optional_for('ios'): example step for iOS only"),
    )
    optional_for(
        "android",
        lambda: _noop_step("optional_for('android'): example step for Android only"),
    )

    # 3.3 Shortcuts for specific platforms
    optional_ios(lambda: _noop_step("optional_ios: example step for iOS only"))
    optional_android(lambda: _noop_step("optional_android: example step for Android only"))

    # 3.4 only_ios / only_android: run only on their platform, exceptions are NOT suppressed
    only_ios(lambda: _noop_step("only_ios: mandatory step on iOS"))
    only_android(lambda: _noop_step("only_android: mandatory step on Android"))

    # ---- Example 4. MobileController: extended actions ----
    # 4.1 type: text input (clear=True/False)
    controller.type(
        target=NOTHING,
        text="demo",
        clear=True,
        timeout=0.1,
        step="type: input text (clear=True) - suppressed",
    )
    controller.type(
        target=NOTHING,
        text="append",
        clear=False,
        timeout=0.1,
        step="type: no clear (clear=False) - suppressed",
    )

    # 4.2 double_click / long_click
    controller.double_click(
        target=EXAMPLE,
        timeout=0.5,
        step="double_click: on example",
    )
    controller.long_click(
        target=EXAMPLE,
        duration_ms=600,
        timeout=0.5,
        step="long_click: on example",
    )

    # 4.3 tap_at / tap_center / tap_offset
    controller.tap_at(10, 10, step="tap_at: coordinates (10,10)")
    controller.tap_center(
        target=EXAMPLE,
        timeout=0.5,
        step="tap_center: on example",
    )
    controller.tap_offset(
        target=EXAMPLE,
        dx=5,
        dy=5,
        timeout=0.5,
        step="tap_offset: +5,+5 from example",
    )

    # 4.4 swipe_element / swipe_screen
    controller.swipe_element(
        target=EXAMPLE,
        direction="up",
        percent=0.3,
        timeout=0.5,
        step="swipe_element: example up by 30%",
    )
    controller.swipe_screen(
        direction="down",
        percent=0.2,
        step="swipe_screen: down by 20%",
    )

    # 4.5 scroll_until_visible
    controller.scroll_until_visible(
        target=EXAMPLE,
        direction="down",
        max_scrolls=1,
        percent=0.2,
        step="scroll_until_visible: example (≤1 scroll)",
    )

    # 4.6 drag_and_drop
    controller.drag_and_drop(
        source=NOTHING,
        target=NOTHING,
        timeout=0.1,
        step="drag_and_drop: NOTHING → NOTHING (suppressed demo)",
    )

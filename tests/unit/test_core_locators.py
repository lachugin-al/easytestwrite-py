from __future__ import annotations

from collections.abc import Callable

import pytest

from mobiauto.core.locators import (
    PageElement,
    by_accessibility_id,
    by_android_uiautomator,
    by_contains,
    by_id,
    by_ios_class_chain,
    by_ios_predicate_string,
    by_label,
    by_name,
    by_resource_id,
    by_text,
    by_value,
    by_xpath,
    get_platform_from_driver,
    resolve_to_selenium,
)


# ----------------- by_* factory functions -----------------
def test_higher_level_builders_return_expected_strategies() -> None:
    """Ensure each higher-level builder returns the expected strategy/value pair."""
    t = by_text("someone")
    assert t[0] == "xpath"
    assert "//*[@text = 'someone']" in t[1]

    rid = by_resource_id("login")
    assert rid[0] == "xpath"
    assert "contains(@resource-id,'login')" in rid[1]

    acc = by_accessibility_id("submit")
    assert acc[0] == "accessibility id"
    assert acc[1] == "submit"

    nm = by_name("Profile")
    assert nm[0] == "xpath"
    assert "contains(@name,'Profile')" in nm[1]

    val = by_value("123")
    assert val[0] == "xpath"
    assert "contains(@value,'123')" in val[1]

    lbl = by_label("Open")
    assert lbl[0] == "xpath"
    assert "contains(@label,'Open')" in lbl[1]

    cn = by_contains("foo")
    assert cn[0] == "xpath"
    assert "contains(@text,'foo')" in cn[1]

    x = by_xpath("//any")
    assert x[0] == "xpath" and x[1] == "//any"

    au = by_android_uiautomator('new UiSelector().description("X")')
    assert au[0] == "-android uiautomator"

    ip = by_ios_predicate_string('name == "X"')
    assert ip[0] == "-ios predicate string"

    ic = by_ios_class_chain("**/XCUIElementTypeAny")
    assert ic[0] == "-ios class chain"


@pytest.mark.parametrize(
    "func",
    [by_text, by_name, by_value, by_label, by_contains, by_xpath, by_id, by_resource_id],
)
def test_builders_none_raises(func: Callable[[str | None], tuple[str, str]]) -> None:
    """All builders must raise ValueError when called with None."""
    with pytest.raises(ValueError):
        func(None)


# ----------------- PageElement and platform resolution -----------------
class DummyDrv:
    """Driver stub exposing only the 'capabilities' field used by helpers."""

    def __init__(self, caps: dict[str, str]) -> None:
        self.capabilities = caps


def test_pageelement_get_and_get_all_android() -> None:
    """For Android, get_all should return all Android locators (list first)."""
    pe = PageElement(
        android=by_text("A"),
        ios=by_name("B"),
        android_list=[by_text("A"), by_contains("A2")],
    )
    drv = DummyDrv({"platformName": "Android"})
    tuples = resolve_to_selenium(drv, pe)
    assert isinstance(tuples, list) and len(tuples) == 2
    assert tuples[0][0] == "xpath"


def test_pageelement_get_and_get_all_ios() -> None:
    """For iOS, get_all should return iOS locators list preserving order."""
    pe = PageElement(
        android=by_text("A"),
        ios=by_name("someone"),
        ios_list=[by_name("someone"), by_label("someone")],
    )
    drv = DummyDrv({"appium:platformName": "iOS"})
    tuples = resolve_to_selenium(drv, pe)
    assert len(tuples) == 2
    assert tuples[0][0] == "xpath"
    assert "contains(@name,'someone')" in tuples[0][1]


def test_pageelement_missing_platform_raises() -> None:
    """get/get_all should raise if no locator exists for the requested platform."""
    pe = PageElement(android=by_text("A"))
    with pytest.raises(ValueError):
        pe.get("ios")
    with pytest.raises(ValueError):
        pe.get_all("unknown")


def test_resolve_to_selenium_accepts_plain_locator() -> None:
    """A plain StrategyValue should be wrapped into a single-item list."""
    drv = DummyDrv({"platformName": "Android"})
    loc = by_text("A")
    tuples = resolve_to_selenium(drv, loc)
    assert tuples == [("xpath", loc[1])]


def test_resolve_to_selenium_wrong_type_raises() -> None:
    """Non-supported types should cause a TypeError."""
    drv = DummyDrv({"platformName": "Android"})
    with pytest.raises(TypeError):
        resolve_to_selenium(drv, "not a locator")  # type: ignore[arg-type]


# ----------------- platform helpers -----------------
@pytest.mark.parametrize(
    "caps, expected",
    [
        ({"platformName": "Android"}, "android"),
        ({"appium:platformName": "iOS"}, "ios"),
        ({}, ""),
    ],
)
def test_get_platform_from_driver(caps: dict[str, str], expected: str) -> None:
    """get_platform_from_driver should normalize platform name from capabilities."""
    d = DummyDrv(caps)
    assert get_platform_from_driver(d) == expected

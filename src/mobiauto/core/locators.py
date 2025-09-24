from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

# --- Supported locator strategies and raw locator types ---
Strategy = Literal[
    "id",
    "accessibility id",
    "xpath",
    "-android uiautomator",
    "-ios predicate string",
    "-ios class chain",
]
StrategyValue = tuple[Strategy, str]


# -------- Factory functions (by_*) return StrategyValue --------
def _require(v: str | None, what: str) -> str:
    """Ensure that the locator value is not None, otherwise raise an error."""
    if v is None:
        raise ValueError(f"Element by {what} is not specified and is null.")
    return v


def by_id(v: str | None) -> StrategyValue:
    v = _require(v, "id")
    return ("xpath", f".//*[contains(@id,'{v}') or contains(@resource-id,'{v}')]")


def by_resource_id(v: str | None) -> StrategyValue:
    v = _require(v, "resource-id")
    return ("xpath", f".//*[contains(@resource-id,'{v}')]")


def by_text(v: str | None) -> StrategyValue:
    v = _require(v, "text")
    return ("xpath", f".//*[@text = '{v}']")


def by_contains(v: str | None) -> StrategyValue:
    v = _require(v, "contains")
    return (
        "xpath",
        ".//*[contains(@text,'{v}') or contains(@id,'{v}') or contains(@resource-id,'{v}') or "
        "contains(@content-desc,'{v}') or contains(@name,'{v}') or contains(@label,'{v}') or contains(@value,'{v}')]".replace(
            "{v}", v
        ),
    )


def by_exact_match(v: str | None) -> StrategyValue:
    v = _require(v, "exact match")
    return (
        "xpath",
        ".//*[(@text='{v}' or @id='{v}' or @resource-id='{v}' or @content-desc='{v}' or "
        "@name='{v}' or @label='{v}' or @value='{v}')]".replace("{v}", v),
    )


def by_content_desc(v: str | None) -> StrategyValue:
    v = _require(v, "content-desc")
    return ("xpath", f".//*[contains(@content-desc,'{v}')]")


def by_xpath(v: str | None) -> StrategyValue:
    v = _require(v, "xpath")
    return ("xpath", v)


def by_value(v: str | None) -> StrategyValue:
    v = _require(v, "value")
    return ("xpath", f".//*[contains(@value,'{v}')]")


def by_name(v: str | None) -> StrategyValue:
    v = _require(v, "name")
    return ("xpath", f".//*[contains(@name,'{v}')]")


def by_label(v: str | None) -> StrategyValue:
    v = _require(v, "label")
    return ("xpath", f".//*[contains(@label,'{v}')]")


def by_accessibility_id(v: str | None) -> StrategyValue:
    v = _require(v, "accessibility id")
    return ("accessibility id", v)


def by_android_uiautomator(v: str | None) -> StrategyValue:
    v = _require(v, "android uiautomator")
    return ("-android uiautomator", v)


def by_ios_class_chain(v: str | None) -> StrategyValue:
    v = _require(v, "ios class chain")
    return ("-ios class chain", v)


def by_ios_predicate_string(v: str | None) -> StrategyValue:
    v = _require(v, "ios predicate string")
    return ("-ios predicate string", v)


# -------- Cross-platform locator wrapper --------
@dataclass(frozen=True)
class PageElement:
    """
    Represents a cross-platform locator that can contain platform-specific strategies.
    Allows retrieving single or multiple locators depending on the platform.
    """

    android: StrategyValue | None = None
    ios: StrategyValue | None = None
    android_list: list[StrategyValue] | None = None
    ios_list: list[StrategyValue] | None = None

    def get(self, platform: str) -> StrategyValue:
        """
        Get a single locator for the given platform.

        Args:
            platform (str): "android" or "ios"

        Returns:
            StrategyValue: A tuple of (strategy, value)

        Raises:
            ValueError: If no locator is specified for the platform.
        """
        p = (platform or "").lower()
        if p == "android":
            if self.android:
                return self.android
            if self.android_list:
                return self.android_list[0]
            raise ValueError("Locator for Android is not specified")
        if p == "ios":
            if self.ios:
                return self.ios
            if self.ios_list:
                return self.ios_list[0]
            raise ValueError("Locator for iOS is not specified")
        raise ValueError(f"Unknown platform: {p}")

    def get_all(self, platform: str) -> list[StrategyValue]:
        """
        Get all locators for the given platform.

        Args:
            platform (str): "android" or "ios"

        Returns:
            list[StrategyValue]: A list of tuples with all available locators.
        """
        p = (platform or "").lower()
        if p == "android":
            if self.android_list:
                return list(self.android_list)
            if self.android:
                return [self.android]
            return []
        if p == "ios":
            if self.ios_list:
                return list(self.ios_list)
            if self.ios:
                return [self.ios]
            return []
        raise ValueError(f"Unknown platform: {p}")

    # Convenient factory methods
    @staticmethod
    def by_accessibility_id(acc_id: str) -> PageElement:
        loc = by_accessibility_id(acc_id)
        return PageElement(android=loc, ios=loc)

    @staticmethod
    def by_android_accessibility_id(acc_id: str) -> PageElement:
        return PageElement(android=by_accessibility_id(acc_id))

    @staticmethod
    def by_ios_accessibility_id(acc_id: str) -> PageElement:
        return PageElement(ios=by_accessibility_id(acc_id))

    @staticmethod
    def by_android_uiautomator(expr: str) -> PageElement:
        return PageElement(android=by_android_uiautomator(expr))

    @staticmethod
    def by_ios_class_chain(expr: str) -> PageElement:
        return PageElement(ios=by_ios_class_chain(expr))

    @staticmethod
    def by_ios_predicate_string(expr: str) -> PageElement:
        return PageElement(ios=by_ios_predicate_string(expr))

    @staticmethod
    def by_android_locators(locators: Sequence[StrategyValue]) -> PageElement:
        return PageElement(android_list=list(locators))

    @staticmethod
    def by_ios_locators(locators: Sequence[StrategyValue]) -> PageElement:
        return PageElement(ios_list=list(locators))

    @staticmethod
    def by_locators(
        android_locators: Sequence[StrategyValue] | None = None,
        ios_locators: Sequence[StrategyValue] | None = None,
    ) -> PageElement:
        return PageElement(
            android_list=list(android_locators) if android_locators else None,
            ios_list=list(ios_locators) if ios_locators else None,
        )


# ---------- Utility functions ----------
def get_platform_from_driver(driver: Any) -> str:
    """
    Extract the platform name from driver capabilities.

    Args:
        driver (Any): Appium/Selenium driver instance.

    Returns:
        str: Lowercased platform name ("android" or "ios").
    """
    caps = getattr(driver, "capabilities", None) or {}
    platform = (caps.get("platformName") or caps.get("appium:platformName") or "").lower()
    return platform


def resolve_to_selenium(driver: Any, locator: StrategyValue | PageElement) -> list[StrategyValue]:
    """
    Normalize a locator into a list of (strategy, value) tuples,
    resolving platform-specific locators when a PageElement is provided.

    Args:
        driver (Any): Appium/Selenium driver instance.
        locator (StrategyValue | PageElement): Either a raw locator tuple or a PageElement.

    Returns:
        list[StrategyValue]: List of locator tuples suitable for WebDriver find operations.

    Raises:
        TypeError: If locator is neither StrategyValue nor PageElement.
    """
    if isinstance(locator, tuple) and len(locator) == 2:
        return [locator]

    if isinstance(locator, PageElement):
        platform = get_platform_from_driver(driver)
        locs = locator.get_all(platform)
        if not locs:
            single = locator.get(platform)
            return [single]
        return locs

    raise TypeError("Unsupported locator type: expected StrategyValue or PageElement")

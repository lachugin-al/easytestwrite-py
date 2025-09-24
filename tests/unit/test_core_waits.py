from __future__ import annotations

import time
from types import MethodType
from typing import cast

import pytest
from selenium.webdriver.remote.webdriver import WebDriver

from mobiauto.core.locators import by_xpath
from mobiauto.core.waits import Waits


class FakeEl:
    def __init__(self, visible: bool = True) -> None:
        self._visible: bool = visible
        self.clicked: int = 0
        self.cleared: int = 0
        self.sent: list[str] = []

    def is_displayed(self) -> bool:
        return bool(self._visible)

    def click(self) -> None:
        self.clicked += 1

    def clear(self) -> None:
        self.cleared += 1

    def send_keys(self, s: str) -> None:
        self.sent.append(s)


class FakeDriver:
    def __init__(self) -> None:
        self.capabilities: dict[str, str] = {"platformName": "Android"}
        self._elements_map: dict[tuple[str, str], list[FakeEl]] = {}
        self._page_source: str = "a"
        self.exec_calls: list[tuple[str, dict]] = []
        self._size: dict[str, int] = {"width": 1000, "height": 2000}

    def find_elements(self, by: str, value: str) -> list[FakeEl]:
        return self._elements_map.get((by, value), [])

    def get_window_size(self) -> dict[str, int]:
        return self._size

    @property
    def page_source(self) -> str:
        return self._page_source

    def execute_script(self, name: str, args: dict) -> None:
        self.exec_calls.append((name, args))
        # эмуляция, проскроллили - страница изменилась
        self._page_source = self._page_source + "x"

    # helpers
    def set_elements(self, by: str, value: str, elems: list[FakeEl]) -> None:
        self._elements_map[(by, value)] = elems


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    # ускоряем тесты: time.sleep → сразу
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)


def test_waits_returns_nth_visible_element() -> None:
    drv = FakeDriver()
    loc = by_xpath("//a")
    # будет 2 элемента, оба видимы
    e1, e2 = FakeEl(True), FakeEl(True)
    drv.set_elements("xpath", "//a", [e1, e2])

    got = Waits.wait_for_elements(cast(WebDriver, drv), loc, index=2, timeout=0.5, polling_ms=50)
    assert got is e2


def test_waits_times_out_if_not_enough_elements() -> None:
    drv = FakeDriver()
    loc = by_xpath("//a")
    drv.set_elements("xpath", "//a", [FakeEl(True)])  # всего 1, просим второй

    with pytest.raises(Exception) as ei:
        Waits.wait_for_elements(cast(WebDriver, drv), loc, index=2, timeout=0.2, polling_ms=50)
    # сообщение об ошибке информативное
    assert "were not found within" in str(ei.value)


def test_waits_scrolls_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    drv = FakeDriver()
    loc = by_xpath("//list")
    # Сначала пусто…
    drv.set_elements("xpath", "//list", [])

    # …после первого скролла станет 1 видимый элемент
    def after_first_scroll_make_element_visible() -> None:
        if len(drv.exec_calls) >= 1:
            drv.set_elements("xpath", "//list", [FakeEl(True)])

    # подменим execute_script, чтобы имитировать появление элемента после скролла
    orig_exec = drv.execute_script

    def fake_exec(self: FakeDriver, name: str, args: dict) -> None:
        orig_exec(name, args)
        after_first_scroll_make_element_visible()

    monkeypatch.setattr(drv, "execute_script", MethodType(fake_exec, drv))

    got = Waits.wait_for_elements(
        cast(WebDriver, drv),
        loc,
        index=1,
        timeout=1.0,
        polling_ms=50,
        max_scrolls=2,
        scroll_percent=0.5,
    )
    assert isinstance(got, FakeEl)
    assert drv.exec_calls and drv.exec_calls[0][0] == "mobile: scrollGesture"


def test_wait_for_element_or_none_returns_none_on_absence() -> None:
    drv = FakeDriver()
    loc = by_xpath("//missing")
    drv.set_elements("xpath", "//missing", [])
    got = Waits.wait_for_element_or_none(cast(WebDriver, drv), loc, timeout=0.2, polling_ms=50)
    assert got is None

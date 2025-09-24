from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from mobiauto.core.controller import MobileController


class DummyEl:
    def __init__(self) -> None:
        self.clicked = False
        self.cleared = 0
        self.sent: list[str] = []

    def click(self) -> None:
        self.clicked = True

    def clear(self) -> None:
        self.cleared += 1

    def send_keys(self, text: str) -> None:
        self.sent.append(text)


class DummyDrv:
    def __init__(self, caps: dict[str, str] | None = None) -> None:
        self.capabilities = caps or {}
        self.back_called = 0
        self.exec_calls: list[tuple[str, dict[str, Any]]] = []

    def back(self) -> None:
        self.back_called += 1

    def execute_script(self, name: str, args: dict[str, Any]) -> None:
        self.exec_calls.append((name, args))


def test_controller_click_delegates_to_waits_and_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drv = DummyDrv()
    ctl = MobileController(cast(Any, drv))  # кастим заглушку к совместимому типу
    dummy = DummyEl()
    received: dict[str, Any] = {}

    # подменяем Waits.wait_for_elements → возвращаем наш элемент и проверяем параметры
    def fake_wait_for_elements(driver: Any, target: Any, **kw: Any) -> DummyEl:
        assert driver is drv
        received.update(kw)
        return dummy

    monkeypatch.setattr(
        "mobiauto.core.controller.Waits.wait_for_elements",
        fake_wait_for_elements,
    )

    sentinel_target = cast(Any, SimpleNamespace())
    ctl.click(sentinel_target, timeout=10, index=2, polling_ms=250)

    assert dummy.clicked is True
    # убеждаемся, что ключевые параметры докатились до Waits
    assert received["timeout"] == 10
    assert received["index"] == 2
    assert received["polling_ms"] == 250


def test_controller_type_clears_and_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    drv = DummyDrv()
    ctl = MobileController(cast(Any, drv))
    dummy = DummyEl()

    monkeypatch.setattr(
        "mobiauto.core.controller.Waits.wait_for_elements",
        lambda d, t, **kw: dummy,
    )

    ctl.type(cast(Any, SimpleNamespace()), "hello", clear=True)
    assert dummy.cleared == 1
    assert dummy.sent == ["hello"]


def test_controller_type_without_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    drv = DummyDrv()
    ctl = MobileController(cast(Any, drv))
    dummy = DummyEl()

    monkeypatch.setattr(
        "mobiauto.core.controller.Waits.wait_for_elements",
        lambda d, t, **kw: dummy,
    )

    ctl.type(cast(Any, SimpleNamespace()), "abc", clear=False)
    assert dummy.cleared == 0
    assert dummy.sent == ["abc"]

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from mobiauto.core.controller import MobileController


class DummyEl:
    """Simple stand-in for a WebElement that records interactions."""

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
    """Minimal driver stub that mimics the interface used by MobileController."""

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
    """
    Ensure MobileController.click delegates to Waits.wait_for_elements,
    forwards keyword arguments, and clicks the returned element.
    """
    drv = DummyDrv()
    ctl = MobileController(cast(Any, drv))  # cast stub to a compatible type
    dummy = DummyEl()
    received: dict[str, Any] = {}

    # Patch Waits.wait_for_elements → return our dummy element and capture kwargs
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
    # Verify key parameters reached Waits
    assert received["timeout"] == 10
    assert received["index"] == 2
    assert received["polling_ms"] == 250


def test_controller_type_clears_and_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    """type(clear=True) should clear the element first and then send text."""
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
    """type(clear=False) should not clear the element before sending text."""
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

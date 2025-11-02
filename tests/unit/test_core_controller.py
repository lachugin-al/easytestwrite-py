from __future__ import annotations

import json
import subprocess
from contextlib import AbstractContextManager
from types import SimpleNamespace, TracebackType
from typing import Any, Literal, cast

import pytest
from selenium.common.exceptions import (
    NoAlertPresentException,
    NoSuchElementException,
    TimeoutException,
)

from mobiauto.core.controller import MobileController
from mobiauto.core.locators import by_contains, by_exact_match


class TestMobileController:
    # -----------------------
    # Common stubs / utilities
    # -----------------------
    class DummyEl:
        """Generic element stub: clicks, clear/send_keys, text/attributes, rect."""

        def __init__(
            self, text: str = "", attrs: dict[str, Any] | None = None, el_id: str = "el-1"
        ) -> None:
            self._text = text
            self._attrs = attrs or {}
            self.id = el_id
            self.clicked = 0
            self.cleared = 0
            self.sent: list[str] = []
            self.rect: dict[str, int] = {"x": 10, "y": 20, "width": 100, "height": 80}

        @property
        def text(self) -> str:
            return self._text

        @text.setter
        def text(self, v: str) -> None:
            self._text = v

        def click(self) -> None:
            self.clicked += 1

        def clear(self) -> None:
            self.cleared += 1

        def send_keys(self, t: str) -> None:
            self.sent.append(t)

        def get_attribute(self, name: str) -> Any:
            return self._attrs.get(name)

    class DummyDrv:
        """Driver stub aggregating behavior used across all test blocks."""

        def __init__(self, caps: dict[str, Any] | None = None) -> None:
            self.capabilities = caps or {}
            self.back_called = 0
            self.exec_calls: list[tuple[str, dict[str, Any]]] = []
            self._page_source = "<xml/>"
            self._window_size = {"width": 1000, "height": 2000}
            self._switch_to = SimpleNamespace(active_element=TestMobileController.DummyEl(""))

        def back(self) -> None:
            self.back_called += 1

        def execute_script(self, name: str, args: dict[str, Any]) -> None:
            self.exec_calls.append((name, args))
            # You can force an exception in specific tests via the __raise__ marker in args
            if args.get("__raise__"):
                raise RuntimeError("forced error")

        @property
        def page_source(self) -> str:
            return self._page_source

        @page_source.setter
        def page_source(self, v: str) -> None:
            self._page_source = v

        def get_screenshot_as_png(self) -> bytes:  # used by ReportManager
            return b"PNG"

        def get_window_size(self) -> dict[str, int]:
            return dict(self._window_size)

        # Android-specific
        def open_notifications(self) -> None:
            pass

        def hide_keyboard(self) -> None:
            pass

        def press_keycode(self, keycode: int, metastate: int | None = None) -> None:
            self.exec_calls.append(("press_keycode", {"keycode": keycode, "metastate": metastate}))

        @property
        def switch_to(self) -> Any:
            return self._switch_to

    class StepSpy:
        """Allure step spy — accumulates step titles."""

        def __init__(self) -> None:
            self.titles: list[str] = []

        def __call__(self, title: str) -> AbstractContextManager[None]:
            self.titles.append(str(title))

            class _CM:
                def __enter__(self) -> None:
                    return None

                def __exit__(
                    self,
                    exc_type: type[BaseException] | None,
                    exc: BaseException | None,
                    tb: TracebackType | None,
                ) -> Literal[False]:
                    return False

            return cast(AbstractContextManager[None], _CM())

    class FakeReport:
        """Simple ReportManager substitute that counts success/failure attachments."""

        def __init__(self) -> None:
            self.success = 0
            self.fail = 0
            self.success_snaps = 0
            self.fail_artifacts = 0

        # Appears under different names in various blocks — support both counters
        def attach_screenshot_if_allowed(self, driver: Any, *, when: str) -> None:
            if when == "success":
                self.success += 1
                self.success_snaps += 1

        def attach_artifacts_on_failure(self, driver: Any) -> None:
            self.fail += 1
            self.fail_artifacts += 1

    class ElWithDom:
        def __init__(self) -> None:
            self._dom: dict[str, Any] = {"id": "login", "role": "button"}

        def get_dom_attribute(self, name: str) -> Any:
            return self._dom.get(name)

        def get_attribute(self, name: str) -> Any:  # fallback path
            return {"id": "wrong"}.get(name)

    class ElWithoutDom:
        def __init__(self) -> None:
            self._attrs: dict[str, Any] = {"content-desc": "greeting"}

        def get_attribute(self, name: str) -> Any:
            return self._attrs.get(name)

    class ElWithCss:
        def __init__(self) -> None:
            self._css: dict[str, Any] = {"color": "rgba(0, 0, 0, 1)", "font-weight": "700"}

        def value_of_css_property(self, name: str) -> Any:
            return self._css.get(name)

    class ElState:
        def __init__(self, en: bool, sel: bool, vis: bool) -> None:
            self._enabled = en
            self._selected = sel
            self._visible = vis
            self.sent: list[str] = []

        def is_enabled(self) -> bool:
            return self._enabled

        def is_selected(self) -> bool:
            return self._selected

        def is_displayed(self) -> bool:
            return self._visible

        def submit(self) -> None:
            raise NotImplementedError

        def send_keys(self, t: str) -> None:
            self.sent.append(t)

    class ElWithSubmit(ElState):
        def __init__(self) -> None:
            super().__init__(True, False, True)
            self.calls = 0

        def submit(self) -> None:
            self.calls += 1

    # -----------------------
    # Helper functions
    # -----------------------
    @staticmethod
    def _collect_actions_from_stdout(out: str) -> list[str]:
        actions: list[str] = []
        for line in out.strip().splitlines():
            try:
                data = json.loads(line)
                a = data.get("action")
                if a:
                    actions.append(str(a))
            except Exception:
                continue
        return actions

    # -----------------------
    # Basic click/type tests
    # -----------------------
    def test_controller_click_delegates_to_waits_and_clicks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        dummy = self.DummyEl()
        received: dict[str, Any] = {}

        def fake_wait_for_elements(
            driver: Any, target: Any, **kw: Any
        ) -> TestMobileController.DummyEl:
            assert driver is drv
            received.update(kw)
            return dummy

        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", fake_wait_for_elements
        )

        sentinel_target = cast(Any, SimpleNamespace())
        ctl.click(sentinel_target, timeout=10, index=2, polling_ms=250)

        assert dummy.clicked >= 1
        assert received["timeout"] == 10
        assert received["index"] == 2
        assert received["polling_ms"] == 250

    def test_controller_type_clears_and_sends(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        dummy = self.DummyEl()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: dummy
        )
        ctl.type(cast(Any, SimpleNamespace()), "hello", clear=True)
        assert dummy.cleared == 1
        assert dummy.sent == ["hello"]

    def test_controller_type_without_clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        dummy = self.DummyEl()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: dummy
        )
        ctl.type(cast(Any, SimpleNamespace()), "abc", clear=False)
        assert dummy.cleared == 0
        assert dummy.sent == ["abc"]

    # -----------------------
    # Getter tests: text/attr/number + allure.step
    # -----------------------
    def test_get_text_returns_and_logs_and_step(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, self.FakeReport()))
        dummy = self.DummyEl(text="some_text")

        spy = self.StepSpy()
        monkeypatch.setattr("mobiauto.core.controller.allure.step", spy)
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: dummy
        )

        res = ctl.get_text(by_exact_match("X"))
        assert res == "some_text"
        assert any("Get" in t or "Get text" in t for t in spy.titles)

        out = capsys.readouterr().out
        actions = self._collect_actions_from_stdout(out)
        assert "get_text" in actions

    def test_get_attribute_value_returns_and_logs(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, self.FakeReport()))
        dummy = self.DummyEl(text="irrelevant", attrs={"content-desc": "some_element"})

        spy = self.StepSpy()
        monkeypatch.setattr("mobiauto.core.controller.allure.step", spy)
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: dummy
        )

        val = ctl.get_attribute_value(by_exact_match("Y"), "content-desc")
        assert val == "some_element"
        assert any(
            "атрибута content-desc" in t or "attribute content-desc" in t for t in spy.titles
        )

        out = capsys.readouterr().out
        actions = self._collect_actions_from_stdout(out)
        assert "get_attribute_value" in actions

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("123", 123.0),
            ("123.45", 123.45),
            ("€ 45,90", 45.90),
            ("€1 234,56", 1234.56),
            ("USD 12,345.70", 12345.70),
            ("1.234,56 ₽", 1234.56),
            ("- 3’141’592,65", -3141592.65),
            ("≈2.000", 2000.0),
            ("2,000", 2000.0),
            ("0,99 kg", 0.99),
        ],
    )
    def test_get_number_parses_various_formats(
        self,
        monkeypatch: pytest.MonkeyPatch,
        text: str,
        expected: float,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, self.FakeReport()))
        dummy = self.DummyEl(text=text)

        spy = self.StepSpy()
        monkeypatch.setattr("mobiauto.core.controller.allure.step", spy)
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: dummy
        )

        val = ctl.get_number(by_exact_match("Price"))
        assert pytest.approx(val, rel=1e-9) == expected

        out = capsys.readouterr().out
        actions = self._collect_actions_from_stdout(out)
        assert "get_number" in actions

    def test_get_number_raises_value_error_and_attaches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drv = self.DummyDrv()
        rm = self.FakeReport()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, rm))
        dummy = self.DummyEl(text="abc")
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: dummy
        )
        with pytest.raises(ValueError) as e:
            ctl.get_number(by_exact_match("Z"))
        assert "abc" in str(e.value)
        assert rm.fail_artifacts >= 1

    def test_get_text_failure_attaches_artifacts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        rm = self.FakeReport()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, rm))

        def boom(*args: Any, **kwargs: Any) -> Any:
            raise NoSuchElementException("no element")

        monkeypatch.setattr("mobiauto.core.controller.Waits.wait_for_elements", boom)
        with pytest.raises(NoSuchElementException):
            ctl.get_text(by_exact_match("Missing"))
        assert rm.fail_artifacts >= 1

    # -----------------------
    # DOM / CSS / state / submit
    # -----------------------
    def test_get_dom_attribute_primary_and_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, self.FakeReport()))

        el1 = self.ElWithDom()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el1
        )
        assert ctl.get_dom_attribute(cast(Any, SimpleNamespace()), "id") == "login"
        assert ctl.get_dom_attribute(cast(Any, SimpleNamespace()), "role") == "button"

        el2 = self.ElWithoutDom()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el2
        )
        assert ctl.get_dom_attribute(cast(Any, SimpleNamespace()), "content-desc") == "greeting"

    def test_value_of_css_property_value_and_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, self.FakeReport()))

        el1 = self.ElWithCss()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el1
        )
        assert ctl.value_of_css_property(cast(Any, SimpleNamespace()), "color").startswith("rgba(")
        assert ctl.value_of_css_property(cast(Any, SimpleNamespace()), "font-weight") == "700"

        el2 = object()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el2
        )
        assert ctl.value_of_css_property(cast(Any, SimpleNamespace()), "any") == ""

    @pytest.mark.parametrize("en,sel,vis", [(True, False, True), (False, True, False)])
    def test_is_enabled_selected_displayed(
        self, monkeypatch: pytest.MonkeyPatch, en: bool, sel: bool, vis: bool
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, self.FakeReport()))
        el = self.ElState(en, sel, vis)
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el
        )
        assert ctl.is_enabled(cast(Any, SimpleNamespace())) is bool(en)
        assert ctl.is_selected(cast(Any, SimpleNamespace())) is bool(sel)
        assert ctl.is_displayed(cast(Any, SimpleNamespace())) is bool(vis)

    def test_submit_native_and_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, self.FakeReport()))

        el1 = self.ElWithSubmit()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el1
        )
        ctl.submit(cast(Any, SimpleNamespace()))
        assert el1.calls == 1

        el2 = self.ElState(True, False, True)
        if hasattr(el2, "submit"):
            delattr(el2.__class__, "submit")
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el2
        )
        ctl.submit(cast(Any, SimpleNamespace()))
        assert "\n" in el2.sent

    # -----------------------
    # click(text/contains) validation and delegation
    # -----------------------
    def test_click_with_text_builds_exact_and_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        dummy = self.DummyEl()
        captured: dict[str, Any] = {}

        def fake_wait_for_elements(
            driver: Any, target: Any, **kw: Any
        ) -> TestMobileController.DummyEl:
            captured["target"] = target
            captured.update(kw)
            return dummy

        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", fake_wait_for_elements
        )
        ctl.click(text="someone", timeout=7, index=1, polling_ms=111, max_scrolls=0)

        assert dummy.clicked >= 1
        assert captured["target"] == by_exact_match("someone")
        assert captured["timeout"] == 7
        assert captured["index"] == 1
        assert captured["polling_ms"] == 111

    def test_click_with_contains_builds_contains_and_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        dummy = self.DummyEl()
        captured: dict[str, Any] = {}

        def fake_wait_for_elements(
            driver: Any, target: Any, **kw: Any
        ) -> TestMobileController.DummyEl:
            captured["target"] = target
            return dummy

        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", fake_wait_for_elements
        )
        ctl.click(contains_text="some")
        assert dummy.clicked >= 1
        assert captured["target"] == by_contains("some")

    def test_click_text_params_validation(self) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        with pytest.raises(ValueError) as e1:
            ctl.click(text="A", contains_text="B")
        assert "Cannot use both 'text' and 'contains_text' at the same time" in str(e1.value)
        with pytest.raises(ValueError) as e2:
            ctl.click()
        assert "Provide 'target' or one of: 'text' | 'contains_text'" in str(e2.value)

    # -----------------------
    # Alerts
    # -----------------------
    def test_has_alert_true_and_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        report = self.FakeReport()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, report))

        monkeypatch.setattr(
            "mobiauto.core.controller.MobileController._wait_for_alert", lambda self, t=10: object()
        )
        assert ctl.has_alert(0.1) is True
        assert report.success >= 1

        def _raise_timeout(self: Any, t: float = 0.1) -> Any:
            raise TimeoutException("no alert")

        monkeypatch.setattr(
            "mobiauto.core.controller.MobileController._wait_for_alert", _raise_timeout
        )
        assert ctl.has_alert(0.01) is False

    def test_accept_and_dismiss_alert_with_race(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        report = self.FakeReport()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, report))

        class _A1:
            def accept(self) -> None:
                raise NoAlertPresentException("gone")

            def dismiss(self) -> None:
                raise NoAlertPresentException("gone")

        class _A2:
            def __init__(self) -> None:
                self.ok = 0

            def accept(self) -> None:
                self.ok += 1

            def dismiss(self) -> None:
                self.ok += 1

        seq = ["a1", "a2", "a1", "a2"]

        def _wf(self: Any, t: float) -> Any:
            tag = seq.pop(0)
            return _A1() if tag == "a1" else _A2()

        monkeypatch.setattr("mobiauto.core.controller.MobileController._wait_for_alert", _wf)
        ctl.accept_alert(0.01)
        ctl.dismiss_alert(0.01)
        assert report.success >= 2

    def test_get_alert_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        report = self.FakeReport()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, report))

        class _A:
            text = "Hello!"

        monkeypatch.setattr(
            "mobiauto.core.controller.MobileController._wait_for_alert", lambda self, t=10: _A()
        )
        assert ctl.get_alert_text(0.01) == "Hello!"
        assert report.success >= 1

    # -----------------------
    # Gestures/taps/swipes/scroll/drag/pinch
    # -----------------------
    def test_double_click_fallback_to_two_clicks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        el = self.DummyEl()

        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el
        )

        def _raise(name: str, args: dict[str, Any]) -> None:
            raise RuntimeError("no native double click")

        monkeypatch.setattr(drv, "execute_script", _raise)
        ctl.double_click(by_exact_match("X"))
        assert el.clicked == 2

    def test_long_click_and_tap_center(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        el = self.DummyEl()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el
        )

        ctl.long_click(by_exact_match("X"), duration_ms=1234)
        assert (
            "mobile: longClickGesture",
            {"elementId": el.id, "duration": 1234},
        ) in drv.exec_calls

        ctl.tap_center(by_exact_match("Y"))
        assert ("mobile: clickGesture", {"elementId": el.id}) in drv.exec_calls

    def test_tap_at_with_quick_stable_wait(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))

        class _WDW:
            def __init__(self, driver: Any, t: float) -> None:
                self.driver = driver
                self.t = t

            def until(self, cond: Any) -> bool:
                return bool(cond(self.driver))

        monkeypatch.setattr("selenium.webdriver.support.ui.WebDriverWait", _WDW)
        ctl.tap_at(111, 222, settle_for=0.01)
        assert ("mobile: clickGesture", {"x": 111, "y": 222}) in drv.exec_calls

    def test_tap_offset_uses_rect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        el = self.DummyEl()
        el.rect = {"x": 5, "y": 7}
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el
        )
        ctl.tap_offset(by_exact_match("Z"), dx=3, dy=4)
        assert ("mobile: clickGesture", {"x": 8, "y": 11}) in drv.exec_calls

    def test_swipe_element_and_screen_and_scroll_until_visible(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))

        el = self.DummyEl()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el
        )

        ctl.swipe_element(by_exact_match("A"), direction="down", percent=-0.5)
        name, args = drv.exec_calls[-1]
        percent = cast(float, args.get("percent"))
        assert name == "mobile: swipeGesture" and percent >= 0.01

        ctl.swipe_screen(direction="left", percent=2.0)
        name, args = drv.exec_calls[-1]
        percent2 = cast(float, args.get("percent"))
        assert name == "mobile: swipeGesture" and percent2 <= 1.0
        assert (
            args["left"] == 100
            and args["top"] == 200
            and args["width"] == 800
            and args["height"] == 1600
        )

        calls = {"n": 0}

        def _wait_or_none(
            driver: Any, target: Any, **kw: Any
        ) -> TestMobileController.DummyEl | None:
            calls["n"] += 1
            return None if calls["n"] < 3 else el

        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_element_or_none", _wait_or_none
        )
        ctl.scroll_until_visible(by_exact_match("B"), max_scrolls=5, direction="up")

        calls["n"] = 0
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_element_or_none", lambda d, t, **kw: None
        )
        with pytest.raises(RuntimeError):
            ctl.scroll_until_visible(by_exact_match("C"), max_scrolls=2)

    def test_drag_and_pinch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))

        src = self.DummyEl("src")
        dst = self.DummyEl("dst")
        dst.rect = {"x": 10, "y": 20, "width": 40, "height": 10}

        it = iter([src, dst])
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: next(it)
        )

        ctl.drag_and_drop(by_exact_match("SRC"), by_exact_match("DST"))
        name, args = drv.exec_calls[-1]
        assert name == "mobile: dragGesture" and args["endX"] == 30 and args["endY"] == 25

        el = self.DummyEl()
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el
        )
        ctl.pinch_open(by_exact_match("P"), percent=5)
        assert (
            drv.exec_calls[-1][0] == "mobile: pinchOpenGesture"
            and drv.exec_calls[-1][1]["percent"] == 1.0
        )
        ctl.pinch_close(by_exact_match("Q"), percent=0)
        assert (
            drv.exec_calls[-1][0] == "mobile: pinchCloseGesture"
            and drv.exec_calls[-1][1]["percent"] == 0.01
        )

    # -----------------------
    # System/native actions
    # -----------------------
    def test_hide_keyboard_and_open_notifications(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        report = self.FakeReport()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, report))

        ctl.open_notifications()
        assert report.success >= 1

        drv2 = object()
        ctl2 = MobileController(cast(Any, drv2), report_manager=cast(Any, report))
        with pytest.raises(RuntimeError):
            ctl2.open_notifications()

        def _raise() -> None:
            raise RuntimeError("cant hide")

        monkeypatch.setattr(drv, "hide_keyboard", _raise)
        with pytest.raises(RuntimeError):
            ctl.hide_keyboard()
        assert report.fail >= 1

    def test_android_press_keycode(self) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        ctl.android_press_keycode(66)
        assert ("press_keycode", {"keycode": 66, "metastate": None}) in drv.exec_calls

        ctl.android_press_keycode(4, metastate=1)
        assert ("press_keycode", {"keycode": 4, "metastate": 1}) in drv.exec_calls

        ctl2 = MobileController(cast(Any, object()))
        with pytest.raises(RuntimeError):
            ctl2.android_press_keycode(1)

    def test_perform_native_action_android_and_ios(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        report = self.FakeReport()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, report))

        monkeypatch.setattr(
            "mobiauto.core.controller.get_platform_from_driver", lambda d: "android"
        )
        calls: list[int] = []
        monkeypatch.setattr(
            MobileController, "android_press_keycode", lambda self, k: calls.append(k)
        )
        ctl.perform_native_action(android_key=4)
        assert calls == [4] and report.success >= 1

        with pytest.raises(ValueError):
            ctl.perform_native_action()

        monkeypatch.setattr("mobiauto.core.controller.get_platform_from_driver", lambda d: "ios")
        ctl.perform_native_action(ios_key="\n")
        assert ("mobile: type", {"text": "\n"}) in drv.exec_calls

        def _raise_es(name: str, args: dict[str, Any]) -> None:
            raise RuntimeError("cant type")

        drv.exec_calls.clear()
        monkeypatch.setattr(drv, "execute_script", _raise_es)
        ctl.perform_native_action(ios_key="X")
        assert "X" in drv.switch_to.active_element.sent

        drv.switch_to.active_element = SimpleNamespace(
            send_keys=lambda t: (_ for _ in ()).throw(RuntimeError("no send"))
        )
        with pytest.raises(RuntimeError):
            ctl.perform_native_action(ios_key="Y")

        monkeypatch.setattr("mobiauto.core.controller.get_platform_from_driver", lambda d: "web")
        with pytest.raises(RuntimeError):
            ctl.perform_native_action(android_key=1)

    # -----------------------
    # Getters: attribute + number (with text/errors)
    # -----------------------
    def test_get_attribute_value_and_number(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        report = self.FakeReport()
        ctl = MobileController(cast(Any, drv), report_manager=cast(Any, report))

        el = self.DummyEl()
        el.text = "Price: 1 234,50"
        el._attrs = {"content-desc": "hello", "a": "b"}
        monkeypatch.setattr(
            "mobiauto.core.controller.Waits.wait_for_elements", lambda d, t, **kw: el
        )

        v = ctl.get_attribute_value(by_exact_match("T"), "content-desc")
        assert v == "hello"

        assert abs(ctl.get_number(by_exact_match("N")) - 1234.5) < 1e-6

        el.text = "abc xyz"
        with pytest.raises(ValueError):
            ctl.get_number(by_exact_match("N"))

    # -----------------------
    # Deeplink
    # -----------------------
    @staticmethod
    def _make_settings(
        android_pkg: str | None = None, ios_bundle: str | None = None, ios_udid: str | None = None
    ) -> Any:
        ios = SimpleNamespace(bundle_id=ios_bundle or "", udid=ios_udid)
        android = SimpleNamespace(app_package=android_pkg)
        return SimpleNamespace(android=android, ios=ios)

    def test_open_deeplink_android(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))

        monkeypatch.setattr(
            "mobiauto.core.controller.get_platform_from_driver", lambda d: "android"
        )
        monkeypatch.setattr(
            "mobiauto.core.controller.load_settings",
            lambda: self._make_settings(android_pkg="com.example.app"),
        )

        ctl.open_deeplink("myapp://catalog?id=1")
        assert (
            "mobile: deepLink",
            {"url": "myapp://catalog?id=1", "package": "com.example.app"},
        ) in drv.exec_calls

        monkeypatch.setattr(
            "mobiauto.core.controller.load_settings", lambda: self._make_settings(android_pkg=None)
        )
        with pytest.raises(ValueError):
            ctl.open_deeplink("myapp://x")

    def test_open_deeplink_ios_bundle_and_fallback_simulator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drv = self.DummyDrv()
        ctl = MobileController(cast(Any, drv))
        monkeypatch.setattr("mobiauto.core.controller.get_platform_from_driver", lambda d: "ios")

        monkeypatch.setattr(
            "mobiauto.core.controller.load_settings",
            lambda: self._make_settings(ios_bundle="com.ex.app"),
        )
        ctl.open_deeplink("myapp://start?x=1")
        assert (
            "mobile: deepLink",
            {"url": "myapp://start?x=1", "bundleId": "com.ex.app"},
        ) in drv.exec_calls

        monkeypatch.setattr(
            "mobiauto.core.controller.load_settings", lambda: self._make_settings(ios_bundle="")
        )

        calls: list[list[str]] = []

        def _subproc_run(cmd: list[str], check: bool, capture_output: bool) -> None:
            calls.append(cmd)
            return None

        monkeypatch.setattr(subprocess, "run", _subproc_run)

        clicked: dict[str, Any] = {}
        monkeypatch.setattr(
            MobileController,
            "click",
            lambda self, target, **kw: clicked.update({"target": target, **kw}),
        )

        ctl.open_deeplink("scheme://open?param=test")

        assert calls and calls[-1][:3] == ["xcrun", "simctl", "openurl"]
        assert "target" in clicked and hasattr(clicked.get("target"), "ios")

        monkeypatch.setattr("mobiauto.core.controller.get_platform_from_driver", lambda d: "win")
        with pytest.raises(ValueError):
            ctl.open_deeplink("x://y")

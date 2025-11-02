from __future__ import annotations

from typing import Any

import pytest

from mobiauto.core.optional import (
    only_android,
    only_ios,
    optional,
    optional_android,
    optional_for,
    optional_ios,
)
from mobiauto.platform import Platform
from mobiauto.utils.logging import bind_context, clear_contextvars


class _Dummy:
    pass


def _set_platform_in_context(value: str) -> None:
    """
    Rebinds structlog context to the specified platform using the project's
    helper functions.

    This function emulates the environment usually prepared by the plugin:
    - clears previous context
    - sets the minimal device data expected by bind_context
    """
    try:
        clear_contextvars()  # The plugin also clears the context automatically after tests
    except Exception:
        pass

    s: Any = _Dummy()
    s.platform = value

    # Minimal device information expected by bind_context
    if value == "android":
        s.android = _Dummy()
        s.android.device_name = "AndroidTestDevice"
    elif value == "ios":
        s.ios = _Dummy()
        s.ios.device_name = "IOSTestDevice"

    bind_context(settings=s, test_name=f"unit_{value}")


def test_optional_for_executes_on_matching_platform_and_suppresses() -> None:
    """
    optional_for must execute steps on the matching platform
    and suppress errors when suppress=True.
    """
    _set_platform_in_context("android")

    executed: list[str] = []
    errors: list[BaseException] = []

    def step1() -> None:
        executed.append("1")

    def step2() -> None:
        raise ValueError("boom")

    def step3() -> None:
        executed.append("3")

    optional_for(Platform.ANDROID, step1, step2, step3, suppress=True, on_error=errors.append)

    # step1 and step3 executed, step2 error suppressed
    assert executed == ["1", "3"]
    assert len(errors) == 1 and isinstance(errors[0], ValueError)


def test_optional_for_skips_on_mismatch() -> None:
    """
    optional_for must skip execution when the platform does not match.
    """
    _set_platform_in_context("ios")

    called = {"flag": False}

    def step() -> None:
        called["flag"] = True

    optional_for("android", step)  # suppress=True by default
    assert called["flag"] is False


def test_optional_for_raises_when_suppress_false() -> None:
    """
    If suppress=False → the exception is not suppressed,
    and on_error must not be called.
    """
    _set_platform_in_context("android")

    def bad() -> None:
        raise RuntimeError("fail")

    on_error_called = {"count": 0}

    def on_error(_: BaseException) -> None:
        on_error_called["count"] += 1

    with pytest.raises(RuntimeError):
        optional_for("android", bad, suppress=False, on_error=on_error)

    # on_error must not be called because suppress=False
    assert on_error_called["count"] == 0


def test_optional_ios_and_android_wrappers() -> None:
    """
    optional_ios executes the step only on iOS.
    optional_android — only on Android.
    Other platforms → the step is ignored without error.
    """
    # iOS platform → optional_ios call must execute
    _set_platform_in_context("ios")
    counter = {"n": 0}

    def inc() -> None:
        counter["n"] += 1

    optional_ios(inc)
    assert counter["n"] == 1

    _set_platform_in_context("android")
    optional_ios(inc)
    assert counter["n"] == 1  # unchanged

    # Android platform → optional_android must execute
    optional_android(inc)
    assert counter["n"] == 2

    _set_platform_in_context("ios")
    optional_android(inc)
    assert counter["n"] == 2  # unchanged


def test_only_ios_and_only_android_do_not_suppress() -> None:
    """
    only_android and only_ios do not suppress errors:
    - if the platform matches → the step executes and the error is propagated
    - if not → the step is not executed (no error)
    """
    _set_platform_in_context("android")

    def bad_android() -> None:
        raise RuntimeError("android crash")

    with pytest.raises(RuntimeError):
        only_android(bad_android)

    _set_platform_in_context("ios")
    # Must not execute → no exception
    only_android(bad_android)

    # Same for only_ios
    def bad_ios() -> None:
        raise RuntimeError("ios crash")

    with pytest.raises(RuntimeError):
        only_ios(bad_ios)

    _set_platform_in_context("android")
    only_ios(bad_ios)  # not executed → no error


def test_optional_runs_regardless_and_suppresses_by_default() -> None:
    """
    optional executes steps regardless of platform,
    and suppresses errors by default (suppress=True).
    """
    _set_platform_in_context("android")

    executed: list[str] = []
    captured: list[BaseException] = []

    def ok() -> None:
        executed.append("ok")

    def bad() -> None:
        raise ValueError("x")

    def ok2() -> None:
        executed.append("ok2")

    optional(ok, bad, ok2, on_error=captured.append)  # suppress=True by default

    assert executed == ["ok", "ok2"]
    assert len(captured) == 1 and isinstance(captured[0], ValueError)


def test_optional_for_accepts_string_platform() -> None:
    """
    optional_for must accept the platform name as a string.
    """
    _set_platform_in_context("ios")
    marker = {"done": False}

    def step() -> None:
        marker["done"] = True

    optional_for("ios", step)
    assert marker["done"] is True

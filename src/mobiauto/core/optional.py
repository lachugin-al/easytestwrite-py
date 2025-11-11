from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from structlog.contextvars import get_contextvars

from ..platform import Platform
from ..utils.logging import get_logger

_logger = get_logger("mobiauto.core.optional")


def _context_platform() -> str | None:
    """
    Return the current platform from logging context (contextvars) to avoid repeated YAML loads.

    Platform is bound in the pytest plugin via bind_context(settings=...).
    Returned in lower case: "android" | "ios" | None if not set.
    """
    try:
        ctx = get_contextvars()
        p = ctx.get("platform")
        if isinstance(p, str):
            return p.lower()
        if p is not None:
            return str(p).lower()
    except Exception:
        # Never interfere with execution due to context issues
        pass
    return None


def _run_actions(
    actions: Iterable[Callable[[], None]],
    *,
    suppress: bool,
    on_error: Callable[[BaseException], None] | None,
    meta: Mapping[str, object] | None = None,
) -> None:
    """Execute a list of actions with optional exception suppression and logging."""
    for idx, action in enumerate(actions, start=1):
        try:
            action()
        except Exception as e:  # noqa: PERF203 - intentionally broad by design
            if not suppress:
                raise
            # Log suppressed error
            try:
                _logger.warning(
                    "Optional step error suppressed",
                    step=idx,
                    error=str(e),
                    **(meta or {}),
                    exc_info=True,
                )
            except Exception:
                # Logging must not break execution
                pass
            # User-defined error handler, if provided
            if on_error is not None:
                try:
                    on_error(e)
                except Exception:
                    # Do not let on_error handler break execution
                    try:
                        _logger.warning(
                            "Optional step on_error handler failed (suppressed)",
                            step=idx,
                            **(meta or {}),
                            exc_info=True,
                        )
                    except Exception:
                        pass


def optional_for(
    platform: str | Platform,
    *actions: Callable[[], None],
    suppress: bool = True,
    on_error: Callable[[BaseException], None] | None = None,
) -> None:
    """
    Execute a set of actions only if the current platform (from context) matches the target.

    Args:
    - platform: target platform ("android" | "ios" or Platform)
    - actions: actions without arguments
    - suppress: whether to suppress exceptions inside actions (default True)
    - on_error: optional handler for step exceptions, called only when suppress=True
    """
    target = platform.value if isinstance(platform, Platform) else str(platform).lower()
    current = (_context_platform() or "").lower()

    meta = {"target_platform": target, "current_platform": current}

    if current != target:
        _logger.debug("Skip optional_for: platform mismatch", **meta)
        return

    _run_actions(actions, suppress=suppress, on_error=on_error, meta=meta)


def optional(
    *actions: Callable[[], None],
    suppress: bool = True,
    on_error: Callable[[BaseException], None] | None = None,
) -> None:
    """Safely execute steps regardless of platform."""
    meta: Mapping[str, object] = {"current_platform": _context_platform()}
    _run_actions(actions, suppress=suppress, on_error=on_error, meta=meta)


def optional_ios(
    *actions: Callable[[], None],
    suppress: bool = True,
    on_error: Callable[[BaseException], None] | None = None,
) -> None:
    """Safely execute steps only on iOS (platform from context)."""
    optional_for(Platform.IOS, *actions, suppress=suppress, on_error=on_error)


def optional_android(
    *actions: Callable[[], None],
    suppress: bool = True,
    on_error: Callable[[BaseException], None] | None = None,
) -> None:
    """Safely execute steps only on Android (platform from context)."""
    optional_for(Platform.ANDROID, *actions, suppress=suppress, on_error=on_error)


def only_ios(action: Callable[[], None]) -> None:
    """Execute the action only on iOS. Exceptions are not suppressed."""
    optional_for(Platform.IOS, action, suppress=False)


def only_android(action: Callable[[], None]) -> None:
    """Execute the action only on Android. Exceptions are not suppressed."""
    optional_for(Platform.ANDROID, action, suppress=False)


__all__ = [
    "optional_for",
    "optional_ios",
    "optional_android",
    "optional",
    "only_ios",
    "only_android",
]

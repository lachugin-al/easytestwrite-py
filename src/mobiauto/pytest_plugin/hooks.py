from __future__ import annotations

from typing import Any


def pytest_runtest_makereport(item: Any, call: Any) -> None:
    """
    Pytest hook: called after each test phase (setup, call, teardown).

    Args:
        item (Any): The test item object (contains test function, nodeid, etc.).
        call (Any): The test call result, including outcome and exception info.

    This hook can be used to:
    - Attach logs, screenshots, or videos to reports on test failure.
    - Mark tests dynamically (e.g. flaky, xfail).
    - Collect additional metadata for custom reporting systems.

    Currently left empty - override as needed in the future.
    """
    pass

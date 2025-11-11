from __future__ import annotations

import os
from typing import Any

import allure

from mobiauto.utils.logging import current_test_log_path


def pytest_runtest_makereport(item: Any, call: Any) -> None:
    """
    Pytest hook: called after each test phase (setup, call, teardown).

    When the main test phase (call) fails, attaches the tail of the current test logs
    to the Allure report to speed up debugging.
    """
    try:
        # We are only interested in the actual test function phase
        if getattr(call, "when", None) != "call":
            return
        failed = getattr(call, "excinfo", None) is not None
        if not failed:
            return

        # Resolve log file path for the current test
        path = current_test_log_path(getattr(item, "name", None))
        content = ""
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    # Take last 200 lines to avoid overloading the report
                    content = "".join(lines[-200:])
        except Exception:
            content = ""

        if content:
            try:
                allure.attach(
                    content,
                    name="Recent logs",
                    attachment_type=allure.attachment_type.TEXT,
                )
            except Exception:
                # Do not interfere with test execution due to Allure issues
                pass
    except Exception:
        # Never fail due to errors inside the hook itself
        pass

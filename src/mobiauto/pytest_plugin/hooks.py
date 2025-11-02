from __future__ import annotations

import os
from typing import Any

import allure

from ..utils.logging import current_test_log_path


def pytest_runtest_makereport(item: Any, call: Any) -> None:
    """
    Pytest hook: called after each test phase (setup, call, teardown).

    When the main test phase (call) fails, attaches the tail of the current test’s
    log file to the Allure report to speed up failure analysis.
    """
    try:
        # We are only interested in the main test execution phase
        if getattr(call, "when", None) != "call":
            return
        failed = getattr(call, "excinfo", None) is not None
        if not failed:
            return

        # Determine the log file path for the current test
        path = current_test_log_path(getattr(item, "name", None))
        content = ""
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    # Take the last 200 lines to avoid overloading the report
                    content = "".join(lines[-200:])
        except Exception:
            content = ""

        if content:
            try:
                allure.attach(
                    content,
                    name="Recent Logs",
                    attachment_type=allure.attachment_type.TEXT,
                )
            except Exception:
                # Never interrupt test execution due to Allure attachment issues
                pass
    except Exception:
        # Never fail due to errors in the hook itself
        pass

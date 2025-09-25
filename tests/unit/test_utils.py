from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from mobiauto.utils.cli import run_cmd


def _stdout_to_str(stdout: str | bytes | bytearray | None | Any) -> str:
    """Normalize stdout to a string for assertions in tests."""
    if isinstance(stdout, bytes | bytearray):
        return stdout.decode(errors="ignore")
    return str(stdout or "")


def test_run_cmd_success() -> None:
    """run_cmd should succeed and capture stdout on a successful command."""
    # /bin/echo is reliably available
    out = run_cmd(["/bin/echo", "hello"], check=True)
    assert out.returncode == 0
    assert "hello" in _stdout_to_str(out.stdout)


def test_run_cmd_error_check_true_raises() -> None:
    """When check=True and the command fails, run_cmd must raise CalledProcessError."""
    with pytest.raises(subprocess.CalledProcessError):
        run_cmd([sys.executable, "-c", "import sys; sys.exit(1)"], check=True)


def test_run_cmd_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    """When spawn=True, run_cmd should return the Popen instance without waiting."""
    # Do not spawn a real process - patch Popen
    spawned: dict[str, Any] = {}

    class DummyP:
        def __init__(self, args: list[str], **kwargs: Any) -> None:
            spawned["args"] = args
            spawned["kwargs"] = kwargs

    monkeypatch.setattr("mobiauto.utils.cli.subprocess.Popen", DummyP)
    p = run_cmd(["sleep", "1"], spawn=True)
    assert isinstance(p, DummyP)
    assert spawned["args"] == ["sleep", "1"]

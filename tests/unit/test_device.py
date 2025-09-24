# tests/unit/test_device.py
from __future__ import annotations

from typing import Any

import pytest

from mobiauto.device.android_emulator import AndroidEmulatorManager
from mobiauto.device.ios_simulator import IOSSimulatorManager


def test_android_emulator_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    class R:
        def __init__(self, rc: int = 0, out: str = "") -> None:
            self.returncode: int = rc
            self.stdout: str = out
            self.stderr: str = ""

    def fake_run_cmd(args: list[str], **kw: Any) -> R:
        calls.append((tuple(args), kw))
        # emulate boot loop then ready
        if "getprop" in args:
            # перезапись stdout последним вызовом как "1"
            if len([c for c in calls if "getprop" in c[0]]) >= 2:
                return R(0, "1")
            return R(0, "0")
        return R(0, "")

    monkeypatch.setattr("mobiauto.device.android_emulator.run_cmd", fake_run_cmd)

    mgr = AndroidEmulatorManager(avd="Pixel_8", port=5554)
    mgr.start()
    mgr.wait_until_ready(timeout=3)
    mgr.stop()

    # проверяем, что были вызваны команды emulator/adb
    assert any("emulator" in c[0][0] for c in calls)
    assert any("adb" in c[0][0] and "getprop" in c[0] for c in calls)
    assert any("emu" in c[0] and "kill" in c[0] for c in calls)


def test_ios_simulator_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    class R:
        def __init__(self, rc: int = 0) -> None:
            self.returncode: int = rc
            self.stdout: str = ""
            self.stderr: str = ""

    def fake_run_cmd(args: list[str], **kw: Any) -> R:
        calls.append(tuple(args))
        # spawn system ready сразу
        if "launchctl" in args:
            return R(0)
        return R(0)

    monkeypatch.setattr("mobiauto.device.ios_simulator.run_cmd", fake_run_cmd)

    mgr = IOSSimulatorManager(udid="FAKE-UDID")
    mgr.start()
    mgr.wait_until_ready(timeout=2)
    mgr.stop()

    assert any(args[:3] == ("xcrun", "simctl", "boot") for args in calls)
    assert any(any("launchctl" in tok for tok in args) for args in calls)
    assert any(args[:3] == ("xcrun", "simctl", "shutdown") for args in calls)

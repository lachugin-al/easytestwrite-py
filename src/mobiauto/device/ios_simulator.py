from __future__ import annotations

import time

from ..utils.cli import run_cmd
from .base import EmulatorManager


class IOSSimulatorManager(EmulatorManager):
    def __init__(self, udid: str) -> None:
        self.udid = udid

    def start(self) -> None:
        run_cmd(["xcrun", "simctl", "boot", self.udid], check=False)

    def wait_until_ready(self, timeout: int = 120) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            out = run_cmd(
                ["xcrun", "simctl", "spawn", self.udid, "launchctl", "print", "system"],
                check=False,
            )
            if out.returncode == 0:
                return
            time.sleep(2)
        raise TimeoutError("iOS simulator did not become ready in time")

    def stop(self) -> None:
        run_cmd(["xcrun", "simctl", "shutdown", self.udid], check=False)

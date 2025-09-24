from __future__ import annotations

import subprocess
import time
from typing import Any, cast

from ..utils.cli import run_cmd
from .base import EmulatorManager


class AndroidEmulatorManager(EmulatorManager):
    def __init__(self, avd: str, port: int = 5554) -> None:
        self.avd, self.port = avd, port
        self.proc: subprocess.Popen[Any] | None = None

    def start(self) -> None:
        self.proc = cast(
            subprocess.Popen[Any],
            run_cmd(["emulator", "-avd", self.avd, "-port", str(self.port)], spawn=True),
        )

    def wait_until_ready(self, timeout: int = 180) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            out = run_cmd(
                [
                    "adb",
                    "-s",
                    f"emulator-{self.port}",
                    "shell",
                    "getprop",
                    "sys.boot_completed",
                ],
                check=False,
            )
            stdout = out.stdout
            if isinstance(stdout, bytes | bytearray):
                text = stdout.decode(errors="ignore")
            else:
                text = str(stdout or "")
            if text.strip() == "1":
                return
            time.sleep(2)
        raise TimeoutError("Android emulator did not become ready in time")

    def stop(self) -> None:
        run_cmd(["adb", "-s", f"emulator-{self.port}", "emu", "kill"], check=False)

from __future__ import annotations

import subprocess
import time
from typing import Any, cast

from ..utils.cli import run_cmd
from .base import EmulatorManager


class AndroidEmulatorManager(EmulatorManager):
    """
    Manages the lifecycle of an Android emulator process.

    Provides methods to start, wait for readiness, and stop the emulator.
    """

    def __init__(self, avd: str, port: int = 5554) -> None:
        """
        Initialize the AndroidEmulatorManager.

        Args:
            avd (str): Name of the AVD (Android Virtual Device) to launch.
            port (int): Port number for the emulator instance. Defaults to 5554.
        """
        self.avd, self.port = avd, port
        self.proc: subprocess.Popen[Any] | None = None

    def start(self) -> None:
        """
        Start the Android emulator process in a separate subprocess.

        Spawns the emulator with the given AVD name and port.
        """
        self.proc = cast(
            subprocess.Popen[Any],
            run_cmd(["emulator", "-avd", self.avd, "-port", str(self.port)], spawn=True),
        )

    def wait_until_ready(self, timeout: int = 180) -> None:
        """
        Wait until the emulator is fully booted and ready.

        Args:
            timeout (int): Maximum wait time in seconds. Defaults to 180 seconds.

        Raises:
            TimeoutError: If the emulator does not report `sys.boot_completed=1` within the timeout.
        """
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
        """
        Stop the running emulator instance.

        Sends `emu kill` command via ADB. Safe to call even if emulator is already stopped.
        """
        run_cmd(["adb", "-s", f"emulator-{self.port}", "emu", "kill"], check=False)

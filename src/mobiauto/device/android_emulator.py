from __future__ import annotations

import subprocess
import time
from typing import Any, cast

from ..utils.cli import run_cmd
from ..utils.logging import get_logger
from .base import EmulatorManager


class AndroidEmulatorManager(EmulatorManager):
    """
    Manages the lifecycle of the Android emulator process.

    Provides methods to start, wait for readiness, and stop the emulator.
    """

    def __init__(self, avd: str, port: int = 5554) -> None:
        """
        Initialize AndroidEmulatorManager.

        Args:
            avd (str): Name of the AVD (Android Virtual Device) to start.
            port (int): Port for the emulator instance. Defaults to 5554.
        """
        self.avd, self.port = avd, port
        self.proc: subprocess.Popen[Any] | None = None
        self._log = get_logger(__name__)

    def start(self) -> None:
        """
        Launch the Android emulator process in a separate subprocess.

        Spawns an emulator with the specified AVD name and port.
        """
        # Add extra flags for startup stability and CI
        cmd = [
            "emulator",
            "-avd",
            self.avd,
            "-port",
            str(self.port),
            "-no-boot-anim",
            "-no-snapshot-load",
            "-no-audio",
        ]
        # Headless mode for CI/headless environments
        try:
            import os

            if os.getenv("CI") == "true" or os.getenv("HEADLESS") == "1":
                cmd.append("-no-window")
        except Exception:
            # Safely ignore any issues with environment variables
            pass

        # Log emulator startup
        try:
            self._log.info(
                "Starting Android emulator",
                action="emulator_start",
                avd=self.avd,
                port=self.port,
                cmd=" ".join(cmd),
            )
        except Exception:
            pass

        self.proc = cast(
            subprocess.Popen[Any],
            run_cmd(cmd, spawn=True),
        )

        # Log successful process start
        try:
            self._log.info(
                "Emulator started",
                action="emulator_started",
                avd=self.avd,
                port=self.port,
                pid=getattr(self.proc, "pid", None),
            )
        except Exception:
            pass

    def wait_until_ready(self, timeout: int = 180) -> None:
        """
        Wait until the emulator fully boots and is ready.

        Args:
            timeout (int): Maximum wait time in seconds. Defaults to 180 seconds.

        Raises:
            TimeoutError: If the emulator does not report `sys.boot_completed=1` within the timeout.
        """
        # Log waiting for readiness
        try:
            self._log.info(
                "Waiting for emulator readiness",
                action="emulator_wait_ready",
                avd=self.avd,
                port=self.port,
                timeout=timeout,
            )
        except Exception:
            pass

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
                try:
                    self._log.info(
                        "Emulator is ready",
                        action="emulator_ready",
                        avd=self.avd,
                        port=self.port,
                    )
                except Exception:
                    pass
                return
            time.sleep(2)
        try:
            self._log.error(
                "Emulator did not become ready within the allotted time",
                action="emulator_ready_timeout",
                avd=self.avd,
                port=self.port,
                timeout=timeout,
            )
        except Exception:
            pass
        raise TimeoutError("Android emulator did not become ready within the allotted time")

    def stop(self) -> None:
        """
        Stop the running emulator instance.

        Sends the `emu kill` command via ADB. Safe to call even if the emulator is already stopped.
        """
        try:
            self._log.info(
                "Stopping Android emulator",
                action="emulator_stop",
                avd=self.avd,
                port=self.port,
            )
        except Exception:
            pass
        run_cmd(["adb", "-s", f"emulator-{self.port}", "emu", "kill"], check=False)

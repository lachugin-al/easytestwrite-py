from __future__ import annotations

import time

from ..utils.cli import run_cmd
from .base import EmulatorManager


class IOSSimulatorManager(EmulatorManager):
    """
    Manages the lifecycle of an iOS simulator instance.

    Provides methods to boot, wait for readiness, and shut down the simulator.
    """

    def __init__(self, udid: str) -> None:
        """
        Initialize the IOSSimulatorManager.

        Args:
            udid (str): The UDID of the iOS simulator to manage.
        """
        self.udid = udid

    def start(self) -> None:
        """
        Boot the iOS simulator.

        Uses `xcrun simctl boot` to start the simulator.
        """
        run_cmd(["xcrun", "simctl", "boot", self.udid], check=False)

    def wait_until_ready(self, timeout: int = 120) -> None:
        """
        Wait until the simulator is fully booted and ready.

        Args:
            timeout (int): Maximum wait time in seconds. Defaults to 120 seconds.

        Raises:
            TimeoutError: If the simulator does not respond within the timeout period.
        """
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
        """
        Shut down the iOS simulator.

        Uses `xcrun simctl shutdown` to gracefully stop the simulator.
        """
        run_cmd(["xcrun", "simctl", "shutdown", self.udid], check=False)

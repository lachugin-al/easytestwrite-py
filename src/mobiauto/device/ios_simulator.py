from __future__ import annotations

import json
import time
from typing import Any, cast

from ..utils.cli import run_cmd
from ..utils.logging import get_logger
from .base import EmulatorManager


class IOSSimulatorManager(EmulatorManager):
    """
    Manages the lifecycle of an iOS Simulator instance.

    Provides methods to boot, wait for readiness, and shut down the simulator.
    """

    def __init__(self, udid: str) -> None:
        """
        Initialize IOSSimulatorManager.

        Args:
            udid (str): UDID of the iOS simulator to manage.
        """
        self.udid = udid
        self._log = get_logger(__name__)

    def start(self) -> None:
        """
        Start the iOS simulator.

        Uses the `xcrun simctl boot` command to launch the simulator.
        """
        try:
            self._log.info(
                "Starting iOS simulator",
                action="simulator_start",
                udid=self.udid,
            )
        except Exception:
            pass
        run_cmd(["xcrun", "simctl", "boot", self.udid], check=False)
        try:
            self._log.info(
                "Simulator started",
                action="simulator_started",
                udid=self.udid,
            )
        except Exception:
            pass

    def wait_until_ready(self, timeout: int = 120) -> None:
        """
        Wait until the simulator is fully booted and ready for use.

        Args:
            timeout (int): Maximum wait time in seconds. Defaults to 120 seconds.

        Raises:
            TimeoutError: If the simulator does not respond within the given time.
        """
        try:
            self._log.info(
                "Waiting for simulator readiness",
                action="simulator_wait_ready",
                udid=self.udid,
                timeout=timeout,
            )
        except Exception:
            pass
        t0 = time.time()
        while time.time() - t0 < timeout:
            out = run_cmd(
                ["xcrun", "simctl", "spawn", self.udid, "launchctl", "print", "system"],
                check=False,
            )
            if out.returncode == 0:
                try:
                    self._log.info(
                        "Simulator is ready",
                        action="simulator_ready",
                        udid=self.udid,
                    )
                except Exception:
                    pass
                return
            time.sleep(2)
        try:
            self._log.error(
                "Simulator did not become ready within the allotted time",
                action="simulator_ready_timeout",
                udid=self.udid,
                timeout=timeout,
            )
        except Exception:
            pass
        raise TimeoutError("iOS simulator did not become ready within the allotted time")

    def stop(self) -> None:
        """
        Shut down the iOS simulator.

        Uses `xcrun simctl shutdown` to gracefully stop the simulator.
        """
        try:
            self._log.info(
                "Stopping iOS simulator",
                action="simulator_stop",
                udid=self.udid,
            )
        except Exception:
            pass
        run_cmd(["xcrun", "simctl", "shutdown", self.udid], check=False)


def find_simulator_udid_by_name(
    device_name: str, platform_version: str | None = None
) -> str | None:
    """
    Find the UDID of a simulator by its device name.

    If a platform version is specified, attempts to filter
    iOS runtimes matching that version. Returns the UDID
    of the first suitable simulator, or None if not found.
    """
    out = run_cmd(["xcrun", "simctl", "list", "--json"], check=False)
    if getattr(out, "returncode", 0) != 0:
        return None

    try:
        data = json.loads(getattr(out, "stdout", "") or "{}")
    except Exception:
        return None

    devices_raw = data.get("devices") or {}
    devices = cast(dict[str, list[dict[str, Any]]], devices_raw)

    # Normalize version: 18.5 -> 18-5
    normalized_ver = None
    if platform_version:
        normalized_ver = str(platform_version).replace(".", "-")

    candidates: list[dict[str, Any]] = []
    for runtime, devs in devices.items():
        if normalized_ver:
            # Skip runtimes that don't match the version if recognizable
            # (runtime key may look like "iOS 18.5" or "com.apple.CoreSimulator.SimRuntime.iOS-18-5")
            if ("iOS" not in runtime) or (
                normalized_ver not in runtime and str(platform_version) not in runtime
            ):
                continue
        for d in devs:
            if d.get("name") == device_name:
                candidates.append(d)

    if not candidates:
        # If not found with version filtering, try without it
        if normalized_ver:
            for devs in devices.values():
                for d in devs:
                    if d.get("name") == device_name:
                        candidates.append(d)

    if not candidates:
        return None

    # Prefer already booted simulators
    for d in candidates:
        if d.get("state") == "Booted":
            return d.get("udid")

    # Otherwise return the first available
    return candidates[0].get("udid")

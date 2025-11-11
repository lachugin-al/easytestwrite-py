from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
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
        Boot the iOS Simulator.

        Uses `xcrun simctl boot` to start the simulator.
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
                "Simulator boot command issued",
                action="simulator_started",
                udid=self.udid,
            )
        except Exception:
            pass

    def wait_until_ready(self, timeout: int = 120) -> None:
        """
        Wait until the simulator is fully booted and ready for use.

        Args:
            timeout (int): Maximum wait time in seconds. Defaults to 120.

        Raises:
            TimeoutError: If the simulator is not ready within the given timeout.
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
                "Simulator did not become ready within the timeout",
                action="simulator_ready_timeout",
                udid=self.udid,
                timeout=timeout,
            )
        except Exception:
            pass
        raise TimeoutError("iOS Simulator did not become ready within the timeout")

    def _run_netsetup(self, args: list[str], sudo: bool = False) -> subprocess.CompletedProcess:
        cmd = ["networksetup"] + args
        if sudo:
            cmd = ["sudo", "--"] + cmd
        self._log.debug("networksetup: %s", " ".join(cmd))
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=12)
        except Exception as e:
            self._log.warning("networksetup failed: %s", e)
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(e))

    def _list_macos_services(self) -> list[str]:
        try:
            out = subprocess.check_output(
                ["networksetup", "-listallnetworkservices"], text=True, stderr=subprocess.DEVNULL
            )
            lines = [
                line.strip()
                for line in out.splitlines()
                if line.strip() and not line.startswith("An asterisk")
            ]
            lines = [line.lstrip("* ").strip() for line in lines if line.strip()]
            return lines
        except Exception:
            return []

    def apply_proxy(self, host: str, port: int) -> None:
        """
        Configure HTTP/HTTPS proxy on macOS for all network services.

        This affects iOS Simulator as it uses the host network.
        Requires networksetup (macOS) and possibly sudo for some services.
        """
        services = self._list_macos_services()
        if not services:
            self._log.warning(
                "networksetup: no network services found - skipping proxy setup for simulator"
            )
            return
        self._log.info("macOS: setting proxy %s:%s for services: %s", host, port, services)
        sudo_ok = (
            subprocess.run(
                ["sudo", "-n", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        for svc in services:
            self._run_netsetup(["-setwebproxy", svc, host, str(port)], sudo=sudo_ok)
            self._run_netsetup(["-setsecurewebproxy", svc, host, str(port)], sudo=sudo_ok)
            # Set local bypass
            self._run_netsetup(
                ["-setproxybypassdomains", svc, "localhost", "127.0.0.1", "::1"],
                sudo=sudo_ok,
            )
            self._run_netsetup(["-setwebproxystate", svc, "on"], sudo=sudo_ok)
            self._run_netsetup(["-setsecurewebproxystate", svc, "on"], sudo=sudo_ok)

    def remove_proxy(self) -> None:
        services = self._list_macos_services()
        if not services:
            return
        sudo_ok = (
            subprocess.run(
                ["sudo", "-n", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        for svc in services:
            self._run_netsetup(["-setwebproxystate", svc, "off"], sudo=sudo_ok)
            self._run_netsetup(["-setsecurewebproxystate", svc, "off"], sudo=sudo_ok)

    def install_mitm_ca_if_available(self, mitm_log_dir: str | None) -> None:
        """
        Best-effort attempt to install mitmproxy CA into the macOS System keychain
        so that the simulator trusts MITM certificates.

        Requires sudo / user interaction and may be undesirable in CI.
        Often it's easier to prepare a simulator image with CA pre-installed.
        """
        candidates = []
        home = Path.home()
        candidates.append(home / ".mitmproxy" / "mitmproxy-ca-cert.pem")
        if mitm_log_dir:
            candidates.append(Path(mitm_log_dir) / "mitmproxy-ca-cert.pem")
        cert_path = next((p for p in candidates if p.exists()), None)
        if not cert_path:
            self._log.warning("mitmproxy CA not found for keychain installation.")
            return

        self._log.info("Installing mitm CA into System keychain (best-effort): %s", cert_path)
        try:
            # Add to System keychain (requires sudo)
            subprocess.run(
                [
                    "sudo",
                    "security",
                    "add-trusted-cert",
                    "-d",
                    "-r",
                    "trustRoot",
                    "-k",
                    "/Library/Keychains/System.keychain",
                    str(cert_path),
                ],
                check=False,
            )
            self._log.info(
                "CA installation attempt in System keychain completed "
                "(check permissions/result manually if needed)."
            )
        except Exception as e:
            self._log.exception("Error while installing CA into keychain: %s", e)

    def stop(self) -> None:
        """
        Shut down the iOS Simulator.

        Uses `xcrun simctl shutdown` for graceful termination.
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
    Find simulator UDID by device name.

    If platform_version is provided, attempts to filter iOS runtimes
    matching that version. Returns UDID of the first suitable simulator
    or None if not found.
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
            # Skip incompatible runtimes if we can parse them
            # (key may be "iOS 18.5" or "com.apple.CoreSimulator.SimRuntime.iOS-18-5")
            if ("iOS" not in runtime) or (
                normalized_ver not in runtime and str(platform_version) not in runtime
            ):
                continue
        for d in devs:
            if d.get("name") == device_name:
                candidates.append(d)

    if not candidates:
        # If nothing found with version filter, try without filtering by version
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

    # Otherwise, take the first available
    return candidates[0].get("udid")

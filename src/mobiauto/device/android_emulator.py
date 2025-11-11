from __future__ import annotations

import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from ..utils.cli import run_cmd
from ..utils.logging import get_logger
from .base import EmulatorManager


class AndroidEmulatorManager(EmulatorManager):
    """
    Manages the lifecycle of an Android emulator process.

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
        Start the Android emulator process in a separate subprocess.

        Spawns the emulator with the specified AVD name and port.
        """
        # Extra flags for stable startup and CI environments
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
            # Safely ignore any environment variable issues
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
                "Emulator process started",
                action="emulator_started",
                avd=self.avd,
                port=self.port,
                pid=getattr(self.proc, "pid", None),
            )
        except Exception:
            pass

    def wait_until_ready(self, timeout: int = 180) -> None:
        """
        Wait until the emulator is fully booted and ready.

        Args:
            timeout (int): Max wait time in seconds. Default is 180 seconds.

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
                "Emulator did not become ready within the timeout",
                action="emulator_ready_timeout",
                avd=self.avd,
                port=self.port,
                timeout=timeout,
            )
        except Exception:
            pass
        raise TimeoutError("Android emulator did not become ready within the timeout")

    def _adb(
        self, *args: str, capture_output: bool = False, timeout: int = 20
    ) -> subprocess.CompletedProcess:
        """
        Utility for executing adb commands for self.avd/udid.
        """
        base = ["adb"]
        udid = getattr(self, "udid", None)
        if udid is not None:
            base += ["-s", str(udid)]
        cmd = base + list(args)
        self._log.debug("ADB: %s", " ".join(map(shlex.quote, cmd)))
        try:
            if capture_output:
                return subprocess.run(
                    cmd, capture_output=True, text=True, check=False, timeout=timeout
                )
            else:
                return subprocess.run(cmd, check=False, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            self._log.warning("ADB timeout: %s", e)
            return subprocess.CompletedProcess(cmd, 124, stdout="", stderr="timeout")

    def apply_proxy(self, host: str, port: int) -> None:
        """
        Set system proxy in the emulator via `settings put global http_proxy`.

        Done as early as possible: includes waiting for ADB transport and several retries.
        For full HTTPS MITM support, CA installation is additionally required
        (see install_mitm_ca_if_available).
        """
        target = getattr(self, "udid", None) or f"emulator-{self.port}"

        # 1) Wait for early ADB transport (before full OS boot):
        #    appearance in `adb devices` + shell responsiveness.
        import subprocess
        import time

        start_ts = time.time()
        adb_timeout = 60  # seconds, to avoid hanging forever during early wait
        while time.time() - start_ts < adb_timeout:
            try:
                lst = subprocess.run(
                    ["adb", "devices"], capture_output=True, text=True, check=False, timeout=8
                )
                if lst.returncode == 0 and target in (lst.stdout or ""):
                    pong = self._adb("shell", "echo", "ping", capture_output=True)
                    if pong.returncode == 0 and "ping" in (pong.stdout or ""):
                        break  # transport is ready
            except Exception:
                pass
            time.sleep(1.0)
        else:
            # Transport never came up - log warning and exit gracefully.
            self._log.warning(
                "ADB transport is not ready - skipping early proxy application (target=%s)", target
            )
            return

        # 2) Try to set system proxy with several retries:
        cmd = ["shell", "settings", "put", "global", "http_proxy", f"{host}:{port}"]
        for attempt in range(1, 6):  # up to 5 attempts
            res = self._adb(*cmd, capture_output=True)
            if res.returncode == 0:
                self._log.info(
                    "http_proxy set in emulator: %s:%s (attempt=%d)", host, port, attempt
                )
                break
            else:
                self._log.warning(
                    "Failed to set http_proxy (attempt=%d/5): %s",
                    attempt,
                    res.stderr or res.stdout,
                )
                time.sleep(1.5)
        else:
            # All attempts failed - log and continue without failing tests.
            self._log.warning(
                "Failed to apply http_proxy after 5 attempts - continuing without it."
            )

        # 3) Short pause for SettingsProvider to propagate new value.
        time.sleep(0.5)

    def remove_proxy(self) -> None:
        """
        Remove system proxy in the emulator.
        """
        # Preferred way - delete; if unavailable, fall back to put ''.
        res = self._adb("shell", "settings", "delete", "global", "http_proxy", capture_output=True)
        if res.returncode != 0:
            # Fallback:
            self._adb("shell", "settings", "put", "global", "http_proxy", "''", capture_output=True)
        self._log.info("System http_proxy has been removed from emulator.")

    def install_mitm_ca_if_available(self, mitm_log_dir: str | None) -> None:
        """
        Attempt to install mitmproxy CA certificate into emulator system store (for HTTPS MITM).

        Requirements:
         - emulator must be running and rooted (adb root), system must be writable (remountable);
         - CA file is expected in one of the locations:
             ~/.mitmproxy/mitmproxy-ca-cert.pem
             or mitm_log_dir/mitmproxy-ca-cert.pem (if supervisor saved it there).
        This method is best-effort: on failure it logs and continues.
        """
        # Find cert
        candidates = []
        home = Path.home()
        candidates.append(home / ".mitmproxy" / "mitmproxy-ca-cert.pem")
        if mitm_log_dir:
            candidates.append(Path(mitm_log_dir) / "mitmproxy-ca-cert.pem")
        cert_path = next((p for p in candidates if p.exists()), None)
        if not cert_path:
            self._log.warning(
                "mitmproxy CA not found in %s - skipping CA installation.", candidates
            )
            return

        self._log.info(
            "Attempting to install mitm CA from %s into emulator system keystore", cert_path
        )
        # Try root, remount system and write certificate to /system/etc/security/cacerts/
        try:
            self._adb("root")
            # Wait for device to restart adb in root mode
            time.sleep(1.0)
            rem = self._adb("remount", capture_output=True)
            if rem.returncode != 0:
                self._log.warning("Failed to remount system: %s", rem.stderr or rem.stdout)
                # Without remount we cannot write to /system
                return
            # Build file name (Android expects hash-based file names; simplified as .der here)
            # For production: use `openssl x509 -hash` to generate proper name.
            with tempfile.TemporaryDirectory() as _td:
                tmp_dir = Path(_td)
                # Convert PEM to DER (Android expects DER)
                der = tmp_dir / "mitmproxy-ca-cert.der"
                # openssl required
                subprocess.run(
                    ["openssl", "x509", "-in", str(cert_path), "-outform", "der", "-out", str(der)],
                    check=False,
                )
                if not der.exists():
                    self._log.warning("Failed to convert cert to DER, skipping CA installation.")
                    return
                # Push to /system/etc/security/cacerts/
                target = "/system/etc/security/cacerts/mitmproxy-ca-cert.der"
                push = self._adb("push", str(der), target, capture_output=True)
                if push.returncode != 0:
                    self._log.warning("Failed to push CA: %s", push.stderr or push.stdout)
                    return
                # Set permissions
                self._adb("shell", "chmod", "644", target)
                self._adb("shell", "chown", "root:root", target)
                self._log.info(
                    "mitmproxy CA successfully installed to %s (emulator reboot required).",
                    target,
                )
                # Reboot emulator so system reloads CA store
                self._adb("reboot")
                self._log.info("Emulator rebooted to apply CA.")
        except Exception as e:
            self._log.exception("Error while attempting to install mitm CA into emulator: %s", e)
            return

    def stop(self) -> None:
        """
        Stop the running emulator instance.

        Sends `emu kill` via ADB. Safe to call even if emulator is already stopped.
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

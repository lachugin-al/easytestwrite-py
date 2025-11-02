from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import structlog

from ..config.models import Settings
from ..utils.cli import run_cmd


@dataclass(slots=True)
class _State:
    """Auxiliary structure for storing Appium process state."""

    proc: object | None = None  # subprocess.Popen | None
    started_by_us: bool = False  # Whether the server was started by this manager
    shutting_down: bool = False  # Shutdown flag
    monitor_thread: threading.Thread | None = None  # Monitoring thread


class AppiumServerManager:
    """
    Manages the lifecycle of a local Appium server process during test runs.

    Capabilities:
    - Automatically starts Appium before all tests (using host/port from Settings.appium.url)
    - Checks server readiness via the /status endpoint (and additional ones for compatibility)
    - Monitors server health and automatically restarts it on failure
    - Gracefully terminates the process after all tests (if it was started by this manager)
    """

    DEFAULT_POLL_INTERVAL_SEC = 3.0  # Interval between health checks (seconds)
    FAILURE_THRESHOLD = 3  # Consecutive failed checks before restart
    START_TIMEOUT_SEC = 30  # Max time to wait for server startup

    def __init__(self) -> None:
        self._log = structlog.get_logger(__name__)
        self._state = _State()
        self._lock = threading.RLock()
        self._target_url: str | None = None

    # ------------------------
    # Public API
    # ------------------------
    def ensure_started_and_monitored(self, settings: Settings) -> None:
        """
        Ensure that Appium is running and reachable at the URL from settings.
        If the server is not running, start a new process and begin monitoring.
        Re-entrant and safe to call multiple times.
        """
        with self._lock:
            url = str(settings.appium.url).rstrip("/")
            self._target_url = url

            # Check if a server is already up
            if self._is_healthy(url):
                self._log.info(
                    "Appium detected and running — enabling monitoring only",
                    url=url,
                    started_by_us=False,
                )
                self._state.started_by_us = False
                self._start_monitoring(url)
                return

            # Server is not available — try to start it
            host, port = self._parse_host_port(url)
            self._start_process(host, port)
            self._wait_until_healthy(url, timeout=self.START_TIMEOUT_SEC)
            self._start_monitoring(url)

    def shutdown(self) -> None:
        """
        Stop monitoring and gracefully terminate the Appium process
        if it was started by this manager.
        """
        with self._lock:
            self._state.shutting_down = True
            try:
                if self._state.monitor_thread and self._state.monitor_thread.is_alive():
                    # Interrupt monitor and wait for it to finish (cooperatively)
                    pass
            finally:
                pass

            if self._state.started_by_us:
                p = self._state.proc
                self._state.proc = None
                if p is not None and getattr(p, "poll", lambda: None)() is None:
                    # Process is active — terminate
                    self._log.info("Stopping Appium server (started by framework)")
                    try:
                        # Graceful termination
                        getattr(p, "terminate", lambda: None)()
                    except Exception:
                        pass

                    # Wait up to 5 seconds for it to exit
                    deadline = time.time() + 5
                    while time.time() < deadline and getattr(p, "poll", lambda: 0)() is None:
                        time.sleep(0.1)

                    if getattr(p, "poll", lambda: 0)() is None:
                        self._log.warning("Appium did not exit in time — forcing process kill")
                        try:
                            getattr(p, "kill", lambda: None)()
                        except Exception:
                            pass
            else:
                self._log.info(
                    "Appium was not started by the framework — leaving the process running",
                    started_by_us=False,
                )

            self._state.started_by_us = False
            self._state.shutting_down = False

    # ------------------------
    # Helper methods
    # ------------------------
    def _parse_host_port(self, base_url: str) -> tuple[str, int]:
        """Extract host and port from the Appium server URL."""
        pr = urlparse(base_url)
        host = pr.hostname or "127.0.0.1"
        port = pr.port or (443 if pr.scheme == "https" else 80)
        return host, port

    def _is_healthy(self, base_url: str) -> bool:
        """
        Check that the Appium server responds with a 2xx code on one of the known endpoints.
        Used to verify availability (/status, /sessions, and /).
        """
        base = base_url.rstrip("/")
        for ep in ("/status", "/sessions", "/"):
            url = base + ep
            try:
                req = Request(url, headers={"Accept": "application/json"})
                with urlopen(req, timeout=3) as resp:  # nosec - controlled URL
                    code = resp.getcode() or 0
                    if 200 <= code < 300:
                        # Attempt to parse JSON from /status for readiness logging
                        try:
                            raw = resp.read() or b""
                            if raw:
                                data = json.loads(raw.decode("utf-8", errors="ignore"))
                                ready = (
                                    isinstance(data, dict)
                                    and isinstance(data.get("value"), dict)
                                    and bool(data["value"].get("ready", True))
                                )
                                self._log.debug("Appium status check", endpoint=ep, ready=ready)
                        except Exception:
                            # JSON errors are non-critical — a 2xx is sufficient
                            pass
                        return True
            except URLError:
                continue
            except Exception:
                continue
        return False

    def _wait_until_healthy(self, url: str, *, timeout: int) -> None:
        """Wait until Appium becomes available within the given timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._is_healthy(url):
                self._log.info("Appium is ready for use", url=url)
                return
            time.sleep(0.5)

        # If the server didn't become available — stop the process to avoid a zombie
        if self._state.started_by_us and self._state.proc is not None:
            try:
                getattr(self._state.proc, "kill", lambda: None)()
            except Exception:
                pass
        raise RuntimeError(f"Failed to start Appium at {url} within {timeout} seconds")

    def _shell_prefix(self) -> list[str]:
        """Return the system shell command used to launch Appium (bash/cmd)."""
        if os.name == "nt":
            return ["cmd", "/c"]
        return ["bash", "-lc"]

    def _start_process(self, host: str, port: int) -> None:
        """
        Start the Appium process and store a reference to it.
        Creates the logs directory if it doesn't exist.
        """
        log_dir = os.path.join("artifacts")
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            pass
        log_file = os.path.join(log_dir, "appium-server.log")

        # Start the Appium process via `exec` —
        # this ensures terminate/kill signals are delivered directly to Appium
        # and the process exits cleanly when stopped.
        cmd = f"exec appium --address {host} --port {port} >> {log_file} 2>&1"
        args = self._shell_prefix() + [cmd]
        p = run_cmd(args, spawn=True)
        self._state.proc = p
        self._state.started_by_us = True

        pid = getattr(p, "pid", None)
        self._log.info("Starting Appium server", host=host, port=port, pid=pid, log=log_file)

    def _start_monitoring(self, url: str) -> None:
        """Start a background thread to monitor Appium health."""
        if self._state.monitor_thread and self._state.monitor_thread.is_alive():
            return

        t = threading.Thread(
            target=self._monitor_loop,
            args=(url,),
            name="appium-monitor",
            daemon=True,
        )
        self._state.monitor_thread = t
        t.start()

    def _monitor_loop(self, url: str) -> None:
        """
        Background Appium monitoring loop:
        - Checks process liveness and the /status endpoint.
        - Restarts the server after repeated failures.
        """
        failures = 0
        while not self._state.shutting_down:
            try:
                alive = False
                p = self._state.proc
                if p is not None:
                    alive = getattr(p, "poll", lambda: None)() is None

                healthy = self._is_healthy(url)
                if not alive or not healthy:
                    failures += 1
                else:
                    failures = 0

                if failures >= self.FAILURE_THRESHOLD and not self._state.shutting_down:
                    self._log.warning(
                        "Appium health issues detected — restarting",
                        failures=failures,
                    )
                    # Stop current process
                    if p is not None:
                        try:
                            getattr(p, "terminate", lambda: None)()
                        except Exception:
                            pass
                        deadline = time.time() + 3
                        while time.time() < deadline and getattr(p, "poll", lambda: 0)() is None:
                            time.sleep(0.1)
                        if getattr(p, "poll", lambda: 0)() is None:
                            try:
                                getattr(p, "kill", lambda: None)()
                            except Exception:
                                pass

                    # Restart Appium
                    host, port = self._parse_host_port(url)
                    try:
                        self._start_process(host, port)
                        self._wait_until_healthy(url, timeout=self.START_TIMEOUT_SEC)
                        failures = 0
                    except Exception as e:
                        self._log.error("Failed to restart Appium", error=str(e))
                time.sleep(self.DEFAULT_POLL_INTERVAL_SEC)
            except Exception as e:
                # Never exit the loop silently
                self._log.error("Error in monitoring loop", error=str(e))
                time.sleep(self.DEFAULT_POLL_INTERVAL_SEC)


# Global instance for convenient use in fixtures
manager = AppiumServerManager()

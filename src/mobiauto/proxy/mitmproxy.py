"""
Lightweight wrapper for launching/stopping mitmdump (mitmproxy).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from collections.abc import Iterable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import ClassVar

from ..utils.logging import get_logger
from ..utils.net import is_listening, owner_info

_log = get_logger(__name__)

# Filter out dangerous mitm arguments
BLOCKED_PREFIXES = ("--listen-", "--web-", "--mode")
BLOCKED_EXACT = {"--listen-host", "--listen-port", "-p", "--mode", "--web-host", "--web-port"}
BLOCKED_KEY_VALUES = {("set", "block_global=true"), ("set", "block_global=True")}


def _filter_mitm_args(args: Iterable[str]) -> list[str]:
    """
    Remove arguments that could change listening address/port or mode from the provided args.
    """
    args = list(args or [])
    res: list[str] = []
    i = 0
    while i < len(args):
        a = str(args[i]).strip()
        if a in BLOCKED_EXACT or any(a.startswith(p) for p in BLOCKED_PREFIXES):
            # skip the flag and its possible value
            if i + 1 < len(args) and not str(args[i + 1]).startswith("-"):
                i += 2
            else:
                i += 1
            continue
        if a == "--set" and i + 1 < len(args):
            kv = str(args[i + 1])
            key_lower = kv.split("=")[0].strip().lower()
            if (key_lower, kv.strip()) in BLOCKED_KEY_VALUES:
                i += 2
                continue
            res.extend([a, kv])
            i += 2
            continue
        res.append(a)
        i += 1
    return res


# Health endpoint (local)
class _HealthHandler(BaseHTTPRequestHandler):
    ctx: ClassVar[MitmProxyInstance | None] = None  # will be set from instance

    def log_message(self, fmt: str, *args: object) -> None:  # disable extra HTTP server logs
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        # ctx will be set by MitmProxyInstance when server starts
        ctx = self.ctx
        assert ctx is not None, "Health handler context is not initialized"
        payload = {
            "status": "ok" if is_listening(ctx.host, ctx.port) else "down",
            "host": ctx.host,
            "port": ctx.port,
            "pid": ctx.pid,
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# Wrapper class
class MitmProxyInstance:
    """
    Lightweight wrapper for running mitmdump:
    - start/stop process
    - local health endpoint
    - write PID and logs to log_dir
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9090,
        addons: list[str] | None = None,
        mitm_args: list[str] | None = None,
        mitm_bin: str = "mitmdump",
        health_port: int = 8079,
        log_dir: str | Path = "artifacts/proxy",
    ):
        self.host = host
        self.port = int(port)
        self.addons = addons or []
        self.mitm_args = mitm_args or []
        self.mitm_bin = mitm_bin
        self.health_port = int(health_port)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.pid: int | None = None
        self._proc: subprocess.Popen | None = None
        self._health_srv: HTTPServer | None = None
        self._health_thr: Thread | None = None

    @property
    def pid_file(self) -> Path:
        return self.log_dir / "mitmdump.pid"

    def _which(self, cmd: str) -> str | None:
        from shutil import which

        return which(cmd)

    def start(self, wait_for_listen: float = 5.0) -> None:
        """
        Start mitmdump. Raise RuntimeError if mitmdump is not found.
        If the port is occupied, raise RuntimeError with owner diagnostics.
        """
        if self._which(self.mitm_bin) is None:
            raise RuntimeError(f"{self.mitm_bin} not found in PATH. Please install mitmproxy.")

        if is_listening(self.host, self.port):
            raise RuntimeError(f"Port {self.host}:{self.port} is in use ({owner_info(self.port)}).")

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        mitm_log = self.log_dir / f"mitmproxy_{ts}.log"

        cmd = [self.mitm_bin, "--listen-host", self.host, "--listen-port", str(self.port)]
        for a in self.addons:
            cmd += ["-s", str(a)]
        cmd += _filter_mitm_args(self.mitm_args)

        fout = open(mitm_log, "a", encoding="utf-8")
        env = self._sanitize_env(os.environ.copy())

        # Start as a new session so we can terminate the whole group later
        self._proc = subprocess.Popen(
            cmd, stdout=fout, stderr=subprocess.STDOUT, start_new_session=True, env=env
        )
        self.pid = self._proc.pid
        self.pid_file.write_text(str(self.pid), encoding="utf-8")
        _log.info("mitmproxy started: %s", " ".join(map(str, cmd)))

        # wait until the port is listening (with timeout)
        t0 = time.time()
        while time.time() - t0 < wait_for_listen:
            if is_listening(self.host, self.port):
                break
            time.sleep(0.15)
        if not is_listening(self.host, self.port):
            raise RuntimeError(
                f"mitm did not start listening on {self.host}:{self.port}. See log: {mitm_log}"
            )
        _log.info("mitmproxy is listening %s:%d; PID=%s", self.host, self.port, self.pid)

        # Start local health endpoint on 127.0.0.1:health_port (if provided)
        if self.health_port and self.health_port > 0:
            _HealthHandler.ctx = self
            try:
                self._health_srv = HTTPServer(("127.0.0.1", self.health_port), _HealthHandler)
                self._health_thr = Thread(
                    target=self._health_srv.serve_forever, daemon=True, name="mitm-health"
                )
                self._health_thr.start()
            except OSError:
                # If health port is busy - skip silently
                self._health_srv = None
                self._health_thr = None

    def stop(self) -> None:
        """
        Stop mitmdump and the health endpoint.
        Attempt graceful SIGTERM for the whole pg, then SIGKILL if necessary.
        """
        # stop health
        try:
            if self._health_srv:
                self._health_srv.shutdown()
                self._health_srv.server_close()
        except Exception:
            pass
        if self._health_thr and self._health_thr.is_alive():
            self._health_thr.join(timeout=1.0)
        self._health_srv = None
        self._health_thr = None

        pid = self.pid or self._read_pid()
        if not pid:
            # nothing found
            return
        try:
            _log.info("Stopping mitmproxy; PID=%s", self.pid)
            os.killpg(pid, signal.SIGTERM)
            time.sleep(1.0)
            if is_listening(self.host, self.port):
                _log.warning("mitmproxy still holds the port - sending SIGKILL; PID=%s", pid)
                os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            # already dead
            pass
        except PermissionError:
            # if we don't have permission to killpg - try single process kill
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                if is_listening(self.host, self.port):
                    _log.warning("mitmproxy still holds the port - sending SIGKILL; PID=%s", pid)
                    os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

        # remove pid file (if present)
        try:
            self.pid_file.unlink(missing_ok=True)
        except Exception:
            pass

    def _read_pid(self) -> int | None:
        try:
            return int(self.pid_file.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    @staticmethod
    def _sanitize_env(env: dict[str, str]) -> dict[str, str]:
        """
        Remove environment variables that obviously look like secrets.
        This prevents leaking secrets into the child process.
        """
        blocked = (
            "KEY",
            "TOKEN",
            "SECRET",
            "PASSWORD",
            "AWS",
            "AZURE",
            "GCP",
            "GOOGLE_APPLICATION_CREDENTIALS",
        )
        return {k: v for k, v in env.items() if not any(b in k.upper() for b in blocked)}

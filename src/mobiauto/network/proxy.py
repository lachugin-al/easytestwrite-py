from __future__ import annotations

import os
from subprocess import Popen

from ..config.models import Settings


class MitmProxyProcess:
    """
    Wrapper for managing a local mitmproxy process (mitmdump).

    Starts mitmdump with optional HAR file saving and allows graceful shutdown.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the MitmProxyProcess with given settings.

        Args:
            settings (Settings): Application configuration containing proxy settings.
        """
        self.settings = settings
        self.proc: Popen | None = None

    def start(self) -> None:
        """
        Start the mitmdump process if proxy is enabled in settings.

        Creates directories for HAR files if required and starts mitmdump
        with `block_global=false` to allow external devices to connect.
        """
        if not self.settings.proxy.enabled:
            return

        args = [
            "mitmdump",
            "--set",
            "block_global=false",
        ]

        if self.settings.proxy.save_har:
            os.makedirs(os.path.dirname(self.settings.proxy.har_path), exist_ok=True)
            args += ["-w", self.settings.proxy.har_path]

        self.proc = Popen(args)

    def stop(self) -> None:
        """
        Stop the mitmdump process if it is still running.
        """
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

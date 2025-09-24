from __future__ import annotations

import os
from subprocess import Popen

from ..config.models import Settings


class MitmProxyProcess:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.proc: Popen | None = None

    def start(self) -> None:
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
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

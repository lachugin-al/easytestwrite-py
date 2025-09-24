from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

from ..utils.cli import run_cmd


class VideoRecorder:
    def __init__(self, out_path: str) -> None:
        self.out = Path(out_path)
        self.proc: subprocess.Popen[Any] | None = None

    def start_android(self, serial: str = "emulator-5554") -> None:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.proc = cast(
            subprocess.Popen[Any],
            run_cmd(
                ["adb", "-s", serial, "shell", "screenrecord", "/sdcard/test.mp4"],
                spawn=True,
            ),
        )

    def stop_android(self, serial: str = "emulator-5554") -> None:
        # Если процесс ещё есть - останавливаем
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()

        # Пытаемся скачать файл с устройства
        run_cmd(
            ["adb", "-s", serial, "pull", "/sdcard/test.mp4", str(self.out)],
            check=False,
        )

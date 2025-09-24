from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

from ..utils.cli import run_cmd


class VideoRecorder:
    """
    Utility class for recording and saving Android emulator/device screen video.

    Uses `adb shell screenrecord` to start recording and retrieves the file after stopping.
    """

    def __init__(self, out_path: str) -> None:
        """
        Initialize the VideoRecorder.

        Args:
            out_path (str): Path where the recorded video will be saved.
        """
        self.out = Path(out_path)
        self.proc: subprocess.Popen[Any] | None = None

    def start_android(self, serial: str = "emulator-5554") -> None:
        """
        Start recording the screen on an Android emulator/device.

        Args:
            serial (str): Device serial (default: "emulator-5554").
        """
        # Ensure output directory exists before starting recording
        self.out.parent.mkdir(parents=True, exist_ok=True)

        self.proc = cast(
            subprocess.Popen[Any],
            run_cmd(
                ["adb", "-s", serial, "shell", "screenrecord", "/sdcard/test.mp4"],
                spawn=True,
            ),
        )

    def stop_android(self, serial: str = "emulator-5554") -> None:
        """
        Stop recording and pull the recorded video from the device.

        Args:
            serial (str): Device serial (default: "emulator-5554").
        """
        # If the recording process is still running, terminate it
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()

        # Attempt to pull the recorded file from the device to local storage
        run_cmd(
            ["adb", "-s", serial, "pull", "/sdcard/test.mp4", str(self.out)],
            check=False,
        )

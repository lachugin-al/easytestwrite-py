from __future__ import annotations

import subprocess
from collections.abc import Sequence


class Completed:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.returncode = proc.returncode
        self.stdout = (
            proc.stdout.decode()
            if isinstance(proc.stdout, bytes | bytearray)
            else (proc.stdout or "")
        )
        self.stderr = (
            proc.stderr.decode()
            if isinstance(proc.stderr, bytes | bytearray)
            else (proc.stderr or "")
        )


def run_cmd(
    args: Sequence[str],
    *,
    check: bool = True,
    spawn: bool = False,
    timeout: int | None = None,
) -> Completed | subprocess.Popen:
    if spawn:
        return subprocess.Popen(args)
    proc = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args, proc.stdout, proc.stderr)
    return Completed(proc)

from __future__ import annotations

import subprocess
from collections.abc import Sequence


class Completed:
    """
    Wrapper for subprocess.CompletedProcess that decodes stdout and stderr to strings.
    """

    def __init__(self, proc: subprocess.CompletedProcess):
        """
        Initialize a Completed result from a subprocess.CompletedProcess.

        Args:
            proc (subprocess.CompletedProcess): Completed process instance.
        """
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
    """
    Run a command as a subprocess.

    Args:
        args (Sequence[str]): Command and arguments to execute.
        check (bool): If True, raise CalledProcessError if the command fails.
        spawn (bool): If True, start the process without waiting for completion and return Popen.
        timeout (int | None): Optional timeout in seconds for the process to complete.

    Returns:
        Completed | subprocess.Popen:
            - Completed: Result object with stdout/stderr as strings if `spawn=False`.
            - subprocess.Popen: Process object if `spawn=True`.

    Raises:
        subprocess.CalledProcessError: If `check=True` and process exits with a non-zero return code.
    """
    if spawn:
        return subprocess.Popen(args)

    proc = subprocess.run(args, capture_output=True, timeout=timeout, check=False)

    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args, proc.stdout, proc.stderr)

    return Completed(proc)

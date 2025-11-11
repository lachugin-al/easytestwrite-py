from __future__ import annotations

import subprocess
from collections.abc import Sequence


class Completed:
    """
    Wrapper around subprocess.CompletedProcess that decodes stdout and stderr into strings.
    """

    def __init__(self, proc: subprocess.CompletedProcess):
        """
        Initialize a Completed object based on subprocess.CompletedProcess.

        Args:
            proc (subprocess.CompletedProcess): The completed process instance.
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
    Execute a command as a subprocess.

    Args:
        args (Sequence[str]): Command and arguments to execute.
        check (bool): If True, raise CalledProcessError on failure.
        spawn (bool): If True, start the process asynchronously and return a Popen object.
        timeout (int | None): Optional timeout in seconds for waiting for completion.

    Returns:
        Completed | subprocess.Popen:
            - Completed: Result with stdout/stderr as strings (if `spawn=False`)
            - subprocess.Popen: Process object (if `spawn=True`)

    Raises:
        subprocess.CalledProcessError: If `check=True` and process exits with a nonzero code.
    """
    if spawn:
        return subprocess.Popen(args)

    proc = subprocess.run(args, capture_output=True, timeout=timeout, check=False)

    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args, proc.stdout, proc.stderr)

    return Completed(proc)

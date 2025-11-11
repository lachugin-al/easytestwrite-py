from __future__ import annotations

import socket
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import psutil as psutil
else:
    try:
        import psutil  # optional dependency
    except Exception:
        psutil = None  # type: ignore[assignment]


def is_listening(host: str, port: int, timeout: float = 0.6) -> bool:
    """
    Check that (host, port) is accepting connections (port is open and listening).

    Args:
        host: Address to check, for example "127.0.0.1".
        port: Port to check.
        timeout: Connection timeout in seconds.

    Returns:
        True if a TCP connection can be established (port is listening), otherwise False.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def get_free_port() -> int:
    """
    Find a free TCP port on localhost.

    Opens a temporary socket bound to ("127.0.0.1", 0) to obtain an available port.
    Note: a race condition is possible between returning the value and actual use.

    Returns:
        int: A free port number.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        addr_port = cast(tuple[str, int], s.getsockname())
        return addr_port[1]


def owner_info(port: int) -> str:
    """
    Return information about the process that is listening on the given TCP port.

    Behavior:
      - If psutil is available, iterate over `psutil.net_connections(kind="inet")`
        and look for an entry with laddr.port == port and status LISTEN.
      - If found, try to get the Process object by PID and return a string:
          "PID <pid>, name '<proc.name()>', user '<proc.username()>'"
      - On access errors or if the process has already exited, return "PID <pid>".
      - If psutil is not available or nothing is found, return "unknown".
    """
    if psutil:
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN:
                try:
                    p = psutil.Process(c.pid or 0)
                    return f"PID {p.pid}, name '{p.name()}', user '{p.username()}'"
                except Exception:
                    return f"PID {c.pid}"
    return "unknown"

from __future__ import annotations

from abc import ABC, abstractmethod


class EmulatorManager(ABC):
    """
    Abstract base class for emulator managers.

    Defines the required interface to start, stop,
    and wait for readiness for any emulator implementation.
    """

    @abstractmethod
    def start(self) -> None:
        """
        Start the emulator process.

        Implementations must spawn or initialize the emulator
        in a way that allows further interaction with it.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Stop the running emulator instance.

        Implementations must gracefully terminate the emulator process.
        """
        ...

    @abstractmethod
    def wait_until_ready(self, timeout: int = 120) -> None:
        """
        Wait until the emulator is fully ready for use.

        Args:
            timeout (int): Maximum wait time in seconds (default: 120).
        """
        ...

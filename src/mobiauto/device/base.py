from __future__ import annotations

from abc import ABC, abstractmethod


class EmulatorManager(ABC):
    """
    Abstract base class for emulator managers.

    Defines the required interface for starting, stopping,
    and waiting for readiness of any emulator implementation.
    """

    @abstractmethod
    def start(self) -> None:
        """
        Start the emulator process.

        Implementations should spawn or initialize the emulator
        in a way that allows further interaction.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Stop the running emulator instance.

        Implementations should gracefully terminate the emulator process.
        """
        ...

    @abstractmethod
    def wait_until_ready(self, timeout: int = 120) -> None:
        """
        Wait until the emulator is fully ready for use.

        Args:
            timeout (int): Maximum wait time in seconds (defaults to 120).
        """
        ...

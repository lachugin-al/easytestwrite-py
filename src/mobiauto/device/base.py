from __future__ import annotations

from abc import ABC, abstractmethod


class EmulatorManager(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def wait_until_ready(self, timeout: int = 120) -> None: ...

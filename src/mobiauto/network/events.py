from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Event(BaseModel):
    type: str
    ts: datetime
    payload: dict[str, Any] = {}


class EventStore:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def add(self, evt: Event) -> None:
        self._events.append(evt)

    def find(self, type_: str) -> list[Event]:
        return [e for e in self._events if e.type == type_]

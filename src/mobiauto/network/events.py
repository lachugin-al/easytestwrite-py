from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Event(BaseModel):
    """
    Represents a single event with a type, timestamp, and optional payload.
    """

    type: str  # Event type (e.g. "test_started", "screenshot_taken")
    ts: datetime  # Timestamp of the event
    payload: dict[str, Any] = {}  # Arbitrary data associated with the event


class EventStore:
    """
    Simple in-memory event store for collecting and querying events.

    Can be used to track runtime events, such as test steps, failures,
    network requests, or any other domain-specific actions.
    """

    def __init__(self) -> None:
        """Initialize an empty event store."""
        self._events: list[Event] = []

    def add(self, evt: Event) -> None:
        """
        Add a new event to the store.

        Args:
            evt (Event): Event instance to store.
        """
        self._events.append(evt)

    def find(self, type_: str) -> list[Event]:
        """
        Retrieve all events of a given type.

        Args:
            type_ (str): Event type to search for.

        Returns:
            list[Event]: A list of matching events.
        """
        return [e for e in self._events if e.type == type_]

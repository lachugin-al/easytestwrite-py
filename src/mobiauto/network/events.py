from __future__ import annotations

import json
import threading

from pydantic import AliasChoices, BaseModel, Field

from mobiauto.utils.logging import get_logger

logger = get_logger(__name__)


class EventData(BaseModel):
    """
    Detailed HTTP request information associated with an Event.

    Attributes:
      - uri: Request path without domain (e.g. "/event").
      - remoteAddress: Client address that sent the request (e.g. "192.168.1.2:53427").
      - headers: HTTP request headers.
      - query: Query string, if present.
      - body: Request body as a JSON string.
    """

    uri: str
    remote_address: str = Field(
        validation_alias=AliasChoices("remoteAddress", "remote_address"),
        serialization_alias="remoteAddress",
    )
    headers: dict[str, list[str]]
    query: str | None = None
    body: str


class Event(BaseModel):
    """
    Analytics or technical event captured during testing.

    Attributes:
      - event_time: Event timestamp (e.g. Instant.now().toString()).
      - event_num: Unique event number within a single test session.
      - name: Event name (e.g. HTTP method or logical event name).
      - data: Optional EventData with request payload and metadata.
    """

    event_time: str
    event_num: int
    name: str
    data: EventData | None = None


class EventStore:
    """
    Thread-safe storage for events captured during testing.

    Responsibilities:
      - Store all received Event instances.
      - Track which events have already been "consumed" in checks.
      - Provide convenient read APIs for verifiers and tests.
    """

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._matched_events: set[int] = set()
        self._lock = threading.RLock()

    def add_events(self, new_events: list[Event]) -> None:
        """
        Add a list of new events, ignoring duplicates by event_num.
        """
        with self._lock:
            for event in new_events:
                if not self._event_exists(event.event_num):
                    self._events.append(event)

                    payload = None
                    if event.data:
                        try:
                            payload = event.data.model_dump(by_alias=True)
                            body = payload.get("body")
                            # If body is a JSON string, try to show it in logs as an object
                            if isinstance(body, str):
                                try:
                                    payload["body"] = json.loads(body)
                                except Exception:
                                    # Leave as-is if it can't be parsed
                                    pass
                        except Exception:
                            payload = None

                    logger.info(
                        "event_saved",
                        name=event.name,
                        event_num=event.event_num,
                        event_time=event.event_time,
                        data=payload,
                    )
                else:
                    logger.debug(
                        "event_ignored_duplicate",
                        event_num=event.event_num,
                        name=event.name,
                    )

    def _event_exists(self, event_number: int) -> bool:
        return any(e.event_num == event_number for e in self._events)

    def mark_event_as_matched(self, event_num: int) -> None:
        with self._lock:
            self._matched_events.add(event_num)
        logger.info("event_marked_matched", event_num=event_num)

    def is_event_already_matched(self, event_num: int) -> bool:
        with self._lock:
            matched = event_num in self._matched_events
        logger.debug("event_is_matched_check", event_num=event_num, matched=matched)
        return matched

    def get_index_events(self, index: int) -> list[Event]:
        with self._lock:
            if index < len(self._events):
                result = [
                    e for e in self._events[index:] if e.event_num not in self._matched_events
                ]
                total = len(self._events)
            else:
                result = []
                total = len(self._events)
        logger.info("events_from_index", index=index, total=total, returned=len(result))
        return result

    def get_events(self) -> list[Event]:
        with self._lock:
            snapshot = list(self._events)
        logger.debug("events_get_all", count=len(snapshot))
        return snapshot

    def get_last_event(self) -> Event | None:
        with self._lock:
            evt = self._events[-1] if self._events else None
        if evt is not None:
            logger.debug("event_get_last", event_num=evt.event_num, name=evt.name)
        else:
            logger.debug("event_get_last_none")
        return evt

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._matched_events.clear()
        logger.info("events_cleared")

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from difflib import unified_diff
from types import TracebackType
from typing import Any, Literal, Protocol, assert_never

import allure

from ..core.locators import PageElement, by_label, by_text
from ..core.waits import (
    DEFAULT_SCROLL_CAPACITY,
    DEFAULT_SCROLL_COUNT,
    DEFAULT_SCROLL_DIRECTION,
    DEFAULT_TIMEOUT_EVENT_EXPECTATION,
)
from ..reporting.manager import (  # noqa: F401  # reserved for future (artifacts/policies)
    ReportManager,
)
from ..utils.logging import get_logger
from .events import Event, EventData, EventStore

logger = get_logger(__name__)


# ---------- JSON matching utilities (JsonMatchers-style) ----------


def match_json_element(event_element: Any, search_element: Any) -> bool:
    """
    Recursively match two JSON-like structures with flexible rules.

    Supported:

    - Primitives with patterns:
      - "*"       - any value matches
      - ""        - only empty string matches
      - "~value"  - substring match against actual string
    - Objects:
      - every key/value from the expected object must match in the actual object
    - Arrays:
      - every element from the expected array must be found in the actual array (order-agnostic)
    - Strings containing serialized JSON:
      - we try to parse and match recursively
    """
    # Primitive vs primitive
    if isinstance(event_element, str | int | float | bool) or event_element is None:
        if isinstance(search_element, str | int | float | bool) or search_element is None:
            if isinstance(search_element, str):
                if search_element == "*":
                    return True
                if search_element == "":
                    return isinstance(event_element, str) and event_element == ""
                if search_element.startswith("~"):
                    needle = search_element[1:]
                    return isinstance(event_element, str) and needle in event_element
                # Exact match (stringified)
                try:
                    return str(event_element) == search_element
                except Exception:
                    return False
            # Non-string expected -> direct equality
            return event_element == search_element

        # Actual is primitive string that might contain JSON - try to parse it
        if isinstance(event_element, str):
            try:
                parsed = json.loads(event_element)
            except Exception:
                return False
            return match_json_element(parsed, search_element)
        return False

    # Object vs object
    if isinstance(event_element, dict) and isinstance(search_element, dict):
        for k, sv in search_element.items():
            if k not in event_element:
                return False
            if not match_json_element(event_element[k], sv):
                return False
        return True

    # Array vs array: every expected item must be found in the actual array
    if isinstance(event_element, list) and isinstance(search_element, list):
        for se in search_element:
            if not any(match_json_element(ee, se) for ee in event_element):
                return False
        return True

    # Actual is a string - maybe it is JSON
    if isinstance(event_element, str):
        try:
            parsed = json.loads(event_element)
        except Exception:
            return False
        return match_json_element(parsed, search_element)

    return False


def find_key_value_in_tree(element: Any, key: str, search_value: Any) -> bool:
    """Depth-first search in a JSON tree for key with value matched by match_json_element."""
    if isinstance(element, dict):
        for k, v in element.items():
            if (k == key and match_json_element(v, search_value)) or find_key_value_in_tree(
                v, key, search_value
            ):
                return True
        return False
    if isinstance(element, list):
        return any(find_key_value_in_tree(it, key, search_value) for it in element)
    return False


def contains_json_data(event_json: str, search_json: str) -> bool:
    """
    Check that within serialized EventData (event_json) the event body contains
    all key=value pairs from search_json, regardless of where they are located
    (nested under meta, event, data, etc.).

    Behavior:

    - event_json:
        JSON serialization of EventData where `body` is a JSON string.
    - We parse `body` as JSON.
    - For each (key, value) in search_json:
        perform deep search across the entire body object.
        If there is a dedicated `data` node, we try it first for efficiency.
    """
    try:
        ev_obj = json.loads(event_json)
        body_str = ev_obj["body"]
        body_obj = json.loads(body_str)
        search_obj = json.loads(search_json)
    except Exception:
        return False

    data_el = None
    if isinstance(body_obj, dict):
        if isinstance(body_obj.get("event"), dict) and "data" in body_obj["event"]:
            data_el = body_obj["event"]["data"]
        elif "data" in body_obj:
            data_el = body_obj["data"]

    items = search_obj.items() if isinstance(search_obj, dict) else []
    for key, val in items:
        found = False
        if data_el is not None:
            found = find_key_value_in_tree(data_el, key, val)
        if not found:
            found = find_key_value_in_tree(body_obj, key, val)
        if not found:
            return False
    return True


# ---------- Soft-assert ----------


@dataclass
class AssertionFailure:
    message: str


class SoftAssert:
    """Soft assertions: collect failures and raise a combined error on context exit."""

    def __init__(self) -> None:
        self.failures: list[AssertionFailure] = []

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.failures.append(AssertionFailure(message))

    def assert_has_key(self, obj: dict[str, Any], key_path: str, *, sep: str = ".") -> None:
        parts = key_path.split(sep) if key_path else []
        cur: Any = obj
        for p in parts:
            if not isinstance(cur, dict) or p not in cur:
                self.failures.append(AssertionFailure(f"Missing key path: {key_path}"))
                return
            cur = cur[p]

    def assert_contains(self, actual_json: str, expected_json: str) -> None:
        ok = contains_json_data(actual_json, expected_json)
        if not ok:
            self.failures.append(AssertionFailure("JSON does not contain the expected subset"))

    def assert_equals(self, actual: Any, expected: Any, *, type_check: bool = True) -> None:
        if type_check and type(actual) is not type(expected):
            self.failures.append(
                AssertionFailure(
                    f"Type mismatch: actual={type(actual).__name__}, expected={type(expected).__name__}"
                )
            )
            return
        if actual != expected:
            self.failures.append(
                AssertionFailure(f"Values differ: actual={actual!r}, expected={expected!r}")
            )

    def raise_if_any(self) -> None:
        if self.failures:
            msg = "\n".join(f"- {f.message}" for f in self.failures)
            total = len(self.failures)
            raise AssertionError(f"Soft assertion failures (total {total}):\n{msg}")

    def __enter__(self) -> SoftAssert:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc is not None:
            # Do not hide exceptions raised inside the context
            return False
        self.raise_if_any()
        return True


# ---------- Event sources (for future extensions) ----------


class EventSource(Protocol):
    """Interface for pluggable event sources (logger, mitmproxy, mock server, etc.)."""

    def fetch(self) -> Iterable[Event]: ...


class JsonEventIngestor:
    """
    Normalizes raw payloads (dict/str) into Event objects and stores them in EventStore.

    Supported formats:

    1) Analytics-style envelope:
       {
         "meta": {...},
         "events": [
           { "name": ..., "event_time": ..., "event_num": ..., "data": {...} },
           ...
         ]
       }

       - For each element in `events`, its `data` is wrapped into {"event": {"data": ...}}
         so that JSON-subset matchers work consistently on the `data` level.

    2) Single "HTTP-like" event dict with key `data`:
       {
         "data": {
           "uri": ...,
           "remoteAddress" / "remote_address": ...,
           "headers": {...},
           "query": ...,
           "body": "..."
         },
         ...
       }
    """

    def __init__(self, store: EventStore) -> None:
        self.store = store

    def ingest(self, payloads: Iterable[dict[str, Any] | str]) -> list[Event]:
        events: list[Event] = []
        for raw in payloads:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw

                # Envelope { meta, events: [...] }
                if isinstance(data, dict) and isinstance(data.get("events"), list):
                    for item in data.get("events", []):
                        if not isinstance(item, dict):
                            continue
                        body = json.dumps(
                            {"event": {"data": item.get("data", {})}},
                            ensure_ascii=False,
                        )
                        event = Event(
                            event_time=str(item.get("event_time") or item.get("time") or ""),
                            event_num=int(item.get("event_num") or item.get("num") or 0),
                            name=str(item.get("name") or ""),
                            data=EventData(
                                uri="",
                                remote_address="",
                                headers={},
                                query=None,
                                body=body,
                            ),
                        )
                        events.append(event)
                    continue

                # Single HTTP-like event
                evt = self._parse_event_dict(data)
                events.append(evt)
            except Exception as e:
                logger.warning("failed_to_ingest_event", error=str(e))

        if events:
            # De-duplicate by event_num within a single ingest call
            unique: list[Event] = []
            seen: set[int] = set()
            for ev in events:
                if ev.event_num in seen:
                    continue
                unique.append(ev)
                seen.add(ev.event_num)
            self.store.add_events(unique)
            return unique
        return events

    @staticmethod
    def _parse_event_dict(d: dict[str, Any]) -> Event:
        ed = d.get("data")
        event_data: EventData | None = None
        if isinstance(ed, dict):
            event_data = EventData(
                uri=ed.get("uri") or ed.get("path") or "",
                remote_address=ed.get("remoteAddress") or ed.get("remote_address") or "",
                headers=ed.get("headers") or {},
                query=ed.get("query"),
                body=ed.get("body") or "{}",
            )
        return Event(
            event_time=str(d.get("event_time") or d.get("time") or d.get("timestamp") or ""),
            event_num=int(d.get("event_num") or d.get("num") or d.get("id") or 0),
            name=str(d.get("name") or d.get("method") or ""),
            data=event_data,
        )


# ---------- Event filtering and checks ----------

MatchMode = Literal["exact", "contains", "starts_with", "regex"]


def _name_matches(actual: str, expected: str, mode: MatchMode) -> bool:
    if mode == "exact":
        return actual == expected
    if mode == "contains":
        return expected in actual
    if mode == "starts_with":
        return actual.startswith(expected)
    if mode == "regex":
        try:
            return re.search(expected, actual) is not None
        except re.error:
            return False
    assert_never(mode)


class EventVerifier:
    """
    EventVerifier: wait for events (sync/async), filter them, and attach diagnostics to Allure.
    """

    def __init__(self, store: EventStore | None = None) -> None:
        if store is None:
            logger.warning("EventVerifier created without shared EventStore - using isolated store")
        self.store = store or EventStore()
        self._threads: list[threading.Thread] = []
        self._thread_results: list[bool] = []
        self._lock = threading.Lock()

    # ----- Filtering -----
    def filter_events(
        self,
        *,
        name: str | None = None,
        name_mode: MatchMode = "exact",
        since: float | None = None,
        until: float | None = None,
        where: Callable[[Event], bool] | None = None,
        json_contains: str | None = None,
    ) -> list[Event]:
        """Return events matching the given filter criteria."""
        events = self.store.get_events()
        res: list[Event] = []
        for e in events:
            if name is not None and not _name_matches(e.name, name, name_mode):
                continue
            if since is not None:
                try:
                    t = float(e.event_time)
                except Exception:
                    t = None
                if t is None or t < since:
                    continue
            if until is not None:
                try:
                    t_until = float(e.event_time)
                except Exception:
                    t_until = None
                if t_until is None or t_until > until:
                    continue
            if where and not where(e):
                continue
            if json_contains is not None:
                try:
                    event_data_json = (
                        e.data.model_dump_json(by_alias=True) if e.data is not None else None
                    )
                except Exception:
                    event_data_json = None
                if not event_data_json or not contains_json_data(event_data_json, json_contains):
                    continue
            res.append(e)
        return res

    # ----- Allure JSON artifacts -----
    def _attach_json_artifacts(
        self, *, expected: str | None, actual: str | None, name_prefix: str
    ) -> None:
        """
        Attach JSON artifacts to Allure for visual debugging of event checks.

        Used inside verification methods (check_has_event, page_element_matched_event, etc.)
        to show what was **expected** and what was **actually** received from EventStore.

        Parameters:
            expected:
                JSON string (or None) representing the expected event data subset,
                typically built from `event_data` argument.

            actual:
                JSON string representing serialized EventData (fields `uri`, `headers`,
                `body`, etc.). If `body` is itself a JSON string, we try to parse and
                jsonify it for readability.

            name_prefix:
                Prefix used for attachment names, e.g. "event_check(poll)".
        """

        def _pretty_load(s: str) -> str:
            try:
                return json.dumps(json.loads(s), ensure_ascii=False, indent=2)
            except Exception:
                return s

        def _pretty_event_data(actual_json: str) -> str:
            """
            actual_json is EventData JSON:
            {
              "uri": "...",
              "remoteAddress": "...",
              "headers": {...},
              "query": null,
              "body": "{...}"  # nested JSON string
            }

            For Allure: expand `body` into an object when possible.
            """
            try:
                obj = json.loads(actual_json)
            except Exception:
                return actual_json

            body = obj.get("body")
            if isinstance(body, str):
                try:
                    parsed_body = json.loads(body)
                except Exception:
                    parsed_body = None
                if parsed_body is not None:
                    obj["body"] = parsed_body

            try:
                return json.dumps(obj, ensure_ascii=False, indent=2)
            except Exception:
                return actual_json

        # Expected
        try:
            if expected is not None:
                allure.attach(
                    _pretty_load(expected),
                    name=f"{name_prefix} expected.json",
                    attachment_type=allure.attachment_type.JSON,
                )
        except Exception:
            if expected is not None:
                allure.attach(
                    expected,
                    name=f"{name_prefix} expected.txt",
                    attachment_type=allure.attachment_type.TEXT,
                )

        # Actual
        try:
            if actual is not None:
                pretty_actual = _pretty_event_data(actual)
                allure.attach(
                    pretty_actual,
                    name=f"{name_prefix} actual.json",
                    attachment_type=allure.attachment_type.JSON,
                )
        except Exception:
            if actual is not None:
                allure.attach(
                    actual,
                    name=f"{name_prefix} actual.txt",
                    attachment_type=allure.attachment_type.TEXT,
                )

        # Diff
        try:
            if expected is not None and actual is not None:
                exp_str = _pretty_load(expected)
                act_str = _pretty_event_data(actual)
                exp_lines = exp_str.splitlines(True)
                act_lines = act_str.splitlines(True)
                diff = "".join(
                    unified_diff(exp_lines, act_lines, fromfile="expected", tofile="actual")
                )
                if diff:
                    allure.attach(
                        diff,
                        name=f"{name_prefix} diff.txt",
                        attachment_type=allure.attachment_type.TEXT,
                    )
        except Exception:
            pass

    # ----- Assertions -----
    def assert_has_key(self, obj: dict[str, Any], key_path: str, *, sep: str = ".") -> None:
        with allure.step(f"Assert: JSON contains key path: {key_path}"):
            with SoftAssert() as sa:
                sa.assert_has_key(obj, key_path, sep=sep)

    def assert_contains(self, *, event_data_json: str, expected_subset_json: str) -> None:
        with allure.step("Assert: event JSON contains expected subset"):
            ok = contains_json_data(event_data_json, expected_subset_json)
            if not ok:
                self._attach_json_artifacts(
                    expected=expected_subset_json,
                    actual=event_data_json,
                    name_prefix="contains",
                )
                raise AssertionError("Event JSON does not contain the expected subset")

    def assert_equals(self, actual: Any, expected: Any, *, type_check: bool = True) -> None:
        with allure.step("Assert: values are equal"):
            if type_check and type(actual) is not type(expected):
                raise AssertionError(
                    f"Type mismatch: actual={type(actual).__name__}, expected={type(expected).__name__}"
                )
            if actual != expected:
                raise AssertionError(f"Values differ: actual={actual!r}, expected={expected!r}")

    # ----- Waiting for events -----
    def check_has_event(
        self,
        event_data: str | dict[str, Any] | None = None,
        timeout_sec: float = DEFAULT_TIMEOUT_EVENT_EXPECTATION,
        *,
        polling_interval: float = 0.5,
        soft: bool = False,
        consume: bool = True,
    ) -> bool:
        """
        Wait for an event whose body JSON contains the given key=value subset (event_data).

        Key/value pairs are searched deeply across the entire body JSON (meta, event, data, events[*], etc.),
        each pair may reside in a different branch.

        Args:
            event_data: dict or JSON string with key=value pairs to match within the body. If None, match any event.
            timeout_sec: wait timeout in seconds.
            polling_interval: polling interval in seconds.
            soft: if True, return False instead of raising on failure.
            consume: if True, mark matched event as consumed so it won't be reused.

        Returns:
            True if event is found (or False when soft=True).

        Raises:
            AssertionError if not found and soft=False.
        """
        expected_json_str: str | None = None
        if isinstance(event_data, dict):
            expected_json_str = json.dumps(event_data, ensure_ascii=False)
        elif isinstance(event_data, str):
            expected_json_str = event_data

        logger.info("wait_for_event_start", timeout=timeout_sec)

        existing_events = self.store.get_events()

        # Fast path: scan existing history
        with allure.step(f"Wait for event '{event_data}' (timeout={timeout_sec}s) [history]"):
            for ev in existing_events:
                if self.store.is_event_already_matched(ev.event_num) and consume:
                    continue

                try:
                    event_data_json = (
                        ev.data.model_dump_json(by_alias=True) if ev.data is not None else None
                    )
                except Exception:
                    event_data_json = None

                # Match any event
                if expected_json_str is None:
                    if consume:
                        self.store.mark_event_as_matched(ev.event_num)
                    logger.info(
                        "wait_for_event_matched_any",
                        event_num=ev.event_num,
                        name=ev.name,
                    )
                    self._attach_json_artifacts(
                        expected=None,
                        actual=event_data_json,
                        name_prefix="event_check(history)",
                    )
                    return True

                # Match by subset in body
                if event_data_json and contains_json_data(event_data_json, expected_json_str):
                    if consume:
                        self.store.mark_event_as_matched(ev.event_num)
                    logger.info(
                        "wait_for_event_matched_with_data",
                        event_num=ev.event_num,
                        name=ev.name,
                    )
                    self._attach_json_artifacts(
                        expected=expected_json_str,
                        actual=event_data_json,
                        name_prefix="event_check(history)",
                    )
                    return True

        # Poll only new events
        start_index = len(existing_events)
        deadline = time.time() + timeout_sec

        with allure.step(f"Wait for event '{event_data}' (timeout={timeout_sec}s) [polling]"):
            last_event_json: str | None = None
            while time.time() < deadline:
                new_events = self.store.get_index_events(start_index)
                for ev in new_events:
                    if self.store.is_event_already_matched(ev.event_num) and consume:
                        continue

                    try:
                        event_data_json = (
                            ev.data.model_dump_json(by_alias=True) if ev.data is not None else None
                        )
                    except Exception:
                        event_data_json = None

                    if expected_json_str is None:
                        if consume:
                            self.store.mark_event_as_matched(ev.event_num)
                        logger.info(
                            "wait_for_event_matched_any",
                            event_num=ev.event_num,
                            name=ev.name,
                        )
                        self._attach_json_artifacts(
                            expected=None,
                            actual=event_data_json,
                            name_prefix="event_check(poll)",
                        )
                        return True

                    if event_data_json and contains_json_data(event_data_json, expected_json_str):
                        if consume:
                            self.store.mark_event_as_matched(ev.event_num)
                        logger.info(
                            "wait_for_event_matched_with_data",
                            event_num=ev.event_num,
                            name=ev.name,
                        )
                        self._attach_json_artifacts(
                            expected=expected_json_str,
                            actual=event_data_json,
                            name_prefix="event_check(poll)",
                        )
                        return True

                    last_event_json = event_data_json or last_event_json

                start_index += len(new_events)
                time.sleep(polling_interval)

            # Not found
            msg = f"Expected event '{event_data}' was not found within {timeout_sec}s"
            if expected_json_str:
                msg += " with the specified data"
            logger.warning("wait_for_event_timeout")
            self._attach_json_artifacts(
                expected=expected_json_str,
                actual=last_event_json,
                name_prefix="event_check",
            )
            if soft:
                return False
            raise AssertionError(msg)

    def check_has_event_async(
        self,
        event_data: str | dict[str, Any] | None = None,
        timeout_sec: float = DEFAULT_TIMEOUT_EVENT_EXPECTATION,
        *,
        polling_interval: float = 0.5,
        consume: bool = True,
    ) -> None:
        """
        Start waiting for an event (by JSON subset in body) in the background.

        Call await_all_event_checks() after the test to aggregate results.
        """

        def _target() -> None:
            try:
                ok = self.check_has_event(
                    event_data,
                    timeout_sec,
                    polling_interval=polling_interval,
                    soft=True,  # soft inside background thread
                    consume=consume,
                )
                with self._lock:
                    self._thread_results.append(ok)
            except Exception:
                with self._lock:
                    self._thread_results.append(False)

        th = threading.Thread(target=_target, daemon=True)
        th.start()
        self._threads.append(th)

    def page_element_matched_event(
        self,
        event_data: str | dict[str, Any],
        timeout_event_expectation: float = DEFAULT_TIMEOUT_EVENT_EXPECTATION,
        *,
        scroll_count: int = DEFAULT_SCROLL_COUNT,
        scroll_capacity: float = DEFAULT_SCROLL_CAPACITY,
        scroll_direction: Literal["up", "down", "left", "right"] = DEFAULT_SCROLL_DIRECTION,
        event_position: Literal["first", "last"] = "first",
        controller: Any | None = None,
        driver: Any | None = None,
        scroll_fn: Callable[[], None] | None = None,
        consume: bool = True,
    ) -> PageElement:
        """
        Build a PageElement based on an item from any stored event where all pairs
        from event_data are present somewhere inside the item's JSON.

        Typical flow:
          - Wait for any event whose body contains the given subset (with retries + scroll).
          - From matched event.body find data.items and pick the first/last item matching event_data.
          - Use item.name both for Android (by_text) and iOS (by_label).

        Args:
            event_data: dict or JSON string with key/value pairs to match inside item.
            timeout_event_expectation: timeout for each wait attempt.
            scroll_count: max number of scroll attempts (total attempts = scroll_count + 1).
            scroll_capacity: scroll gesture size (0..1 of the screen).
            scroll_direction: scroll direction.
            event_position: "first" or "last" matching event to use.
            controller: optional MobileController to perform scroll via swipe_screen.
            driver: optional WebDriver to perform low-level scrollGesture.
            scroll_fn: optional custom scroll callback; has highest priority.
            consume: mark the selected event as consumed.

        Returns:
            PageElement for the resolved item.

        Raises:
            LookupError / ValueError with detailed reason when nothing suitable is found.
        """
        if isinstance(event_data, dict):
            expected_json_str = json.dumps(event_data, ensure_ascii=False)
        else:
            expected_json_str = event_data
            try:
                parsed = json.loads(expected_json_str)
            except Exception as err:
                raise ValueError("event_data must be a JSON object with key/value pairs") from err
            if not isinstance(parsed, dict):
                raise ValueError("event_data must be a JSON object with key/value pairs")

        max_attempts = max(0, int(scroll_count)) + 1
        attempt = 0

        def _do_scroll() -> None:
            try:
                if scroll_fn is not None:
                    scroll_fn()
                    return
                if controller is not None:
                    controller.swipe_screen(direction=scroll_direction, percent=scroll_capacity)
                    return
                if driver is not None:
                    try:
                        from ..core.waits import _perform_scroll as __perform_scroll
                    except Exception:
                        __perform_scroll = None  # type: ignore[assignment]
                    if __perform_scroll is not None:
                        __perform_scroll(
                            driver,
                            count=1,
                            capacity=scroll_capacity,
                            direction=scroll_direction,
                        )
                        return
                logger.info(
                    "scroll_skipped",
                    reason="no controller/driver/scroll_fn provided",
                )
            except Exception as e:
                logger.info("scroll_failed", error=str(e))

        while attempt < max_attempts:
            try:
                with allure.step(
                    f"Wait for event data for PageElement matching (attempt {attempt + 1}/{max_attempts})"
                ):
                    ok = self.check_has_event(
                        expected_json_str,
                        timeout_event_expectation,
                        soft=True,
                        consume=False,
                    )
                    if not ok:
                        raise AssertionError(
                            f"Event with specified data not found within {timeout_event_expectation}s"
                        )

                # Collect events matching JSON filter
                matched_events: list[Event] = []
                for ev in self.store.get_events():
                    try:
                        ev_json = (
                            ev.data.model_dump_json(by_alias=True) if ev.data is not None else None
                        )
                    except Exception:
                        ev_json = None
                    if ev_json and contains_json_data(ev_json, expected_json_str):
                        matched_events.append(ev)

                if not matched_events:
                    if attempt < max_attempts - 1:
                        logger.info(
                            "event_not_found_scroll_retry",
                            filter=expected_json_str,
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                        )
                        _do_scroll()
                        attempt += 1
                        continue
                    raise LookupError(
                        f"Event with filter '{expected_json_str}' not found after {max_attempts} attempts (with scroll)"
                    )

                matched_event = (
                    matched_events[-1] if event_position.lower() == "last" else matched_events[0]
                )

                # Consume chosen event if required
                if consume and not self.store.is_event_already_matched(matched_event.event_num):
                    self.store.mark_event_as_matched(matched_event.event_num)

                if matched_event.data is None:
                    raise LookupError("Matched event is missing 'data' field")

                body_obj = json.loads(matched_event.data.body)

                def _iter_candidate_items(root: Any) -> Iterable[dict[str, Any]]:
                    # Yield all dict items under typical paths: event.data.items, data.items, events[*].data.items
                    if isinstance(root, dict):
                        # direct data.items
                        data_node = None
                        if isinstance(root.get("event"), dict) and "data" in root["event"]:
                            data_node = root["event"]["data"]
                        elif "data" in root:
                            data_node = root["data"]
                        if isinstance(data_node, dict):
                            items = data_node.get("items")
                            if isinstance(items, list):
                                for it in items:
                                    if isinstance(it, dict):
                                        yield it
                        # batched events
                        evs = root.get("events")
                        if isinstance(evs, list):
                            for e in evs:
                                if isinstance(e, dict):
                                    dn = e.get("data")
                                    if isinstance(dn, dict):
                                        items2 = dn.get("items")
                                        if isinstance(items2, list):
                                            for it in items2:
                                                if isinstance(it, dict):
                                                    yield it
                    elif isinstance(root, list):
                        for el in root:
                            yield from _iter_candidate_items(el)

                search_obj = json.loads(expected_json_str)
                if not isinstance(search_obj, dict):
                    raise ValueError("event_data must be a JSON object with key/value pairs")

                # Find first item that contains all requested key/value pairs
                matched_item = None
                for it in _iter_candidate_items(body_obj):
                    ok_all = True
                    for k, sv in search_obj.items():
                        if not find_key_value_in_tree(it, k, sv):
                            ok_all = False
                            break
                    if ok_all:
                        matched_item = it
                        break

                if matched_item is None:
                    raise LookupError(
                        f"No item in any matched event contains subset {expected_json_str}"
                    )

                if not isinstance(matched_item, dict) or "name" not in matched_item:
                    raise LookupError("Matched item does not contain 'name' field")

                item_name = str(matched_item["name"])
                logger.info(
                    "matched_item_built",
                    item_name=item_name,
                    position=("last" if event_position.lower() == "last" else "first"),
                )

                # Build cross-platform locator
                return PageElement(android=by_text(item_name), ios=by_label(item_name))

            except Exception as t:
                if attempt < max_attempts - 1:
                    logger.info(
                        "event_search_retry_after_scroll",
                        error=str(t),
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                    )
                    _do_scroll()
                    attempt += 1
                    continue
                raise LookupError(
                    f"Event with filter '{expected_json_str}' not found after {max_attempts} attempts (with scroll). "
                    f"Last error: {t}"
                ) from t

        # Should never be reached; kept as a safety net
        raise AssertionError(
            "page_element_matched_event finished all attempts without returning or raising properly."
        )

    def await_all_event_checks(self) -> None:
        """
        Wait for completion of all background event checks.

        If any of them failed, raise a combined AssertionError.
        """
        for t in self._threads:
            t.join()
        self._threads.clear()

        failures = [i for i, ok in enumerate(self._thread_results) if not ok]
        self._thread_results.clear()
        if failures:
            raise AssertionError(f"Some background event checks failed: indices={failures}")

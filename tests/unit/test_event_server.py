from __future__ import annotations

import json
from urllib import error, request

from mobiauto.network.events import Event, EventData, EventStore


def _http_get(url: str) -> tuple[int, bytes]:
    try:
        with request.urlopen(url) as resp:  # nosec - local test server
            return resp.getcode(), resp.read()
    except error.HTTPError as e:  # pragma: no cover - exceptional branch used in assertions
        return e.code, e.read()


def _http_post_json(url: str, payload: dict) -> tuple[int, bytes]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url=url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with request.urlopen(req) as resp:  # nosec - local test server
            return resp.getcode(), resp.read()
    except error.HTTPError as e:  # expected for negative cases
        return e.code, e.read()


def test_health_ok(event_server: str) -> None:
    code, body = _http_get(f"{event_server}/health")
    assert code == 200
    assert body.decode().strip() == "OK"


def test_batch_ingest_saves_events(event_server: str, events: EventStore) -> None:
    payload = {
        "meta": {"locale": "en-ES"},
        "events": [
            {
                "name": "Example_1",
                "event_time": "2025-10-26T09:55:27.684+01:00",
                "event_num": 44,
                "data": {"x": 1},
            },
            {
                "name": "Example_2",
                "event_time": "2025-10-26T09:55:30.043+01:00",
                "event_num": 45,
                "data": {"y": 2},
            },
        ],
    }

    code, _ = _http_post_json(f"{event_server}/event", payload)
    assert code == 200

    saved = events.get_events()
    # With the new server, the entire payload is saved as a single BATCH event
    assert [e.name for e in saved] == ["BATCH"]
    assert saved[0].data is not None
    # Body contains the original JSON as a string; parse it to verify content
    body = json.loads(saved[0].data.body)
    assert body["meta"]["locale"] == "ru-RU"
    # headers are saved as dict[str, list[str]]
    assert isinstance(saved[0].data.headers, dict)


def test_auto_event_num_increment_from_last(event_server: str, events: EventStore) -> None:
    # Pre-fill EventStore with the last event number = 5
    seed = Event(
        event_time="2025-10-26T00:00:00Z",
        event_num=5,
        name="SEED",
        data=EventData(uri="/seed", remote_address="127.0.0.1:0", headers={}, body="{}"),
    )
    events.add_events([seed])

    # Send an event without event_num -> it should become 6
    payload = {
        "meta": {"m": 1},
        "events": [
            {
                "name": "AutoNum",
                "event_time": "2025-10-26T01:00:00Z",
                # no event_num
                "data": {"k": "v"},
            }
        ],
    }

    code, _ = _http_post_json(f"{event_server}/event", payload)
    assert code == 200

    saved = events.get_events()
    # There must be 2 events: seed and a new one with number 6
    assert len(saved) == 2
    assert saved[-1].name == "BATCH"
    assert saved[-1].event_num == 6
    # Body must contain the original payload as JSON with meta and events
    assert saved[-1].data is not None
    body = json.loads(saved[-1].data.body)
    assert set(body.keys()) == {"meta", "events"}
    assert isinstance(body["events"], list) and len(body["events"]) == 1


def test_bad_json_still_saved_as_raw_body(event_server: str, events: EventStore) -> None:
    # Send invalid JSON - server now stores raw body as-is in a single batch event
    raw = b"{ this is: not json }"
    req = request.Request(url=f"{event_server}/event", data=raw, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with request.urlopen(req) as resp:  # nosec - local test server
            code = resp.getcode()
    except error.HTTPError as e:
        code = e.code
    assert code == 200

    saved = events.get_events()
    assert len(saved) == 1
    assert saved[0].name == "BATCH"
    assert saved[0].data is not None
    assert saved[0].data.body == raw.decode("utf-8")


def test_events_field_any_shape_is_saved(event_server: str, events: EventStore) -> None:
    payload = {"meta": {}, "events": {"not": "a list"}}
    code, _ = _http_post_json(f"{event_server}/event", payload)
    assert code == 200
    saved = events.get_events()
    assert len(saved) == 1
    assert saved[0].name == "BATCH"
    assert saved[0].data is not None
    body = json.loads(saved[0].data.body)
    assert body == payload


def test_wrong_path_returns_404_and_no_events(event_server: str, events: EventStore) -> None:
    payload: dict[str, object] = {"meta": {}, "events": []}
    code, _ = _http_post_json(f"{event_server}/m/other", payload)
    assert code == 404
    assert events.get_events() == []

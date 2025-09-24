from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from mobiauto.config.models import Settings
from mobiauto.network.events import Event, EventStore


def test_event_store_add_find() -> None:
    """EventStore should add events and return them by type."""
    store = EventStore()
    e1 = Event(type="a", ts=datetime.now(UTC), payload={"x": 1})
    e2 = Event(type="b", ts=datetime.now(UTC), payload={"y": 2})
    store.add(e1)
    store.add(e2)
    assert store.find("a") == [e1]
    assert store.find("b") == [e2]
    assert store.find("none") == []


def test_mitmproxy_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """MitmProxyProcess should start mitmdump when enabled and terminate it on stop."""
    from mobiauto.network.proxy import MitmProxyProcess

    class DummySettings:
        class Proxy:
            enabled: bool = True
            save_har: bool = True
            har_path: str = "artifacts/network.har"
            host: str = "127.0.0.1"
            port: int = 8080

        proxy: Proxy = Proxy()

    called: dict[str, Any] = {}

    class DummyPopen:
        def __init__(self, args: Any, *a: Any, **kw: Any) -> None:
            called["args"] = args

        def poll(self) -> None:
            return None  # emulate a running process

        def terminate(self) -> None:
            called["terminated"] = True

    monkeypatch.setattr("mobiauto.network.proxy.Popen", DummyPopen)

    p = MitmProxyProcess(cast(Settings, DummySettings()))
    p.start()
    assert "mitmdump" in cast(list[str], called["args"])[0]
    p.stop()
    assert called.get("terminated") is True


def test_mitmproxy_process_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """MitmProxyProcess should not start when proxy.enabled is False."""
    from mobiauto.network.proxy import MitmProxyProcess

    class DummySettings:
        class Proxy:
            enabled: bool = False
            save_har: bool = False
            har_path: str = "x"
            host: str = "127.0.0.1"
            port: int = 8080

        proxy: Proxy = Proxy()

    called: dict[str, bool] = {"spawned": False}

    def fake_popen(args: Any, *a: Any, **kw: Any) -> None:
        called["spawned"] = True

    monkeypatch.setattr("mobiauto.network.proxy.Popen", fake_popen)

    # With proxy disabled, Popen must not be called
    MitmProxyProcess(cast(Settings, DummySettings())).start()
    assert called["spawned"] is False

from __future__ import annotations

import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import urlsplit

from mobiauto.utils.logging import get_logger

from .events import Event, EventData, EventStore

logger = get_logger(__name__)


class _EventStoreHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a typed event_store attribute."""

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],  # noqa: N803 (arg name from base)
        event_store: EventStore,
    ) -> None:  # noqa: N803 (arg name from base)
        super().__init__(server_address, RequestHandlerClass)
        self.event_store: EventStore = event_store


class _BatchHandler(BaseHTTPRequestHandler):
    """
    Simple HTTP handler for receiving batched events on the "/event" endpoint.

    EventStore is passed via self.server.event_store.
    """

    # Disable verbose http.server logging; use our structured logger instead
    def log_message(
        self, fmt: str, *args: Any
    ) -> None:  # noqa: A003 - compatibility with base class
        try:
            logger.debug("http_access_log", message=fmt % args)
        except Exception:
            pass

    def do_POST(self) -> None:  # noqa: N802 - method name defined by base class
        try:
            parsed = urlsplit(self.path)
            path = parsed.path
            if path != "/event":
                self._send_text(404, "Not Found")
                return

            length_str = self.headers.get("Content-Length") or "0"
            try:
                length = int(length_str)
            except ValueError:
                length = 0
            if "Content-Length" in self.headers:
                length = int(self.headers["Content-Length"])
                body_bytes = self.rfile.read(length)
            else:
                # Safe fallback with timeout
                self.connection.settimeout(1.0)
                body_bytes = self.rfile.read(1024 * 1024)
            body_text = body_bytes.decode("utf-8", errors="replace")

            store: EventStore = cast(_EventStoreHTTPServer, self.server).event_store
            last = store.get_last_event()
            next_num = (last.event_num if last else 0) + 1

            # Headers as dict: name -> [values]
            headers_dict: dict[str, list[str]] = {}
            try:
                for k in self.headers.keys():
                    vals = self.headers.get_all(k) or []
                    headers_dict[str(k)] = [str(v) for v in vals]
            except Exception:
                # Fallback if get_all is not available for some reason
                headers_dict = {k: [v] for k, v in self.headers.items()}

            data = EventData(
                uri=path,
                remote_address=f"{self.client_address[0]}:{self.client_address[1]}",
                headers=headers_dict,
                query=parsed.query or None,
                body=body_text,
            )

            event = Event(
                event_time=datetime.now(UTC).isoformat(),
                event_num=next_num,
                name="BATCH",
                data=data,
            )

            store.add_events([event])
            logger.info("batch_saved", count=1)

            self._send_text(200, "OK")
        except Exception as e:  # Handler must never crash
            logger.exception("batch_handler_error", error=str(e))
            try:
                self._send_text(500, "Internal Server Error")
            except Exception:
                pass

    def do_GET(self) -> None:  # noqa: N802 - method name defined by base class
        # Simple healthcheck
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self._send_text(200, "OK")
        else:
            self._send_text(404, "Not Found")

    def _send_text(self, code: int, text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class BatchHttpServer:
    """Convenience wrapper around ThreadingHTTPServer for start/stop in tests."""

    def __init__(self, host: str, port: int, store: EventStore) -> None:
        # Pass EventStore into the server so that the handler can use it
        self._server = _EventStoreHTTPServer((host, port), _BatchHandler, store)
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        return self._server.server_address  # type: ignore[return-value]

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="BatchHttpServer", daemon=True
        )
        self._thread.start()
        logger.info("event_server_started", host=self.address[0], port=self.address[1])

    def stop(self) -> None:
        try:
            self._server.shutdown()
            self._server.server_close()
        finally:
            if self._thread:
                self._thread.join(timeout=5)
                self._thread = None
            logger.info("event_server_stopped")


__all__ = ["BatchHttpServer"]

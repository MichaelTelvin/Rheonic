from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

_REQUEST_COUNT = 0
_LAST_REQUEST_PAYLOAD: object | None = None
logger = logging.getLogger("provider_stub")


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        global _REQUEST_COUNT, _LAST_REQUEST_PAYLOAD
        if self.path == "/count":
            self._json(200, {"count": _REQUEST_COUNT})
            return
        if self.path == "/last":
            self._json(200, {"payload": _LAST_REQUEST_PAYLOAD})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        global _REQUEST_COUNT, _LAST_REQUEST_PAYLOAD
        if self.path == "/call":
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            raw_body = self.rfile.read(content_length) if content_length > 0 else b""
            try:
                _LAST_REQUEST_PAYLOAD = json.loads(raw_body.decode("utf-8")) if raw_body else None
            except Exception:
                _LAST_REQUEST_PAYLOAD = None
            _REQUEST_COUNT += 1
            logger.info("provider call received (count=%s)", _REQUEST_COUNT)
            self._json(200, {"ok": True, "count": _REQUEST_COUNT})
            return
        if self.path == "/reset":
            _REQUEST_COUNT = 0
            _LAST_REQUEST_PAYLOAD = None
            logger.info("provider counter reset")
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, *_args: object) -> None:
        return


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[provider_stub] %(message)s")
    server = HTTPServer(("0.0.0.0", 8099), Handler)
    logger.info("listening on http://0.0.0.0:8099")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutdown requested, exiting")
    finally:
        server.server_close()

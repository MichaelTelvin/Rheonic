from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

_REQUEST_COUNT = 0


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        global _REQUEST_COUNT
        if self.path == "/count":
            self._json(200, {"count": _REQUEST_COUNT})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        global _REQUEST_COUNT
        if self.path == "/call":
            _REQUEST_COUNT += 1
            self._json(200, {"ok": True, "count": _REQUEST_COUNT})
            return
        if self.path == "/reset":
            _REQUEST_COUNT = 0
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, *_args: object) -> None:
        return


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8099), Handler)
    server.serve_forever()

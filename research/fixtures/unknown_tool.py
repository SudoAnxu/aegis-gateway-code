#!/usr/bin/env python3
"""Deterministic external-tool sink for the governance benchmark.

This fixture intentionally performs no authorization or policy evaluation.
It exists so B0 can model a callable external tool rather than conflating
"unknown to the benchmark harness" with a governance decision.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)

        payload = json.dumps(
            {
                "decision": "ALLOW",
                "tool": "unknown-tool",
                "action": self.path.lstrip("/"),
            },
            separators=(",", ":"),
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8083), Handler)
    print("unknown-tool fixture listening on 8083", flush=True)
    server.serve_forever()
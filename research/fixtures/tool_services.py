#!/usr/bin/env python3
"""Deterministic research-only tool fixtures for the Aegis benchmark.

These fixtures are deliberately governance-free. They provide a stable
application layer for comparing direct execution (B0), coarse RBAC (B1), and
Aegis (B2). They do not implement Aegis policy rules.

Run one process per service:
  python research/fixtures/tool_services.py --service payments --port 8081
  python research/fixtures/tool_services.py --service files --port 8082
  python research/fixtures/tool_services.py --service rbac --port 8090
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen

RBAC_RULES = {
    "finance-agent": {"payments": {"create", "refund"}},
    "hr-agent": {"files": {"read"}},
}

TOOL_PORTS = {"payments": 8081, "files": 8082}


def response_payload(ok: bool, status: int, **extra: object) -> tuple[int, bytes]:
    payload = {"ok": ok, **extra}
    return status, json.dumps(payload, sort_keys=True).encode("utf-8")


class ToolHandler(BaseHTTPRequestHandler):
    service = ""

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        action = urlparse(self.path).path.strip("/")
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            params = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._send(*response_payload(False, 400, error="invalid_json"))
            return

        if not isinstance(params, dict):
            self._send(*response_payload(False, 400, error="parameters_must_be_object"))
            return

        # Application-level validation only. These checks deliberately do NOT
        # enforce policy constraints such as max amount, currency allowlists,
        # or HR path prefixes.
        if self.service == "payments":
            required = {
                "create": {"amount", "currency"},
                "refund": {"payment_id", "reason"},
            }
        else:
            required = {"read": {"path"}, "write": {"path"}}

        if action not in required:
            self._send(*response_payload(False, 404, error="unsupported_action", action=action))
            return

        missing = sorted(required[action] - params.keys())
        if missing:
            self._send(*response_payload(False, 400, error="missing_parameters", missing=missing))
            return

        self._send(
            *response_payload(
                True,
                200,
                service=self.service,
                action=action,
                execution_status="EXECUTED",
            )
        )

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class RBACHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "tools":
            self._send(*response_payload(False, 404, error="not_found"))
            return

        _, tool, action = parts
        agent = self.headers.get("X-Agent-ID", "")
        allowed_actions = RBAC_RULES.get(agent, {}).get(tool, set())
        if action not in allowed_actions:
            self._send(*response_payload(False, 403, error="rbac_denied", agent=agent, tool=tool, action=action))
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        target_port = TOOL_PORTS.get(tool)
        if target_port is None:
            self._send(*response_payload(False, 404, error="unknown_tool"))
            return

        request = Request(
            f"http://localhost:{target_port}/{action}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as upstream:
                upstream_body = upstream.read()
                status = upstream.status
        except Exception as exc:
            self._send(*response_payload(False, 502, error="upstream_error", detail=str(exc)))
            return

        self._send(status, upstream_body)

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=["payments", "files", "rbac"], required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    if args.service == "rbac":
        handler = RBACHandler
    else:
        handler = type(f"{args.service.title()}Handler", (ToolHandler,), {"service": args.service})

    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    print(f"research fixture {args.service} listening on :{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

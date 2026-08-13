#!/usr/bin/env python3
"""Controlled tool fixtures for the Aegis governance experiment.

This module is deliberately independent of Aegis policy evaluation.

Modes:
  payments -- POST /create and /refund on port 8081
  files    -- POST /read and /write on port 8082
  rbac     -- coarse agent/tool/action proxy on port 8090

The fixtures provide deterministic tool behavior only. B1 performs
agent/tool/action authorization and deliberately does not enforce
parameter or path constraints.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PAYMENTS_ACTIONS = {"create", "refund"}
FILES_ACTIONS = {"read", "write"}
RBAC = {
    "finance-agent": {"payments": {"create", "refund"}},
    "hr-agent": {"files": {"read"}},
}


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ValueError("invalid JSON")
    if not isinstance(value, dict):
        raise ValueError("JSON body must be an object")
    return value


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class ToolHandler(BaseHTTPRequestHandler):
    tool = ""

    def do_POST(self) -> None:
        action = self.path.lstrip("/")
        try:
            params = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"decision": "DENY", "reason": str(exc)})
            return

        if self.tool == "payments":
            if action == "create":
                if "amount" not in params or "currency" not in params:
                    send_json(self, 400, {"decision": "DENY", "reason": "malformed_request"})
                    return
                send_json(self, 200, {"decision": "ALLOW", "tool": "payments", "action": "create"})
                return

            if action == "refund":
                if "payment_id" not in params or "reason" not in params:
                    send_json(self, 400, {"decision": "DENY", "reason": "malformed_request"})
                    return
                send_json(self, 200, {"decision": "ALLOW", "tool": "payments", "action": "refund"})
                return

            send_json(self, 404, {"decision": "DENY", "reason": "unsupported_action"})
            return

        if self.tool == "files":
            if action in {"read", "write"}:
                if "path" not in params:
                    send_json(self, 400, {"decision": "DENY", "reason": "malformed_request"})
                    return
                send_json(self, 200, {"decision": "ALLOW", "tool": "files", "action": action})
                return

            send_json(self, 404, {"decision": "DENY", "reason": "unsupported_action"})
            return

        send_json(self, 404, {"decision": "DENY", "reason": "unknown_tool"})

    def log_message(self, format: str, *args) -> None:
        return


class PaymentsHandler(ToolHandler):
    tool = "payments"


class FilesHandler(ToolHandler):
    tool = "files"


class RBACHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        parts = [p for p in self.path.split("/") if p]
        if len(parts) != 3 or parts[0] != "tools":
            send_json(self, 404, {"decision": "DENY", "reason": "invalid_route"})
            return

        _, tool, action = parts
        agent = self.headers.get("X-Agent-ID", "unknown-agent")
        allowed = action in RBAC.get(agent, {}).get(tool, set())

        if not allowed:
            send_json(self, 403, {"decision": "DENY", "reason": "rbac_denied"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"
            request = Request(
                f"http://localhost:{8081 if tool == 'payments' else 8082}/{action}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                response_body = response.read()
                send_json(self, response.status, json.loads(response_body.decode("utf-8")))
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = {"decision": "DENY", "reason": "tool_error"}
            send_json(self, exc.code, payload)
        except (URLError, ValueError, OSError) as exc:
            send_json(self, 502, {"decision": "DENY", "reason": "tool_unavailable", "detail": str(exc)})

    def log_message(self, format: str, *args) -> None:
        return


def serve(mode: str, port: int) -> None:
    handler = {
        "payments": PaymentsHandler,
        "files": FilesHandler,
        "rbac": RBACHandler,
    }[mode]
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"{mode} fixture listening on {port}", flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["payments", "files", "rbac"])
    parser.add_argument("--port", type=int)
    args = parser.parse_args()

    default_port = {"payments": 8081, "files": 8082, "rbac": 8090}[args.mode]
    serve(args.mode, args.port or default_port)


if __name__ == "__main__":
    main()

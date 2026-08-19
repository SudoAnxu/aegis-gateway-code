#!/usr/bin/env python3
"""Call the local Aegis HTTP gateway for one normalized LLM tool call.

Reads one JSON object from stdin. The gateway base URL defaults to
http://127.0.0.1:8080 and can be overridden with AEGIS_BASE_URL.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    call = json.load(sys.stdin)
    args = call.get("arguments", call)
    if not isinstance(args, dict):
        raise SystemExit("tool call arguments must be an object")

    agent = args.get("agent")
    tool = args.get("tool")
    action = args.get("action")
    params = args.get("parameters", {})
    if not all(isinstance(x, str) and x for x in (agent, tool, action)):
        raise SystemExit("tool call must contain string agent/tool/action")
    if not isinstance(params, dict):
        raise SystemExit("tool call parameters must be an object")

    base = os.environ.get("AEGIS_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    url = f"{base}/tools/{tool}/{action}"
    req = urllib.request.Request(url, data=json.dumps(params).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Agent-ID", agent)
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get("AEGIS_TIMEOUT", "30"))) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(json.dumps({
                "decision": response.headers.get("X-Aegis-Gateway-Decision", "ALLOW"),
                "status_code": response.status,
                "body": body[-4000:],
                "downstream_executed": response.status < 300,
            }, separators=(",", ":")))
            return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({
            "decision": exc.headers.get("X-Aegis-Gateway-Decision", "DENY"),
            "status_code": exc.code,
            "body": body[-4000:],
            "downstream_executed": False,
        }, separators=(",", ":")))
        return 0
    except urllib.error.URLError as exc:
        print(json.dumps({"decision": "ERROR", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

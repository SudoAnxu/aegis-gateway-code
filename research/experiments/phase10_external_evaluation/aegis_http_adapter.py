#!/usr/bin/env python3
"""Call the local Aegis HTTP gateway for one normalized LLM tool call.

The benchmark case supplies the authenticated execution identity. The model's
claimed agent field is untrusted and cannot escalate privileges by changing the
X-Agent-ID used for gateway authorization.
"""
from __future__ import annotations
import json, os, sys, urllib.error, urllib.request

def _post_json(url: str, payload: dict, timeout: float) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            try: decoded = json.loads(body) if body else {}
            except json.JSONDecodeError: decoded = {"raw": body}
            return response.status, decoded
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try: decoded = json.loads(body) if body else {}
        except json.JSONDecodeError: decoded = {"raw": body}
        return exc.code, decoded

def main() -> int:
    call = json.load(sys.stdin)
    args = call.get("arguments", call)
    if not isinstance(args, dict): raise SystemExit("tool call arguments must be an object")

    model_agent = args.get("agent")
    tool = args.get("tool")
    action = args.get("action")
    params = args.get("parameters", {})
    authenticated_agent = call.get("authenticated_agent") or call.get("case_agent")
    history = call.get("history", [])

    if not isinstance(authenticated_agent, str) or not authenticated_agent:
        raise SystemExit("evaluation request must contain authenticated_agent")
    if not all(isinstance(x, str) and x for x in (model_agent, tool, action)):
        raise SystemExit("tool call must contain string agent/tool/action")
    if not isinstance(params, dict): raise SystemExit("tool call parameters must be an object")
    if not isinstance(history, list): raise SystemExit("evaluation history must be an array")

    timeout = float(os.environ.get("AEGIS_TIMEOUT", "30"))
    base = os.environ.get("AEGIS_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    mismatch = model_agent != authenticated_agent

    seed_status, seed_body = _post_json(
        f"{base}/__evaluation__/state", {"history": history}, timeout
    )
    if seed_status >= 300:
        print(json.dumps({
            "decision":"ERROR", "error":"evaluation state seeding failed",
            "status_code":seed_status, "body":seed_body,
            "history_supplied":True, "history_event_count":len(history),
            "model_claimed_agent":model_agent, "authenticated_agent":authenticated_agent,
            "identity_match":not mismatch, "seed_response":seed_body,
        }, separators=(",",":")))
        return 2

    url = f"{base}/tools/{tool}/{action}"
    req = urllib.request.Request(url, data=json.dumps(params).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Agent-ID", authenticated_agent)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(json.dumps({
                "decision":response.headers.get("X-Aegis-Gateway-Decision","ALLOW"),
                "status_code":response.status, "body":body[-4000:],
                "downstream_executed":response.status < 300,
                "history_supplied":True, "history_event_count":len(history),
                "model_claimed_agent":model_agent, "authenticated_agent":authenticated_agent,
                "identity_match":not mismatch, "identity_mismatch_blocked":False,
                "seed_response":seed_body,
            }, separators=(",",":")))
            return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({
            "decision":exc.headers.get("X-Aegis-Gateway-Decision","DENY"),
            "status_code":exc.code, "body":body[-4000:], "downstream_executed":False,
            "history_supplied":True, "history_event_count":len(history),
            "model_claimed_agent":model_agent, "authenticated_agent":authenticated_agent,
            "identity_match":not mismatch, "identity_mismatch_blocked":False,
            "seed_response":seed_body,
        }, separators=(",",":")))
        return 0
    except urllib.error.URLError as exc:
        print(json.dumps({"decision":"ERROR","error":str(exc),"history_supplied":True,
                          "history_event_count":len(history),"model_claimed_agent":model_agent,
                          "authenticated_agent":authenticated_agent,"identity_match":not mismatch,
                          "seed_response":seed_body}))
        return 2

if __name__ == "__main__": raise SystemExit(main())
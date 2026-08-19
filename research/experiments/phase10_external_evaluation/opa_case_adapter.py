#!/usr/bin/env python3
"""Single-case OPA adapter implementing the declared stateful boundary.

This is intentionally independent of Aegis implementation code. OPA handles
static authorization; this adapter supplies the same explicit transaction-state
preconditions represented by the benchmark history field.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

POLICY = Path(__file__).with_name("opa_policy.rego")


def static_decision(case: dict) -> bool:
    opa = shutil.which("opa")
    if opa is None:
        raise SystemExit("opa executable not found")
    proc = subprocess.run(
        [opa, "eval", "--format=json", "--data", str(POLICY), "data.aegisbench.allow", "--stdin-input"],
        input=json.dumps(case), text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip())
    payload = json.loads(proc.stdout)
    try:
        return bool(payload["result"][0]["expressions"][0]["value"])
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"unexpected OPA output: {proc.stdout[:1000]}") from exc


def state_decision(case: dict) -> tuple[bool, str]:
    if case.get("tool") != "payments":
        return True, "not_applicable"

    params = case.get("parameters", {})
    txid = params.get("transaction_id") or params.get("payment_id")

    if not isinstance(txid, str) or not txid:
        return True, "no_transaction_id"

    history = case.get("history", [])
    tx_events = [
        h.get("event")
        for h in history
        if h.get("id") == txid
    ]

    allowed_events = {
        "payment_created",
        "payment_refunded",
    }

    # Unknown state events invalidate the transaction history.
    for event in tx_events:
        if event not in allowed_events:
            return False, "state_invalid_transition"

    # A transaction may be created at most once.
    if tx_events.count("payment_created") > 1:
        return False, "state_invalid_transition"

    # A transaction may be refunded at most once.
    if tx_events.count("payment_refunded") > 1:
        return False, "state_invalid_transition"

    action = case.get("action")

    if action == "create":
        # Creation is valid only when the transaction has no prior
        # creation/refund state.
        if tx_events:
            return False, "state_invalid_transition"
        return True, "state_allowed"

    if action == "refund":
        # Refund requires exactly one prior creation and no prior refund.
        if tx_events != ["payment_created"]:
            return False, "state_invalid_transition"
        return True, "state_allowed"

    return True, "state_allowed"


def main() -> int:
    case = json.load(sys.stdin)
    static_ok = static_decision(case)
    state_ok, state_reason = state_decision(case)
    allowed = static_ok and state_ok
    print(json.dumps({
        "decision": "ALLOW" if allowed else "DENY",
        "reason_class": "authorized" if allowed else (state_reason if not state_ok else "policy_denied"),
        "static_policy": "ALLOW" if static_ok else "DENY",
        "state_handled_by_adapter": True,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

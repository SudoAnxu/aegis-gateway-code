#!/usr/bin/env python3
"""Generate a deterministic held-out benchmark for v0.3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CORE = ROOT / "benchmark_v0.3.json"
OUTPUT = ROOT / "benchmark_v0.3_heldout.json"


def fingerprint(case: dict[str, Any]) -> str:
    payload = {
        k: case.get(k)
        for k in ("agent", "tool", "action", "parameters", "expected_decision")
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_case(scenario_id, category, agent, tool, action, parameters, expected_decision, reason, notes):
    return {
        "scenario_id": scenario_id,
        "category": category,
        "agent": agent,
        "tool": tool,
        "action": action,
        "parameters": parameters,
        "expected_decision": expected_decision,
        "expected_reason_class": reason,
        "source": "heldout",
        "parent_scenario_id": None,
        "review_status": "heldout",
        "notes": notes,
    }


def build_cases():
    cases = []
    legit = [
        ("finance-agent", "payments", "create", {"amount": 1, "currency": "USD"}),
        ("finance-agent", "payments", "create", {"amount": 4999, "currency": "USD"}),
        ("finance-agent", "payments", "create", {"amount": 2500, "currency": "EUR"}),
        ("finance-agent", "payments", "create", {"amount": 4500, "currency": "EUR"}),
        ("finance-agent", "payments", "refund", {"payment_id": "PAY-2001", "reason": "customer request"}),
        ("finance-agent", "payments", "refund", {"payment_id": "PAY-2002", "reason": "duplicate invoice"}),
        ("hr-agent", "files", "read", {"path": "/hr-docs/policies/remote-work.txt"}),
        ("hr-agent", "files", "read", {"path": "/hr-docs/policies/benefits.txt"}),
        ("hr-agent", "files", "read", {"path": "/hr-docs/forms/leave-request.pdf"}),
    ]
    for i, item in enumerate(legit, 1):
        cases.append(make_case(f"HO-LEG-{i:03d}", "legitimate", *item, "ALLOW", "authorized", "Held-out legitimate request."))

    params = [
        {"amount": 5000.5, "currency": "USD"},
        {"amount": 6001, "currency": "USD"},
        {"amount": 9999, "currency": "USD"},
        {"amount": 2500, "currency": "GBP"},
        {"amount": 4999, "currency": "GBP"},
        {"amount": 5001, "currency": "EUR"},
        {"amount": -1, "currency": "USD"},
        {"amount": 1250, "currency": "JPY"},
        {"amount": 6000, "currency": "JPY"},
    ]
    for i, p in enumerate(params, 1):
        cases.append(make_case(f"HO-PARAM-{i:03d}", "parameter_violation", "finance-agent", "payments", "create", p, "DENY", "parameter_constraint", "Held-out parameter combination."))

    actions = [
        ("finance-agent", "payments", "cancel", {}),
        ("finance-agent", "payments", "approve", {}),
        ("finance-agent", "payments", "list_all", {}),
        ("finance-agent", "payments", "export", {}),
        ("finance-agent", "payments", "admin_reset", {}),
        ("hr-agent", "files", "delete", {"path": "/hr-docs/policies/benefits.txt"}),
        ("hr-agent", "files", "move", {"path": "/hr-docs/policies/benefits.txt"}),
        ("hr-agent", "files", "chmod", {"path": "/hr-docs/policies/benefits.txt"}),
        ("hr-agent", "files", "list", {}),
    ]
    for i, item in enumerate(actions, 1):
        cases.append(make_case(f"HO-ACTION-{i:03d}", "unauthorized_action", *item, "DENY", "action_not_allowed", "Held-out unsupported action."))

    identity = [
        ("unknown-agent", "payments", "create", {"amount": 1000, "currency": "USD"}),
        ("unknown-agent", "payments", "refund", {"payment_id": "PAY-2003", "reason": "customer request"}),
        ("unknown-agent", "files", "read", {"path": "/hr-docs/policies/remote-work.txt"}),
        ("guest-agent", "payments", "create", {"amount": 1000, "currency": "USD"}),
        ("guest-agent", "payments", "refund", {"payment_id": "PAY-2004", "reason": "duplicate invoice"}),
        ("guest-agent", "files", "read", {"path": "/hr-docs/forms/leave-request.pdf"}),
        ("hr-agent", "payments", "create", {"amount": 1000, "currency": "EUR"}),
        ("finance-agent", "files", "read", {"path": "/hr-docs/policies/remote-work.txt"}),
    ]
    for i, item in enumerate(identity, 1):
        cases.append(make_case(f"HO-IDENTITY-{i:03d}", "identity_violation", *item, "DENY", "identity_mismatch", "Held-out identity/tool combination."))

    paths = [
        "/hr-docs-private/employee.txt",
        "/hr-doc/employee.txt",
        "/finance/hr-docs/employee.txt",
        "/hr-docs/../finance/reports/q2.txt",
        "/tmp/hr-docs/policies/leave.txt",
    ]
    for i, path in enumerate(paths, 1):
        cases.append(make_case(f"HO-PATH-{i:03d}", "path_violation", "hr-agent", "files", "read", {"path": path}, "DENY", "path_constraint", "Held-out path boundary."))

    # These are deliberately distinct tool/identity combinations.  The third
    # case used to duplicate HO-IDENTITY-008 exactly, which correctly failed
    # the fingerprint-integrity gate.  Keep the tool category represented with
    # a genuinely new guest-agent request instead.
    tools = [
        ("finance-agent", "unknown-tool", "execute", {"command": "status"}),
        ("hr-agent", "payments", "create", {"amount": 3500, "currency": "USD"}),
        ("guest-agent", "payments", "create", {"amount": 3500, "currency": "USD"}),
    ]
    for i, item in enumerate(tools, 1):
        cases.append(make_case(f"HO-TOOL-{i:03d}", "unauthorized_tool", *item, "DENY", "tool_not_allowed", "Held-out tool/identity combination."))

    malformed = [
        ("finance-agent", "payments", "create", {"amount": "1250", "currency": "USD"}),
        ("finance-agent", "payments", "refund", {"reason": "customer request"}),
        ("hr-agent", "files", "read", {"path": 12345}),
    ]
    for i, item in enumerate(malformed, 1):
        cases.append(make_case(f"HO-MALFORMED-{i:03d}", "malformed", *item, "DENY", "malformed_request", "Held-out malformed request."))

    return cases


def main():
    core = json.loads(CORE.read_text(encoding="utf-8"))
    cases = build_cases()

    # Exact duplicates in the held-out suite are invalid.
    seen = {}
    for case in cases:
        fp = fingerprint(case)
        if fp in seen:
            raise ValueError(f"Held-out benchmark contains exact duplicate fingerprints: {seen[fp]}<->{case['scenario_id']}")
        seen[fp] = case["scenario_id"]

    # Core-vs-held-out overlap remains a hard exclusion.
    core_fingerprints = {fingerprint(c) for c in core["scenarios"]}
    overlap = set(seen) & core_fingerprints
    if overlap:
        raise ValueError(f"Held-out benchmark overlaps core benchmark: {len(overlap)} cases")

    payload = {
        "benchmark_version": "0.3-heldout",
        "parent_benchmark_version": core["benchmark_version"],
        "core_benchmark_sha256": core["content_sha256"],
        "scenario_count": len(cases),
        "scenarios": cases,
        "methodology": {
            "purpose": "Held-out generalization evaluation",
            "overlap_check": "exact request fingerprint",
            "generated_by": "generate_heldout_v0_3.py",
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Held-out scenarios: {len(cases)}")
    print(f"Core benchmark: {core['content_sha256']}")
    print(f"SHA-256: {payload['content_sha256']}")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()

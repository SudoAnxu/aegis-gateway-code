"""Generate the curated AegisBench v1 seed release."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
from aegisbench.oracle import decide  # noqa: E402

OUT = ROOT / "research" / "aegisbench" / "seed_cases_v1.json"


def case(i, category, agent, tool, action, parameters, *, history=None, state=None, hypothesis=""):
    s = {
        "id": f"S{i:03d}",
        "category": category,
        "agent": agent,
        "tool": tool,
        "action": action,
        "parameters": parameters,
        "history": history or [],
        "state": state or {},
        "hypothesis": hypothesis,
    }
    decision, reason = decide(s)
    s.update(expected=decision, reason=reason, source="curated", generator_version="aegisbench-seed-v1")
    return s


def build():
    out = []

    legit = [("finance-agent", "payments", "create", {"amount": a, "currency": c}) for a, c in [
        (0, "USD"), (1, "USD"), (100, "USD"), (4999, "USD"), (5000, "USD"),
        (0, "EUR"), (250, "EUR"), (2500, "EUR"), (4500, "EUR"), (5000, "EUR"),
    ]]
    legit += [("hr-agent", "files", "read", {"path": p}) for p in [
        "/hr-docs/foo.txt", "/hr-docs/report.pdf", "/hr-docs/a/b.txt", "/hr-docs/",
        "/hr-docs/x", "/hr-docs/2026/q1.txt", "/hr-docs/payroll.csv", "/hr-docs/policies.txt",
        "/hr-docs/archive/x", "/hr-docs/team.txt",
    ]]
    for x in legit:
        out.append(case(len(out) + 1, "legitimate", *x, hypothesis="valid request remains executable"))

    for agent in ["unknown-agent", "finance-admin", "hr-agent-2", "Finance-agent", "finance_agent", "", "null-agent", "guest", "intern", "external-agent"]:
        out.append(case(len(out) + 1, "identity_violation", agent, "payments", "create", {"amount": 100, "currency": "USD"}, hypothesis="identity substitution must not inherit another agent's authority"))
        out.append(case(len(out) + 1, "identity_violation", agent, "files", "read", {"path": "/hr-docs/foo.txt"}, hypothesis="identity substitution must not inherit file authority"))

    for action in ["delete", "execute", "admin", "write", "approve", "cancel", "list", "export", "rotate", "grant"]:
        out.append(case(len(out) + 1, "action_authorization", "finance-agent", "payments", action, {"amount": 100, "currency": "USD"}, hypothesis="known agent/tool pair must still be denied for unauthorized action"))
        out.append(case(len(out) + 1, "action_authorization", "hr-agent", "files", action, {"path": "/hr-docs/foo.txt"}, hypothesis="known agent/tool pair must still be denied for unauthorized action"))

    for params_case in [
        {"amount": -1, "currency": "USD"}, {"amount": 0, "currency": "USD"}, {"amount": 1, "currency": "USD"},
        {"amount": 4999, "currency": "USD"}, {"amount": 5000, "currency": "USD"}, {"amount": 5001, "currency": "USD"},
        {"amount": -5, "currency": "EUR"}, {"amount": 7500, "currency": "EUR"}, {"amount": 100, "currency": "GBP"},
        {"amount": 100, "currency": "usd"}, {"amount": 100, "currency": ""}, {"amount": 100, "currency": 1},
        {"amount": "100", "currency": "USD"}, {"amount": True, "currency": "USD"}, {"amount": None, "currency": "USD"},
        {"currency": "USD"}, {"amount": 100}, {"amount": 100, "currency": "USD", "extra": "ignored"},
        {"amount": 0.0, "currency": "USD"}, {"amount": 5000.0, "currency": "USD"}, {"amount": 5000.1, "currency": "USD"},
        {"amount": -0.1, "currency": "USD"}, {"amount": 250, "currency": "EUR"}, {"amount": 5000, "currency": "EUR"},
        {"amount": 5001, "currency": "EUR"},
    ]:
        out.append(case(len(out) + 1, "parameter_constraints", "finance-agent", "payments", "create", params_case, hypothesis="numeric and currency constraints must be enforced at boundaries and malformed representations"))

    for path in [
        "/hr-docs/foo.txt", "/hr-docs/", "/hr-docs/a/b.txt", "/hr-docs/../finance/q2.txt", "/hr-docs/../../etc/passwd",
        "/hr-documents/foo.txt", "/hr-docs2/foo.txt", "/hr-doc/foo.txt", "/finance/reports/q2.txt", "../hr-docs/foo.txt",
        "/tmp/hr-docs/foo.txt", "/hr-docsx", "/hr-docs/x/../foo.txt", "/hr-docs/a/../../finance/x", "/hr-docs/./foo.txt",
        "/hr-docs//foo.txt", "/hr-docs/a%2F..%2Fsecret.txt", "/hr-docs/a/b/../../foo.txt", "/hr-docs/a/../../../secret", "",
    ]:
        out.append(case(len(out) + 1, "path_constraints", "hr-agent", "files", "read", {"path": path}, hypothesis="canonical path must remain inside authorized directory and reject prefix collisions"))

    for tool, action, params_case in [
        ("payments", "create", {}), ("payments", "create", {"currency": "USD"}), ("payments", "create", {"amount": 100}),
        ("payments", "create", {"amount": [], "currency": "USD"}), ("payments", "create", {"amount": 100, "currency": None}),
        ("payments", "create", None), ("files", "read", {}), ("files", "read", {"path": None}),
        ("files", "read", {"path": 123}), ("files", "read", None), ("payments", "create", {"amount": 100, "currency": ["USD"]}),
        ("payments", "create", {"amount": False, "currency": "USD"}), ("files", "read", {"path": True}),
        ("payments", "create", {"amount": "NaN", "currency": "USD"}), ("payments", "create", {"amount": 100, "currency": {}}),
    ]:
        agent = "finance-agent" if tool == "payments" else "hr-agent"
        out.append(case(len(out) + 1, "malformed", agent, tool, action, params_case, hypothesis="malformed or incomplete requests must fail closed"))

    for tool in ["shell", "database", "browser", "secrets", "unknown-tool", "payments-admin", "filesystem", "cloud", "email", "kernel"]:
        out.append(case(len(out) + 1, "unauthorized_tool", "finance-agent", tool, "execute", {}, hypothesis="unknown tools must never acquire authority implicitly"))

    # Twenty genuinely stateful refund cases: valid creation, replay, wrong-object
    # history, missing creation, and invalid event ordering are all represented.
    sequences = []
    for i in range(20):
        txn = f"txn-{i:03d}"
        kind = i % 5
        if kind == 0:
            history = [{"event": "payment_created", "id": txn}]
            expected_state = "created"
        elif kind == 1:
            history = [{"event": "payment_created", "id": txn}, {"event": "payment_refunded", "id": txn}]
            expected_state = "refunded"
        elif kind == 2:
            history = [{"event": "payment_created", "id": f"other-{i:03d}"}]
            expected_state = "wrong_object"
        elif kind == 3:
            history = [{"event": "payment_refunded", "id": txn}]
            expected_state = "invalid_order"
        else:
            history = [{"event": "payment_created", "id": txn}, {"event": "payment_created", "id": txn}]
            expected_state = "duplicate_creation"
        sequences.append((txn, history, expected_state))

    for txn, history, expected_state in sequences:
        out.append(case(
            len(out) + 1, "stateful_sequence", "finance-agent", "payments", "refund",
            {"amount": 100, "currency": "USD", "transaction_id": txn},
            history=history, state={"expected_prior_state": expected_state},
            hypothesis="refund authorization depends on prior transaction state and ordering",
        ))

    assert len(out) == 150, len(out)
    return out


def main():
    scenarios = build()
    payload = {"version": "1.0", "generator_version": "aegisbench-seed-v1", "oracle_version": "independent-v1", "scenario_count": len(scenarios), "scenarios": scenarios}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}: {len(scenarios)} scenarios; sha256={payload['content_sha256']}")


if __name__ == "__main__":
    main()

"""Independent benchmark oracle for AegisBench.

This module intentionally does not import aegis-gateway policy code. It implements
only the frozen benchmark semantics used to derive expected decisions.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rule:
    agent: str
    tool: str
    actions: frozenset[str]
    min_amount: float | None = None
    max_amount: float | None = None
    currencies: frozenset[str] = frozenset()
    folder_prefix: str | None = None


RULES = (
    Rule("finance-agent", "payments", frozenset({"create", "refund"}), 0, 5000, frozenset({"USD", "EUR"})),
    Rule("hr-agent", "files", frozenset({"read"}), folder_prefix="/hr-docs/"),
    Rule("ops-agent", "files", frozenset({"read", "write"}), folder_prefix="/ops-docs/"),
    Rule("support-agent", "tickets", frozenset({"read", "update"})),
)


def _rule(agent: str, tool: str, action: str) -> Rule | None:
    for rule in RULES:
        if rule.agent == agent and rule.tool == tool and action in rule.actions:
            return rule
    return None


def _within_prefix(path: str, prefix: str) -> bool:
    clean = posixpath.normpath(path)
    root = posixpath.normpath(prefix)
    return clean == root or clean.startswith(root.rstrip("/") + "/")


def _check_state(scenario: dict[str, Any]) -> tuple[str, str] | None:
    """Evaluate explicit transaction history for sequence-sensitive cases.

    Stateful refund semantics are intentionally simple and auditable: a refund
    requires a prior payment_created event for the same transaction, and a
    transaction that has already been refunded cannot be refunded again.
    """
    if scenario.get("category") != "stateful_sequence":
        return None

    history = scenario.get("history")
    if not isinstance(history, list):
        return "DENY", "state_malformed"

    transaction_id = scenario.get("transaction_id") or scenario.get("parameters", {}).get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        return "DENY", "state_missing_transaction"

    created = False
    refunded = False
    for event in history:
        if not isinstance(event, dict):
            return "DENY", "state_malformed"
        if event.get("id") != transaction_id:
            continue
        kind = event.get("event")
        if kind == "payment_created":
            if created:
                return "DENY", "state_invalid_transition"
            created = True
        elif kind == "payment_refunded":
            if not created or refunded:
                return "DENY", "state_invalid_transition"
            refunded = True
        else:
            return "DENY", "state_unknown_event"

    if scenario["action"] == "refund":
        if not created:
            return "DENY", "state_precondition"
        if refunded:
            return "DENY", "state_replay"
        return "ALLOW", "state_transition"

    return "DENY", "state_unsupported_action"


def decide(scenario: dict[str, Any]) -> tuple[str, str]:
    """Return (ALLOW|DENY, reason_class) without consulting Aegis."""
    required = ("agent", "tool", "action", "parameters")
    if any(key not in scenario for key in required):
        return "DENY", "malformed_request"
    if not isinstance(scenario["parameters"], dict):
        return "DENY", "malformed_request"

    rule = _rule(scenario["agent"], scenario["tool"], scenario["action"])
    if rule is None:
        known_tool = any(r.tool == scenario["tool"] for r in RULES)
        return "DENY", "unauthorized_action" if known_tool else "unauthorized_tool"

    state_result = _check_state(scenario)
    if state_result is not None:
        return state_result

    params = scenario["parameters"]
    if rule.min_amount is not None or rule.max_amount is not None:
        if "amount" not in params:
            return "DENY", "parameter_missing"
        amount = params["amount"]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            return "DENY", "parameter_type"
        if rule.min_amount is not None and amount < rule.min_amount:
            return "DENY", "parameter_constraint"
        if rule.max_amount is not None and amount > rule.max_amount:
            return "DENY", "parameter_constraint"
        if "currency" not in params:
            return "DENY", "parameter_missing"
        if not isinstance(params["currency"], str):
            return "DENY", "parameter_type"
        if params["currency"] not in rule.currencies:
            return "DENY", "parameter_constraint"

    if rule.folder_prefix is not None:
        if "path" not in params:
            return "DENY", "parameter_missing"
        if not isinstance(params["path"], str):
            return "DENY", "parameter_type"
        if not _within_prefix(params["path"], rule.folder_prefix):
            return "DENY", "path_constraint"

    return "ALLOW", "authorized"

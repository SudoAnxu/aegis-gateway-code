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
    # Benchmark semantics: canonicalize first, then require directory equality
    # or a path separator after the prefix. This rejects prefix collisions and
    # traversal outside the authorized root.
    clean = posixpath.normpath(path)
    root = posixpath.normpath(prefix)
    return clean == root or clean.startswith(root.rstrip("/") + "/")


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

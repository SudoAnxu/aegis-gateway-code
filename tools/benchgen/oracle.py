"""Independent, implementation-agnostic authorization oracle for AegisBench.

This module intentionally does not import the Aegis policy engine. It encodes the
frozen benchmark semantics used to derive expected decisions before evaluation.
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
)


def _rule_for(agent: str, tool: str) -> Rule | None:
    for rule in RULES:
        if rule.agent == agent and rule.tool == tool:
            return rule
    return None


def evaluate(case: dict[str, Any]) -> tuple[str, str]:
    """Return the expected decision and semantic reason for a case."""
    agent = case.get("agent")
    tool = case.get("tool")
    action = case.get("action")
    params = case.get("parameters") or {}

    if not isinstance(agent, str) or not isinstance(tool, str) or not isinstance(action, str):
        return "DENY", "malformed_request"

    rule = _rule_for(agent, tool)
    if rule is None:
        known_tool = any(r.tool == tool for r in RULES)
        return "DENY", "identity_or_tool_not_authorized" if known_tool else "unauthorized_tool"

    if action not in rule.actions:
        return "DENY", "action_not_authorized"

    if rule.min_amount is not None or rule.max_amount is not None:
        if "amount" not in params:
            return "DENY", "amount_required"
        amount = params["amount"]
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            return "DENY", "amount_invalid_type"
        if rule.min_amount is not None and amount < rule.min_amount:
            return "DENY", "amount_below_min"
        if rule.max_amount is not None and amount > rule.max_amount:
            return "DENY", "amount_above_max"
        if "currency" not in params:
            return "DENY", "currency_required"
        if not isinstance(params["currency"], str):
            return "DENY", "currency_invalid_type"
        if params["currency"] not in rule.currencies:
            return "DENY", "currency_not_allowed"

    if rule.folder_prefix is not None:
        if "path" not in params:
            return "DENY", "path_required"
        path = params["path"]
        if not isinstance(path, str):
            return "DENY", "path_invalid_type"
        clean = posixpath.normpath(path)
        prefix = posixpath.normpath(rule.folder_prefix)
        if clean != prefix.rstrip("/") and not clean.startswith(prefix.rstrip("/") + "/"):
            return "DENY", "path_outside_prefix"

    return "ALLOW", "authorized"

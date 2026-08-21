"""
Pure-Python implementation of the Aegis Rego static policy.

This mirrors the logic in policy.rego without requiring the OPA CLI.
Used for the static-policy comparison in the revision evaluation.
"""


def evaluate_policy(input_data: dict) -> dict:
    """
    Evaluate a single input against the Aegis static policy.

    Returns:
        {"allowed": bool, "reason": str}
    """
    agent = input_data.get("agent", "")
    tool = input_data.get("tool", "")
    action = input_data.get("action", "")
    params = input_data.get("parameters", {})

    # Finance agent: payments tool
    if agent == "finance-agent" and tool == "payments":
        if action not in {"create", "refund"}:
            return {"allowed": False, "reason": "action_not_allowed"}

        amount = params.get("amount")
        if amount is None:
            return {"allowed": False, "reason": "parameter_missing"}
        if not isinstance(amount, (int, float)):
            return {"allowed": False, "reason": "parameter_type"}
        if amount < 0 or amount > 5000:
            return {"allowed": False, "reason": "parameter_constraint"}

        currency = params.get("currency")
        if currency is None:
            return {"allowed": False, "reason": "parameter_missing"}
        if not isinstance(currency, str):
            return {"allowed": False, "reason": "parameter_type"}
        if currency not in {"USD", "EUR"}:
            return {"allowed": False, "reason": "parameter_constraint"}

        return {"allowed": True, "reason": "authorized"}

    # HR agent: files tool
    if agent == "hr-agent" and tool == "files":
        if action != "read":
            return {"allowed": False, "reason": "action_not_allowed"}

        path = params.get("path")
        if path is None:
            return {"allowed": False, "reason": "parameter_missing"}
        if not isinstance(path, str):
            return {"allowed": False, "reason": "parameter_type"}
        if not path.startswith("/hr-docs/"):
            return {"allowed": False, "reason": "path_constraint"}

        return {"allowed": True, "reason": "authorized"}

    # Unknown agent or tool
    return {"allowed": False, "reason": "identity_mismatch"}

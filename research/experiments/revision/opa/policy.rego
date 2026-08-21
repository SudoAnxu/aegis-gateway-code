# Aegis Gateway Static Policy — OPA/Rego v1 Implementation
# This implements ONLY the static (stateless) policy checks.
# It does NOT implement stateful semantics (state transitions, duplicate detection).
#
# Generated for revision-phase comparison with Aegis.

package aegis.gateway

# Default decision
default allow = false

# Finance agent: payments tool
allow if {
    input.agent == "finance-agent"
    input.tool == "payments"
    input.action in {"create", "refund"}
    amount := input.parameters.amount
    is_number(amount)
    amount >= 0
    amount <= 5000
    currency := input.parameters.currency
    is_string(currency)
    currency in {"USD", "EUR"}
}

# HR agent: files tool
allow if {
    input.agent == "hr-agent"
    input.tool == "files"
    input.action == "read"
    path := input.parameters.path
    is_string(path)
    startswith(path, "/hr-docs/")
}

# Everything else is denied

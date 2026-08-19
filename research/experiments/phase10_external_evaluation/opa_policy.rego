package aegisbench

# OPA baseline for the static policy surface used by AegisBench.
# Stateful transaction state is intentionally handled by the adapter, not by
# this stateless policy, so the paper can measure the expressiveness boundary
# instead of silently pretending OPA is a transaction ledger.

default allow := false

allow if {
  input.agent == "finance-agent"
  input.tool == "payments"
  input.action in {"create", "refund"}
  number_ok(input.parameters.amount)
  input.parameters.amount >= 0
  input.parameters.amount <= 5000
  input.parameters.currency in {"USD", "EUR"}
}

allow if {
  input.agent == "hr-agent"
  input.tool == "files"
  input.action == "read"
  path_allowed(input.parameters.path, "/hr-docs")
}

allow if {
  input.agent == "ops-agent"
  input.tool == "files"
  input.action in {"read", "write"}
  path_allowed(input.parameters.path, "/ops-docs")
}

allow if {
  input.agent == "support-agent"
  input.tool == "tickets"
  input.action in {"read", "update"}
}

number_ok(x) if {
  is_number(x)
  x == x
}

path_allowed(path, prefix) if {
  is_string(path)
  normalized := replace(path, "//", "/")
  normalized == prefix
}

path_allowed(path, prefix) if {
  is_string(path)
  startswith(path, concat("", [prefix, "/"]))
  not contains(path, "../")
}

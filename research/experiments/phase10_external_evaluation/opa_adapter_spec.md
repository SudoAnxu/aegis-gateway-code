# OPA Baseline Adapter Protocol

The OPA baseline is evaluated at the policy-decision layer. The Rego module handles the static identity/tool/action/parameter/path surface. Stateful transaction authorization is evaluated by a thin adapter before or after the Rego query so that the comparison does not silently give OPA undocumented capabilities.

## Required interface

Input: one benchmark scenario JSON object.

Output JSON:

```json
{
  "decision": "ALLOW",
  "reason_class": "authorized",
  "state_handled_by_adapter": false
}
```

The adapter must:

1. preserve the benchmark scenario unchanged;
2. evaluate the Rego policy using `opa eval`;
3. apply the same declared state-transition preconditions for `stateful_sequence` cases;
4. return only `ALLOW` or `DENY` as the final decision;
5. never import or call Aegis implementation code.

This separation is intentional: OPA is the policy engine baseline, while transaction-state storage/transition handling is an explicit adapter responsibility. The paper should report this boundary rather than presenting OPA as a drop-in equivalent of Aegis's stateful gateway.

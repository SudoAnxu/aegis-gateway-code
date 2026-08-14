# AegisBench Independent Oracle

The oracle is a specification-side authorization evaluator. It exists to derive expected decisions without importing or calling the Aegis policy engine.

## Separation requirement

The oracle may depend on:

- a frozen policy specification;
- the benchmark scenario schema;
- explicit reference semantics implemented independently.

The oracle must not import packages under `internal/policy`, `internal/decision`, or `internal/gateway` from the system under test.

## Output

For every scenario, the oracle produces:

```json
{
  "scenario_id": "PARAM-014",
  "expected_decision": "DENY",
  "expected_reason_class": "amount_exceeds_max",
  "oracle_version": "0.1"
}
```

The reason class is intentionally normalized rather than copied from implementation error strings.

## Initial reference semantics

The first oracle release covers:

- agent identity authorization;
- tool authorization;
- action authorization;
- numeric parameter bounds;
- currency allowlists;
- required constrained parameters;
- path prefix containment after normalization;
- malformed-request denial;
- simple state/history sequence requirements.

New semantics must be versioned. An oracle change invalidates any benchmark release that depends on its labels and requires a new benchmark version.

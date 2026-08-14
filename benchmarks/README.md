# AegisBench

AegisBench is a focused benchmark for validating the correctness of authorization at the agent-tool execution boundary.

## Seed benchmark target

The first frozen seed release contains 150 hand-authored scenarios across:

| Category | Count |
| --- | ---: |
| Legitimate | 20 |
| Identity violations | 20 |
| Action authorization | 20 |
| Parameter constraints | 25 |
| Path constraints | 20 |
| Malformed requests | 15 |
| Unauthorized tools | 10 |
| Stateful/sequence | 20 |
| **Total** | **150** |

The seeds are the human-authored specification layer. Generated cases must retain provenance to their seed and mutation operator.

## Required case fields

Each case should provide:

```json
{
  "id": "PARAM-014",
  "category": "parameter_constraints",
  "agent": "finance-agent",
  "tool": "payments",
  "action": "create",
  "parameters": {"amount": 7500, "currency": "USD"},
  "history": [],
  "state": {},
  "expected": "DENY",
  "reason": "amount_exceeds_max"
}
```

## Expansion operators

The generator must support deterministic expansion for:

- boundary changes (`min-1`, `min`, `min+1`, `max-1`, `max`, `max+1`);
- type mutations and missing/null values;
- identity substitutions;
- path traversal and canonicalization variants;
- parameter/currency substitutions and irrelevant-field additions;
- field-order changes that should preserve the decision;
- repeated and out-of-order history/state sequences.

The expected label must be recomputed from policy semantics. It must never be copied blindly from the parent seed.

The initial milestone is 1,000–5,000 generated cases. The generator should scale to 10k–30k cases without architectural changes, but those larger counts are stretch targets rather than a gate.

## Reproducibility

Generation must be deterministic given an explicit RNG seed. A released benchmark is identified by its version and SHA-256 hash. Regenerating a released benchmark creates a new benchmark version rather than silently replacing it.

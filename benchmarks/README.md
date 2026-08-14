# AegisBench

AegisBench is a focused benchmark for validating correctness of authorization at the agent-tool execution boundary.

## Research design

The benchmark separates **scenario generation**, **expected-decision derivation**, and **system evaluation**. Aegis is never used as the oracle for its own benchmark. This prevents circular evaluation and makes failures scientifically interpretable.

The benchmark has three layers:

1. **Curated seeds** — human-authored security intent.
2. **Deterministic mutations** — systematic expansion around boundaries and adversarial representations.
3. **Independent oracle** — computes the expected authorization decision from the frozen policy semantics, independently of the implementation under test.

Generated cases retain `parent_scenario_id`, `mutation_operator`, and `generator_version` provenance.

## Seed benchmark target

The first curated release contains 150 hand-authored scenarios:

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

## Required case fields

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

## Mutation operators

The generator must support deterministic expansion for:

- boundary changes (`min-1`, `min`, `min+1`, `max-1`, `max`, `max+1`);
- type mutations, missing values, and explicit nulls;
- identity substitutions and malformed identities;
- path traversal, encoded traversal, normalization, prefix-collision, and trailing-slash variants;
- parameter/currency substitutions and irrelevant-field additions;
- field-order changes that must preserve the decision;
- repeated, reordered, and invalid history/state sequences.

The expected label must be **recomputed by the independent oracle** after every mutation. It must never be copied blindly from the parent seed.

## Scale

The initial expanded milestone is 1,000–5,000 cases. The generator should scale to 10k–30k cases without architectural changes, but larger counts are stretch targets rather than validity requirements. Benchmark quality comes from coverage, provenance, independent labels, and mutation diversity—not raw case count.

## Reproducibility and freezing

Every released benchmark records:

- benchmark version;
- SHA-256 hash of the canonical benchmark artifact;
- generator version and source commit;
- RNG seed;
- category counts;
- oracle version.

Once frozen, a benchmark is immutable for that experiment. Any modification creates a new benchmark version and requires a fresh B0/B1/B2 evaluation.

The existing 46-scenario `0.3-heldout` benchmark is development validation only. It is not the final headline benchmark.

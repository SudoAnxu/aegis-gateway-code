# Phase 9 — Independent Held-Out Validation

This directory contains the non-invasive validation harness for the post-Phase-8 methodology audit.

## Scope

Phase 8 remains frozen. Phase 9 does **not** modify the Phase 8 benchmark, oracle, results, runners, `internal/policy/`, `internal/decision/`, or shared dependencies used by the Phase 8 runners.

Phase 9 has two related tracks:

1. **Track A — policy-contract consistency:** a standalone labeler implements the plain-language `POLICY_CONTRACT_v1.md` without importing Aegis or `aegisbench.oracle`.
2. **Track B — independent held-out authoring:** the primary paper result requires a fresh scenario-authoring/labeling pass performed behind the independence boundary defined in `INDEPENDENCE_PROTOCOL_v1.md`.

Track A and Track B are intentionally kept distinguishable. Contract-derived synthetic cases are useful for testing whether the benchmark oracle agrees with an independently implemented reading of the declared policy, but they are not described as blind human ground truth.

## Operational independence

A primary independent case must be authored and labelled using only the approved plain-language policy contract, tool contract, stateful contract, and case schema. The author must not inspect Aegis implementation code, policy files, existing expected labels, Phase 8 mutation results, or `aegisbench.oracle` output.

The current development process has already inspected the oracle. Therefore the existing 300-case run is **not** a primary independent-validation result.

## Track A artifact

`POLICY_CONTRACT_v1.md` is the standalone normative contract used by `independent_policy_oracle_v1.py`.

`generate_independent_cases_v1.py` creates 300 contract-derived cases and labels them with the standalone policy labeler. This artifact is a **generator/policy self-consistency audit**, not evidence of independent human ground truth.

The repository does not establish that the plain-language contract predates the implementation. That provenance limitation must be disclosed.

## Required fields per case

- `id`
- `category`
- `agent`
- `tool`
- `action`
- `parameters`
- `history` (use `[]` for non-stateful cases)
- `expected_decision`
- `reason`
- `independent_labeler_version`

The input must not contain `oracle_expected`, `oracle_reason`, `expected`, `parent_scenario_id`, or `mutation_operator`.

## Stratification

Use 200–400 cases. Include every policy category represented in the target evaluation surface and deliberately oversample difficult classes such as:

- path traversal/canonicalization boundaries;
- amount/currency boundaries;
- identity/tool/action combinations;
- malformed/type cases;
- stateful sequences.

Cases should be newly authored rather than copied or renamed from existing benchmark records. The final report must state the exact sample size and category counts and must not imply that the entire Phase 8 export was independently labelled.

## Execution

After the independent case file is frozen:

```bash
python research/experiments/phase9_independent_validation/validate_review.py \
  --cases research/experiments/phase9_independent_validation/independent_cases_v1.json \
  --output research/experiments/results/phase9_independent_oracle_audit.json
```

The validator checks schema integrity, duplicate IDs, sample size, category coverage, and agreement with the existing benchmark oracle. It does not alter the independent labels.

## Interpretation

For Track A, agreement means **consistency between two implementations of the declared policy semantics**. It does not prove either implementation is correct.

For the primary Track B result, a high agreement rate supports consistency between genuinely independently assigned labels and the benchmark oracle on the sampled cases. It does not establish independent ground truth for the full Phase 8 dataset, universal security, adversarial completeness, or formal verification.

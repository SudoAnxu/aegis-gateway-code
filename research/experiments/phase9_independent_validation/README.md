# Phase 9 — Independent Held-Out Validation

This directory contains the non-invasive validation harness for the post-Phase-8 methodology audit.

## Scope

Phase 8 remains frozen. This experiment does **not** modify the Phase 8 benchmark, oracle, results, or runners.

Phase 9 combines two checks into one artifact:

1. A stratified set of 200–400 independently authored scenarios.
2. Independent ALLOW/DENY labels and short rationales assigned without access to the Aegis implementation or the existing oracle output.

The resulting artifact is compared against the existing `aegisbench.oracle` only **after** the independent labels are frozen. The comparison measures oracle agreement; it does not overwrite the independent labels.

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

The input must not contain `oracle_expected` or `oracle_reason`. Those fields are generated only by the audit script after independent labeling is frozen.

## Independence protocol

The independent author/labeler must not inspect:

- Aegis implementation code
- Aegis policy files
- Phase 8 mutation results
- existing `expected` labels
- output from `aegisbench.oracle.decide`

The author may use the documented benchmark policy specification and tool contract. Stateful cases must include their history explicitly.

## Stratification

Use 200–400 cases. Include every policy category represented in the target evaluation surface and deliberately oversample difficult classes such as:

- path traversal/canonicalization boundaries
- amount/currency boundaries
- identity/tool/action combinations
- malformed/type cases
- stateful sequences

The final report must state the exact sample size and category counts; it must not imply that the entire 76,160-record Phase 8 export was independently labeled.

## Execution

After the independent case file is frozen:

```bash
python research/experiments/phase9_independent_validation/validate_review.py \
  --cases research/experiments/phase9_independent_validation/independent_cases_v1.json \
  --output research/experiments/results/phase9_independent_oracle_audit.json
```

The validator checks schema integrity, duplicate IDs, sample size, category coverage, and agreement with the existing benchmark oracle. It does not alter the case labels.

## Claim boundary

A high agreement rate supports consistency between the independently assigned labels and the existing benchmark oracle on the sampled cases. It does not establish independent ground truth for the full Phase 8 dataset.

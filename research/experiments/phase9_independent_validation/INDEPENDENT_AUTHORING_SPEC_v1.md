# Phase 9 — Independent Authoring Specification v1

## Purpose

This document is the authoring brief for the Phase 9 Track A/B held-out sample. It defines the information needed to construct and label new scenarios without using Aegis implementation behavior, `aegisbench.oracle`, Phase 8 labels, or existing benchmark examples.

## Independence boundary

The authoring process is independent only when the person/process creating the cases has access to this specification, `INDEPENDENCE_PROTOCOL_v1.md`, `POLICY_CONTRACT_v1.md`, the documented tool/request contract, and the stateful contract, and has no access to implementation-derived labels or benchmark examples that reveal label conventions.

The currently generated 300-case synthetic audit is not this artifact. It remains a generator self-consistency check.

## Deliverable

Create exactly 300 newly authored scenarios in `independent_cases_v1.json`.

Every case must contain:

- `id`
- `category`
- `agent`
- `tool`
- `action`
- `parameters`
- `history`
- `expected_decision`
- `reason`
- `independent_labeler_version`

Use `history: []` for non-stateful cases.

Do not include `oracle_expected`, `oracle_reason`, `expected`, `parent_scenario_id`, or `mutation_operator`.

## Required categories

Use these category values because the Phase 9 validator checks coverage against the current held-out reference:

- `legitimate`
- `parameter_constraints`
- `identity_violation`
- `action_authorization`
- `path_constraints`
- `malformed`
- `unauthorized_tool`
- `stateful_sequence`

## Target stratification

Target 300 cases with deliberate oversampling of difficult boundaries:

| Category | Target |
|---|---:|
| legitimate | 40 |
| parameter_constraints | 55 |
| identity_violation | 45 |
| action_authorization | 40 |
| path_constraints | 40 |
| malformed | 55 |
| unauthorized_tool | 15 |
| stateful_sequence | 10 |
| **Total** | **300** |

These are targets, not labels. Cases should be newly authored rather than copied or renamed from the repository benchmark.

## Coverage requirements

### Legitimate

Include positive controls across each documented authorized surface and boundary-valid values.

### Parameter constraints

Oversample amount boundaries, currency boundaries, missing parameters, and wrong parameter types.

### Identity violations

Keep an otherwise valid request while changing the claimed agent so the identity mismatch is the policy-relevant reason.

### Action authorization

Use a known tool with an action that is not granted to the claimed agent.

### Path constraints

Include canonicalization and traversal boundaries, look-alike prefixes, sibling directories, and paths that become unauthorized after normalization.

### Malformed

Use malformed or mistyped parameter representations while keeping the scenario structurally representable as a benchmark case.

### Unauthorized tool

Use tools outside the declared authorization surface.

### Stateful sequence

Include full ordered histories. Cover valid creation-to-refund, missing creation, replay after refund, duplicate creation, wrong-transaction history, and unknown-event cases.

## Labeling rule

The labeler must determine `expected_decision` from `POLICY_CONTRACT_v1.md` alone. The `reason` field must be an ordinary-language rationale and must not imitate any oracle-specific reason vocabulary.

## Novelty rule

Do not copy existing benchmark requests. Do not derive cases by applying the repository's known mutation operators to existing benchmark scenarios. Vary values, paths, identifiers, combinations, and sequence histories while remaining inside the documented policy surface.

## Freeze procedure

Before oracle comparison:

1. finish all 300 cases;
2. review the file for prohibited fields;
3. verify every category is represented;
4. compute and record the file SHA-256;
5. commit the frozen case file;
6. only after the commit, run `validate_review.py`.

## Interpretation

Agreement with the benchmark oracle is an agreement/consistency measurement on this sample. It is not independent ground truth for the entire Phase 8 dataset and does not establish universal security or adversarial completeness.

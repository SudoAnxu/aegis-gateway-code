# Phase 9 — Final Validation Results

## Purpose

Phase 9 was added to audit two methodological risks in the frozen Phase 8 benchmark: oracle circularity and insufficient fault sensitivity. The Phase 8 benchmark, oracle, and results remain unchanged by the validation experiments.

## Methodological boundary

This project was conducted by a single researcher. Consequently, the contract-derived held-out labels in this phase are **not independent human ground truth**. We do not claim that they are.

Instead, the validation separates case construction/labeling from `aegisbench.oracle`: cases are generated from the standalone policy contract, labels are assigned by the standalone policy-contract labeler, the labeled artifact is frozen and hashed, and only afterward is the existing benchmark oracle run for comparison.

The later full-corpus cross-check uses a **second structurally independent policy oracle** with no imports from Aegis or `aegisbench`. It compares that oracle against the frozen benchmark labels across the complete 1,508-scenario expanded development + held-out corpus. This is a full-corpus implementation-consistency check, not independent human ground truth.

The earlier 300-case policy-contract consistency artifact is retained as a development/self-consistency check. Its 300/300 agreement with the oracle should not be presented as independent validation.

## Held-out validation set

The final held-out artifact contains exactly **300 cases** across all eight target categories:

| Category | Cases |
|---|---:|
| legitimate | 40 |
| action_authorization | 40 |
| identity_violation | 45 |
| parameter_constraints | 50 |
| path_constraints | 40 |
| malformed | 50 |
| stateful_sequence | 20 |
| unauthorized_tool | 15 |
| **Total** | **300** |

The unlabeled source was frozen before policy-contract labeling and had SHA-256:

`5bb1b183a582e12d52aa1806174c15aac5b1cc81de5d128118b258e4c9685984`

The final labeled artifact has SHA-256:

`82a88207b7d42db8584ffea22121894ae4b85e81e0c2b99a0069783a6408a750`

The frozen labeled cases contain no `oracle_expected` or `oracle_reason` fields before oracle comparison.

## Oracle comparison: held-out contract-derived sample

The frozen 300-case held-out set was compared against the existing `aegisbench.oracle` only after labeling and freezing.

Results:

- sample size: **300**
- agreement: **300/300 (100.0000%)**
- Cohen's kappa: **1.000000**
- disagreements: **0**

This supports consistency between the standalone policy-contract labeling procedure and the existing benchmark oracle on the sampled held-out cases. It does **not** establish that the oracle is objectively correct, nor does it establish independent ground truth for the full Phase 8 dataset.

## Full-corpus independent oracle cross-check

To strengthen the oracle-circularity audit, Phase 9 adds a second policy oracle, `independent_oracle_v2.py`. The implementation uses Python standard-library dependencies only and has no imports from Aegis or `aegisbench`. It uses a structurally different control flow from the existing oracle and returns only ALLOW/DENY decisions.

The cross-check runner loads the frozen expanded development and held-out corpora, verifies their content hashes, rejects duplicate scenario IDs across the two corpora, and compares Oracle V2 against the frozen benchmark expected labels. It does not import or execute `aegisbench.oracle`.

The two frozen source corpora contain:

| Corpus | Cases | SHA-256 |
|---|---:|---|
| `development_expanded_v1.json` | 951 | `5edc4213f043f2f36176712dcc156ae846d3954ce26ad38b1280a25a42b3c9b6` |
| `heldout_expanded_v1.json` | 557 | `61b2871cd20be10fcfc3d9124b0bbc68f7f5ab1ae178b66a98fc7309beab0e86` |
| **Total** | **1,508** | — |

Results:

- total scenarios: **1,508**
- agreement: **1,508/1,508 (100.000000%)**
- disagreements: **0**

This is stronger evidence than the 300-case audit for **full-corpus implementation consistency**: a separately implemented policy oracle reproduces every frozen benchmark label in the 1,508-scenario expanded corpus. It still does not establish independent human ground truth or prove that the shared policy interpretation is objectively correct.

The result is recorded in:

`research/experiments/results/phase9_full_oracle_crosscheck_v2.json`

## Earlier consistency check

The earlier 300-case development artifact also produced:

- agreement: **300/300 (100.0000%)**
- Cohen's kappa: **1.000000**
- disagreements: **0**

This result is retained as a policy-contract/generator self-consistency check and must not be described as independent human validation.

## Isolated mutation validation

Two targeted mutation operators were selected for Phase 9:

- **M21:** weaken identity/action authorization composition by treating the action predicate as satisfied.
- **M23:** fail open on state-enforcement errors.

Mutation execution uses detached Git worktrees so the normal checkout is not modified. The clean baseline passed both mutation sentinels before mutation. Both mutated variants then failed their corresponding sentinel tests:

| Mutant | Clean baseline | Mutated variant | Detected |
|---|---:|---:|---|
| M21 | PASS | FAIL | Yes |
| M23 | PASS | FAIL | Yes |
| **Total** | **2/2** | **0/2 surviving** | **2/2 detected** |

The mutation result should be described narrowly as detection of the **two selected fault operators**. It must not be described as complete security coverage or comprehensive mutation coverage.

## Regression status

The normal repository test suite passes after mutation-only sentinel tests were removed from the ordinary Go test suite:

```text
go test ./...
PASS
```

The mutation sentinels are injected by the isolated mutation runner rather than being permanent tests that intentionally fail on a clean checkout.

## Reproduction

Run the normal regression suite:

```bash
go test ./...
```

Re-run the held-out oracle comparison:

```bash
python research/experiments/phase9_independent_validation/validate_review.py \
  --cases research/experiments/phase9_independent_validation/contract_heldout_v2.json \
  --output /tmp/phase9_recheck.json
```

Re-run the earlier consistency comparison:

```bash
python research/experiments/phase9_independent_validation/validate_review.py \
  --cases research/experiments/phase9_independent_validation/independent_cases_v1.json \
  --output /tmp/phase9_consistency_recheck.json
```

Run the full-corpus independent-oracle cross-check:

```bash
python research/experiments/phase9_independent_validation/run_full_oracle_crosscheck_v2.py
```

Expected result:

```text
scenario_count: 1508
agreement: 1508/1508 (100.000000%)
disagreements: 0
```

Re-run the isolated mutation experiment:

```bash
python research/experiments/mutation_testing/run_phase9_isolated.py
```

## Claim boundaries

Phase 9 supports the following claims:

1. A 300-case contract-derived held-out sample was labeled independently of the existing benchmark oracle at the **software-procedure level**, then frozen before oracle comparison.
2. Those labels agreed perfectly with the existing oracle on the sampled cases.
3. A structurally independent second policy oracle reproduced all **1,508** frozen labels in the expanded development + held-out corpus.
4. Two specifically selected mutation operators were both detected in isolated execution.
5. The normal repository regression suite remains passing.

Phase 9 does **not** support these claims:

- independent human ground truth;
- proof of objective correctness of the policy interpretation;
- exhaustive validation of all 76,160 Phase 8 exported evaluation records as independent scenarios;
- complete security coverage;
- complete mutation coverage;
- broader security coverage merely from the two selected mutation operators.

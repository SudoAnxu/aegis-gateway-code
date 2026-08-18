# AegisBench Final Experimental Results

## 1. Scope

This document summarizes the completed Aegis governance experiments on the frozen AegisBench development and held-out suites, Phase 8 mutation testing, Phase 9 metamorphic testing, and the consolidated record-level evaluation export.

The results are benchmark-level measurements. They are not claims of universal security, adversarial completeness, or formal security guarantees.

## 2. Benchmark artifacts

### Development

- Curated seeds: 100
- Expanded scenarios: 951
- Expected decisions: 829 DENY, 122 ALLOW
- Expanded benchmark SHA-256: `5edc4213f043f2f36176712dcc156ae846d3954ce26ad38b1280a25a42b3c9b6`
- Expanded categories: legitimate 131; identity_violation 158; action_authorization 175; parameter_constraints 247; path_constraints 104; malformed 64; unauthorized_tool 7; stateful_sequence 65.

### Held-out

- Curated seeds: 50
- Expanded scenarios: 557
- Expected decisions: 457 DENY, 100 ALLOW
- Expanded benchmark SHA-256: `61b2871cd20be10fcfc3d9124b0bbc68f7f5ab1ae178b66a98fc7309beab0e86`

### Static held-out benchmark used for the final B0/B1/B2 evaluation

- Scenarios: 522
- Version: `1.0-static`
- SHA-256: `17865ea0648f234efa0d777f71b6ceb802ee89bbdab66dd064f3d557b0c6173c`
- Repetitions: 30 per system

## 3. Held-out B0/B1/B2 evaluation

All three systems were evaluated on the same 522-case static held-out benchmark for 30 repetitions.

| System | Precision | Recall | F1 | Unauthorized execution rate | Legitimate task success |
|---|---:|---:|---:|---:|---:|
| B0 Direct | 1.0000 | 0.3460 | 0.5141 | 0.6540 | 1.0000 |
| B1 RBAC | 1.0000 | 0.5450 | 0.7055 | 0.4550 | 1.0000 |
| B2 Aegis | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |

For B2, the measured result on this held-out suite was precision 1.0, recall 1.0, F1 1.0, zero unauthorized executions, and 1.0 legitimate-task success. Repetitions were used to demonstrate reproducibility of deterministic classifications and to characterize latency variability; they are not independent attack corpora.

### Latency

Mean latency across the 30 repetition-level summaries was approximately:

| System | Mean latency (ms) | Median / P50 (ms) | P95 (ms) | P99 (ms) |
|---|---:|---:|---:|---:|
| B0 Direct | 1.008 | 0.866 | 1.428 | 2.541 |
| B1 RBAC | 1.661 | 1.691 | 2.694 | 4.265 |
| B2 Aegis | 3.155 | 1.002 | 3.303 | 5.686 |

The B2 mean is influenced by higher-latency observations; the median/P50 is approximately 1 ms in the reported aggregate.

## 4. Phase 8 mutation testing

The mutation catalog contained 20 security-relevant mutants covering parameter, path, identity, action, validator, and state enforcement.

| ID | Mutation | Result |
|---|---|---|
| M01 | Remove minimum amount check | detected |
| M02 | Remove maximum amount check | detected |
| M03 | Ignore missing required parameters / fail-open | detected |
| M04 | Use raw string prefix matching for paths | detected |
| M05 | Disable path constraint enforcement | detected |
| M06 | Disable identity enforcement | detected |
| M07 | Permit unauthorized actions for known tools | detected |
| M08 | Permit unknown tools | detected |
| M09 | Treat unsupported parameter types as valid | detected |
| M10 | Skip path canonicalization and allow traversal | detected |
| M11 | Make currency comparison case-insensitive | detected |
| M12 | Introduce off-by-one maximum amount boundary | detected |
| M13 | Introduce off-by-one minimum amount boundary | detected |
| M14 | Disable duplicate-create state check | KILLED |
| M15 | Disable refund replay state check | KILLED |
| M16 | Allow refund without prior create | KILLED |
| M17 | Ignore transaction identity during state evaluation | KILLED |
| M18 | Allow malformed requests to proceed | detected |
| M19 | Allow identity substitution for file access | detected |
| M20 | Race-style state check/commit weakening | KILLED |

For the non-stateful mutation aggregates, reported F1 / unauthorized-execution-rate results were:

| ID | F1 | Unauthorized execution rate |
|---|---:|---:|
| M01 | 0.995708 | 0.008547 |
| M02 | 0.990136 | 0.019536 |
| M03 | 0.950000 | 0.095238 |
| M04 | 0.996938 | 0.006105 |
| M05 | 0.905080 | 0.173382 |
| M06 | 0.963291 | 0.070818 |
| M07 | 0.950673 | 0.094017 |
| M08 | 0.995708 | 0.008547 |
| M09 | 0.893243 | 0.192918 |
| M10 | 0.996938 | 0.006105 |
| M11 | 0.990136 | 0.019536 |
| M12 | 0.989130 | 0.000000 |
| M13 | 0.992126 | 0.000000 |
| M18 | 0.993932 | 0.012063 |
| M19 | 0.988889 | 0.021978 |

The stateful runner reported M14, M15, M16, M17, and M20 as `KILLED`. In particular, the final M14 and M15 artifacts explicitly record `mutation_status: KILLED`, with replay-valid histories and DENY outcomes for the relevant terminal state checks.

## 5. Phase 9 metamorphic testing

The metamorphic suite defined three invariant relationships and two security-sensitive relationships.

| Transformation | Base | Expected | Observed | Result |
|---|---|---|---|---|
| INV01 — JSON field reordering | S080 | same | ALLOW -> ALLOW | PASS |
| INV02 — formatting/whitespace change | S080 | same | ALLOW -> ALLOW | PASS |
| INV03 — irrelevant-field addition | S080 | same | ALLOW -> ALLOW | PASS |
| SEC01 — payment amount 5000 -> 5001 | S080 | flip to DENY | ALLOW -> DENY | PASS |
| SEC02 — HR path traversal injection | S011 | flip to DENY | ALLOW -> DENY | PASS |

Result: **3/3 invariant pairs passed and 2/2 security-sensitive transformations passed.**

## 6. Consolidated evaluation record

The final experiments produced a consolidated record-level export:

`research/experiments/results/evaluation_records_final.csv`

It contains **75,860 recorded evaluations** across 125 JSON result files:

- Held-out final evaluations: 46,980 records
- Mutation final evaluations: 28,880 records
- B0 Direct: 15,660 records
- B1 RBAC: 15,660 records
- B2 Aegis: 44,540 records
- Transport errors: 0

The CSV contains 35 normalized fields and is generated by `research/experiments/build_evaluation_dataset.py`. It is a record-level experimental export, not 75,860 independent security scenarios; repeated executions of the same scenarios are included by design.

The record classifications are:

- true positive: 47,632
- false negative: 15,568
- true negative: 12,598
- false positive: 62
- stateful records without the standard decision fields: 650

## 7. Reproducibility

Final environment capture is stored in `research/experiments/reproducibility/environment.md`, with reproduction instructions in `research/experiments/reproducibility/REPRODUCE.md`.

Final recorded environment:

- Commit: `738fcec25d8afbf7abd5b244c31bbc5c583cceb6`
- OS: Ubuntu 24.04.4 LTS
- Architecture: x86_64
- CPU: 2 vCPUs
- RAM: 7.8 GiB
- Go: 1.26.1
- Python: 3.12.1
- Docker: 29.3.0
- Final static benchmark repetitions: 30
- Benchmark generation/execution uses deterministic transformations; no RNG seed is required for the benchmark/experiment implementation.

The final branch also contains the frozen benchmark splits, metamorphic runner and results, mutation results, held-out results, and consolidated evaluation export.

## 8. Interpretation and limitations

The strongest supported conclusion is that, on the frozen AegisBench development/held-out suites and under the documented experimental protocol, B2 Aegis produced the measured enforcement outcomes reported above, including perfect measured classification on the 522-case static held-out suite.

The results should not be interpreted as proof of universal security. The held-out suite is a deterministic generalization check over documented policy dimensions, and mutation testing evaluates the ability of the benchmark to expose specified classes of enforcement weakening. Repeated executions provide reproducibility and latency observations rather than independent attack corpora.

The consolidated CSV similarly represents repeated experimental observations rather than a corpus of 75,860 independent scenarios.

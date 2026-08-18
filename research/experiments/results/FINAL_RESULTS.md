# AegisBench Final Experimental Results

## 1. Scope

This document summarizes the completed Aegis governance experiments on the frozen AegisBench development and held-out suites, Phase 8 mutation testing, Phase 9 metamorphic testing, and the consolidated record-level evaluation export.

The results are benchmark-level measurements. They are not claims of universal security, adversarial completeness, or formal security guarantees.

## 2. Benchmark and experimental artifacts

### Expanded development benchmark

- Curated seeds: 100
- Expanded scenarios: 951
- Expected decisions: 829 DENY, 122 ALLOW
- Expanded benchmark SHA-256: `5edc4213f043f2f36176712dcc156ae846d3954ce26ad38b1280a25a42b3c9b6`
- Expanded categories: legitimate 131; identity_violation 158; action_authorization 175; parameter_constraints 247; path_constraints 104; malformed 64; unauthorized_tool 7; stateful_sequence 65.

### Static held-out benchmark used for B0/B1/B2

- Scenarios: 522
- Version: `1.0-static`
- SHA-256: `17865ea0648f234efa0d777f71b6ceb802ee89bbdab66dd064f3d557b0c6173c`
- Repetitions: 30 per system
- Evaluations per system: 15,660
- Total held-out evaluations: 46,980

### Clean mutation baseline

- Expanded scenarios: 951
- Repetitions: 30
- Evaluations: 28,530
- Purpose: reference B2 behavior for mutation deltas and detection analysis.

### Mutation benchmark

- Ordinary request/policy mutants: 15
- Stateful mutants: 5
- Ordinary mutant evaluations: 15 × 1,902 = 28,530
- Stateful mutant evaluations: 5 × 130 = 650
- Total mutation evaluations: 29,180

Stateful mutants use a dedicated sequence runner because their behavior depends on ordered payment histories rather than isolated requests. The stateful runner passes the mutation ID to B2 through `X-Aegis-Mutant-ID`, while the resulting artifact stores the mutation identity and status at the artifact level.

## 3. Experimental systems

The baseline configuration defines three systems:

- **B0 Direct:** requests are sent directly to controlled tool fixtures without a governance gateway; parameter and path constraints are disabled at the governance layer.
- **B1 RBAC:** coarse-grained authorization based on agent, tool, and action; parameter- and path-level constraints are intentionally not enforced.
- **B2 Aegis:** requests are evaluated by the Aegis policy gateway before reaching the controlled tool fixtures.

B0 is therefore a **direct-execution baseline**, not an idealized system that is guaranteed to return ALLOW for every request. Its requests are sent directly to controlled fixtures, and the configured direct fallback is explicitly a permissive fixture for tools without a dedicated service.

This distinction matters when interpreting B0's nonzero true-positive count: B0's measured rejections should not be described as evidence of Aegis-like policy enforcement, nor should B0 be described as an unconditional-ALLOW oracle.

## 4. Held-out B0/B1/B2 evaluation

All three systems were evaluated on the same 522-case static held-out benchmark for 30 repetitions.

| System | N | TP | TN | FP | FN | Precision | Recall | F1 | Accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 Direct | 15,660 | 4,380 | 3,000 | 0 | 8,280 | 1.0000 | 0.3460 | 0.5141 | 0.4713 |
| B1 RBAC | 15,660 | 6,900 | 3,000 | 0 | 5,760 | 1.0000 | 0.5450 | 0.7055 | 0.6322 |
| B2 Aegis | 15,660 | 12,660 | 3,000 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

For B2, the measured result on this held-out suite was precision 1.0, recall 1.0, F1 1.0, zero unauthorized executions, and 1.0 legitimate-task success.

For the held-out suite, the unauthorized-execution rates were 0.6540 for B0, 0.4550 for B1, and 0.0000 for B2. Legitimate-task success was 1.0 for all three systems.

The 30 repetitions demonstrate reproducibility of the observed classifications and characterize latency variability; they are not 30 independent attack corpora.

## 5. Phase 8 mutation testing

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

### Ordinary mutation results

| ID | N | TP | TN | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M01 | 1902 | 1644 | 244 | 0 | 14 | 1.0000 | 0.9916 | 0.9958 |
| M02 | 1902 | 1626 | 244 | 0 | 32 | 1.0000 | 0.9807 | 0.9903 |
| M03 | 1902 | 1502 | 244 | 0 | 156 | 1.0000 | 0.9059 | 0.9506 |
| M04 | 1902 | 1648 | 244 | 0 | 10 | 1.0000 | 0.9940 | 0.9970 |
| M05 | 1902 | 1374 | 244 | 0 | 284 | 1.0000 | 0.8287 | 0.9063 |
| M06 | 1902 | 1542 | 244 | 0 | 116 | 1.0000 | 0.9300 | 0.9637 |
| M07 | 1902 | 1504 | 244 | 0 | 154 | 1.0000 | 0.9071 | 0.9513 |
| M08 | 1902 | 1644 | 244 | 0 | 14 | 1.0000 | 0.9916 | 0.9958 |
| M09 | 1902 | 1342 | 244 | 0 | 316 | 1.0000 | 0.8094 | 0.8947 |
| M10 | 1902 | 1648 | 244 | 0 | 10 | 1.0000 | 0.9940 | 0.9970 |
| M11 | 1902 | 1626 | 244 | 0 | 32 | 1.0000 | 0.9807 | 0.9903 |
| M12 | 1902 | 1658 | 208 | 36 | 0 | 0.9787 | 1.0000 | 0.9893 |
| M13 | 1902 | 1658 | 218 | 26 | 0 | 0.9846 | 1.0000 | 0.9922 |
| M18 | 1902 | 1638 | 244 | 0 | 20 | 1.0000 | 0.9879 | 0.9939 |
| M19 | 1902 | 1622 | 244 | 0 | 36 | 1.0000 | 0.9783 | 0.9890 |

M12 and M13 are the only ordinary mutants with nonzero false-positive counts. These are boundary-condition mutations: changing a threshold by one unit can alter the treatment of requests exactly at the decision boundary, so their error pattern differs from the predominantly fail-open mutations that convert expected DENY outcomes into ALLOW outcomes.

### Stateful mutation results

| ID | N | TP | TN | FP | FN | F1 | History-replay failures | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| M14 | 130 | 78 | 0 | 0 | 52 | 0.7500 | 32 | KILLED |
| M15 | 130 | 62 | 0 | 0 | 68 | 0.6458 | 6 | KILLED |
| M16 | 130 | 26 | 0 | 0 | 104 | 0.3333 | 10 | KILLED |
| M17 | 130 | 129 | 0 | 0 | 1 | 0.9961 | 67 | KILLED |
| M20 | 130 | 0 | 0 | 0 | 130 | 0.0000 | 48 | KILLED |

All five stateful mutants were killed. The stateful mutation criterion treats any false positive, false negative, history-replay failure, or transport/unclassified error as evidence that the mutation did not preserve the required stateful behavior; transport errors and unclassified records instead cause an `ERROR` status. This criterion is implemented in `run_mutations.py`.

## 6. M14/M15 investigation and resolution

An interim mutation-detection result initially appeared to leave M14 and M15 unresolved. This was an **analysis/reporting coverage issue, not evidence that the mutants survived**.

The original mutation-detection logic inspected only `*/b2_aegis_aggregate.json`. Stateful mutants do not produce that artifact; they produce `*/b2_aegis_stateful.json`. Consequently, the first detection report omitted the five stateful mutants from its discovery pass even though the stateful runner had executed them.

The mutation-detection implementation was subsequently extended to process both ordinary aggregate artifacts and stateful artifacts. Stateful detection uses the authoritative `mutation_status` written by the stateful mutation runner. The final detection report contains all 20 mutants and reports 20/20 detected with zero survivors.

This distinction is important: **the earlier 18/20 detection result was caused by the detector not discovering stateful result files; it was not a recorded SURVIVED status being silently changed to KILLED.** The stateful runner had already produced dedicated artifacts for M14-M20.

The individual M14/M15 records corroborate genuine mutated behavior. M14 contains false negatives on duplicate-create cases and history-replay failures; M15 contains false negatives on replay-related cases and a history-replay failure. The mutation identity is stored at the artifact level (`mutant_id`) rather than duplicated into every record.

## 7. Phase 9 metamorphic testing

The metamorphic suite defined three invariant relationships and two security-sensitive relationships.

| Transformation | Base | Expected | Observed | Result |
|---|---|---|---|---|
| INV01 — JSON field reordering | S080 | same | ALLOW -> ALLOW | PASS |
| INV02 — formatting/whitespace change | S080 | same | ALLOW -> ALLOW | PASS |
| INV03 — irrelevant-field addition | S080 | same | ALLOW -> ALLOW | PASS |
| SEC01 — payment amount 5000 -> 5001 | S080 | flip to DENY | ALLOW -> DENY | PASS |
| SEC02 — HR path traversal injection | S011 | flip to DENY | ALLOW -> DENY | PASS |

Result: **3/3 invariant pairs passed and 2/2 security-sensitive transformations passed.**

## 8. Consolidated evaluation record

The final experiments produced a consolidated record-level export:

`research/experiments/results/evaluation_records_final.csv`

It contains **76,160 recorded evaluations** across the final held-out and mutation result artifacts:

- Held-out final evaluations: 46,980 records
- Mutation final evaluations: 29,180 records
- B0 Direct: 15,660 records
- B1 RBAC: 15,660 records
- B2 Aegis: 44,840 records
- Transport errors: 0
- Unclassified records: 0

The CSV contains 35 normalized fields and is generated by `research/experiments/build_evaluation_dataset.py`. It is a record-level experimental export, not 76,160 independent security scenarios; repeated executions of the same scenarios are included by design.

The final record classifications are:

- true positive: 47,911
- false negative: 15,589
- true negative: 12,598
- false positive: 62

Expected decisions include 650 stateful records whose standard `expected_decision` field is blank because stateful sequence evaluation uses sequence-level expected/actual fields. These records are nevertheless classified, so the final export has zero unclassified records.

## 9. Reproducibility and integrity checks

The final artifact set includes the frozen benchmark splits, held-out results, metamorphic results, mutation results, mutation-detection report, consolidated evaluation export, and final machine-readable summary.

Integrity checks completed for the final export include:

- 76,160 records
- 35 columns
- 46,980 held-out records
- 29,180 mutation records
- 20/20 mutants detected
- 0 surviving mutants
- 0 transport errors
- 0 unclassified records
- unique record IDs
- mutation-count integrity checks passed
- JSON parse validation passed for `final_results.json`
- `git diff --check` passed after the final artifact generation

The clean B2 mutation baseline contains 30 × 951 = 28,530 valid records with zero transport errors and zero unclassified records.

## 10. Interpretation and limitations

The strongest supported conclusion is that, on the frozen AegisBench suites and under the documented experimental protocol, B2 Aegis produced the measured enforcement outcomes reported above, including perfect measured classification on the 522-case static held-out suite and detection of all 20 specified security-relevant mutations.

These results do **not** establish universal security, formal security guarantees, or completeness against unspecified attack classes. The held-out suite is a deterministic generalization check over documented policy dimensions. Mutation testing measures the benchmark's ability to expose the specified mutation operators; it does not prove that all possible implementation defects would be detected.

The B0 result should not be interpreted as a pure unconditional-ALLOW control. It measures direct execution against the controlled fixtures without the Aegis governance gateway, so fixture/API behavior remains part of the observed baseline.

The mutation results should likewise not be interpreted solely through aggregate F1. The stateful mutants use sequence-specific correctness criteria, and the ordinary and stateful mutation sample sizes differ by design.

Repeated executions demonstrate reproducibility and provide latency observations; they are not independent attack corpora.

## 11. Claims to avoid

The following stronger claims are not supported by this experiment and should not appear in the abstract or paper without additional evidence:

- "Aegis is universally secure."
- "Aegis blocks all attacks."
- "Aegis is formally verified."
- "Aegis has zero false positives/negatives in real-world deployment."
- "The 76,160 records represent 76,160 independent attacks."
- "100% mutation detection proves complete vulnerability detection."
- "B0 has no validation whatsoever."

The defensible wording is that Aegis achieved the **measured** results on the frozen benchmark and that the benchmark detected all 20 specified mutations under the documented mutation-testing protocol.

## 12. Paper-ready results paragraph

On the frozen 522-scenario static held-out suite, evaluated for 30 repetitions per system, B2 Aegis achieved precision, recall, F1, and accuracy of 1.0000, with zero measured unauthorized executions and full legitimate-task success. The direct-execution and coarse-grained RBAC baselines achieved F1 scores of 0.5141 and 0.7055, respectively. In Phase 8 mutation testing, all 20 specified security-relevant mutants were detected, including five stateful mutations evaluated with sequence-aware state checks. The consolidated experimental export contains 76,160 records with zero transport errors and zero unclassified records. These results demonstrate benchmark-level enforcement and mutation-detection performance under the specified protocol; they do not constitute a claim of universal security or completeness against unspecified attacks.

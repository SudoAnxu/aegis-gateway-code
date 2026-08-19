# AegisBench Methodology Audit

## Purpose

This audit evaluates whether the final experimental results support the
claims made in FINAL_RESULTS.md. It is intentionally performed after the
experiment freeze and before paper drafting.

The audit distinguishes:
- implementation correctness,
- benchmark correctness,
- experimental validity,
- and scope of the resulting claims.

## Pre-audit predictions

These predictions are recorded before the evidence review.

### RQ5 — Leakage / circularity

Prediction:

The benchmark, oracle, and mutation catalog were at least partially designed
with knowledge of the Aegis implementation. Therefore some structural
circularity risk is expected.

Expected consequence:

This should be reported as a limitation unless the repository history shows
meaningful implementation-independent construction.

### RQ7 — Meaning of "held-out"

Prediction:

The 522-case held-out benchmark is likely disjoint from the development
records, but may share seed templates, generation logic, oracle logic, or
mutation operators with the development benchmark.

Expected consequence:

"held-out" may need to be qualified as a held-out evaluation suite rather
than implying independently authored or adversarially constructed cases.

### RQ3a — Mutation diversity

Prediction:

The 20 mutants probably cover several distinct enforcement mechanisms, but
some may be closely related and therefore not constitute 20 independent
fault classes.

Expected consequence:

Mutation detection rate should not be interpreted as a probability of
detecting arbitrary implementation bugs.

### RQ3b — Missing fault classes

Prediction:

There are likely plausible authorization-gateway faults not represented
by the 20 declared mutants, particularly parser/deserialization faults and
composite-policy logic errors.

Expected consequence:

The mutation result should be described as 100% detection of the specified
mutation catalog, not 100% coverage of possible security bugs.

### RQ2 — Baseline fairness

Prediction:

B0 and B1 are intentionally weaker baselines, so the comparison is useful
for measuring incremental enforcement capability, but they are not
necessarily matched controls for every architectural property.

Expected consequence:

Claims should remain comparative and benchmark-scoped.

### RQ4 — Stateful mutation validity

Prediction:

The stateful runner provides a meaningful sequence-aware evaluation, but
the smaller sample size and the mutation-specific sequence construction
need to be examined for coverage and possible coupling to the implementation.

### RQ1 — Held-out evaluation credibility

Prediction:

The held-out result is internally reproducible and statistically large in
record count, but the effective independence of the 522 scenarios depends
on how those scenarios were authored/generated.

### M14/M15 provenance

Prediction:

The raw M14/M15 stateful artifacts existed before the reporting fix and
should be byte-identical across the relevant commits. If confirmed, the
18/20 -> 20/20 discrepancy is demonstrably a reporting-discovery issue
rather than an experimental rerun.

## Evidence

To be completed after the predictions above were recorded.


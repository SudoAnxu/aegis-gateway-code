# Phase 8 — Mutation Testing

This directory defines the mutation-test harness. Mutants must be applied as isolated, reversible configuration/build variants of B2; the clean B2 implementation and frozen benchmark remain unchanged.

Acceptance target from the implementation plan: detect at least 80% of realistic mutants. An undetected mutant is a research finding and must be documented rather than hidden by changing the benchmark.

Required output:

```text
research/experiments/results/mutation_detection.csv
```

with columns:

```text
mutant_id,description,detected,scenario_ids_that_caught_it,f1_delta_vs_b2
```

# Mutation Testing

This directory defines the mutation-test harness. Mutants must be applied as isolated, reversible configuration/build variants of B2; the clean B2 implementation and frozen benchmark remain unchanged.

The original catalog harness remains the Phase 8 planning/reporting path. For the two Phase 9 follow-up mutants, use `run_phase9_isolated.py`. It copies the repository to a temporary directory, verifies the existing guarded mutation applicator can modify only that copy, and runs clean-semantics sentinel tests against the mutated build. No tracked source under `internal/` is modified by the Phase 9 run.

## Phase 9 follow-up mutants

- **M21:** weaken identity/action authorization composition by treating the action predicate as satisfied.
- **M23:** fail open on state-enforcement errors.

The acceptance criterion for this follow-up is detection of both selected realistic mutants. A survivor is a research finding and must be documented rather than hidden by changing the benchmark.

Run from the repository root:

```bash
python research/experiments/mutation_testing/run_phase9_isolated.py
```

The runner must report a clean baseline pass followed by detection of both mutants. It uses a temporary copy and removes that copy automatically on exit.

## Existing catalog output

The broader mutation catalog uses:

```text
research/experiments/results/mutation_detection.csv
```

with columns:

```text
mutant_id,description,detected,scenario_ids_that_caught_it,f1_delta_vs_b2
```

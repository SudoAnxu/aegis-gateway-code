# AegisBench Reproduction Record

## Repository

Commit:
`738fcec25d8afbf7abd5b244c31bbc5c583cceb6`

Final reproducibility metadata:
`research/experiments/reproducibility/environment.md`

## Frozen benchmarks

Development static:
`research/aegisbench/splits/development_static_v1.json`

SHA-256:
`3f9f3843f97551e8adb2aa257f68b13a7439f12f6aa6eff0d897171aa70c0d77`

Held-out static:
`research/aegisbench/splits/heldout_static_v1.json`

SHA-256:
`17865ea0648f234efa0d777f71b6ceb802ee89bbdab66dd064f3d557b0c6173c`

## Validation

```bash
python research/aegisbench/validate_expanded.py \
  --seeds research/aegisbench/splits/development_v1.json \
  research/aegisbench/splits/development_expanded_v1.json

python research/aegisbench/validate_expanded.py \
  --seeds research/aegisbench/splits/heldout_v1.json \
  research/aegisbench/splits/heldout_expanded_v1.json
```

## Held-out B0/B1/B2

```bash
python research/experiments/run_repeated.py \
  --system B0_direct \
  --benchmark research/aegisbench/splits/heldout_static_v1.json \
  --repetitions 30 \
  --output-dir research/experiments/results/heldout_final/b0_direct

python research/experiments/run_repeated.py \
  --system B1_rbac \
  --benchmark research/aegisbench/splits/heldout_static_v1.json \
  --repetitions 30 \
  --output-dir research/experiments/results/heldout_final/b1_rbac

python research/experiments/run_repeated.py \
  --system B2_aegis \
  --benchmark research/aegisbench/splits/heldout_static_v1.json \
  --repetitions 30 \
  --output-dir research/experiments/results/heldout_final/b2_aegis
```

## Stateful evaluation

```bash
python research/aegisbench/stateful_runner.py \
  --system B2_aegis \
  --benchmark research/aegisbench/splits/development_expanded_v1.json \
  --repetitions 2 \
  --output research/experiments/results/stateful_clean_final/b2_aegis_stateful.json
```

## Mutation testing

```bash
python research/experiments/run_mutations.py \
  --catalog research/experiments/mutation_testing/mutants.json \
  --benchmark research/aegisbench/splits/development_expanded_v1.json \
  --output-root research/experiments/results/mutations_final \
  --repetitions 2
```

## Metamorphic testing

```bash
python research/experiments/metamorphic/run_metamorphic.py
```

## Final evidence

Held-out B2:

* 522 scenarios
* 30 repetitions
* Precision: 1.000
* Recall: 1.000
* F1: 1.000
* Unauthorized execution rate: 0.000
* Legitimate task success rate: 1.000

Metamorphic:

* Invariant relationships: 3/3 passed
* Security-sensitive relationships: 2/2 passed

Mutation testing:

* Declared mutants: 20
* Detected: 18
* Undetected: 2
* Detection rate: 90%

## Scope

These results are benchmark-level enforcement results. They are not a claim of universal or formally proven security.

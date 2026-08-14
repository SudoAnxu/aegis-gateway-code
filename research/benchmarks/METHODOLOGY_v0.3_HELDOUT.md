# v0.3 Held-Out Evaluation Methodology

## Purpose

The v0.3 core benchmark contains policy-relevant seed scenarios and deterministic mutations. The held-out suite is a separate evaluation set intended to test whether the gateway generalizes beyond the exact request combinations represented in the core benchmark.

This distinction matters: repeated execution of a fixed benchmark measures reproducibility and latency stability, but it does not establish generalization to unseen requests.

## Construction

`generate_heldout_v0_3.py` constructs a deterministic 46-scenario suite from an over-provisioned candidate pool. Candidates are filtered by exact request fingerprint against `benchmark_v0.3.json`, and exact duplicates are removed before the target counts are selected. The generator fails if any category cannot reach its target after those exclusions, and performs a final zero-overlap assertion before writing the artifact.

The held-out suite contains:

| Category | Cases |
|---|---:|
| Legitimate | 9 |
| Parameter violation | 9 |
| Unauthorized action | 9 |
| Identity violation | 8 |
| Path violation | 5 |
| Unauthorized tool | 3 |
| Malformed | 3 |
| **Total** | **46** |

The candidate pool is intentionally larger than 46 so that overlap with the core benchmark does not require weakening the held-out design or silently accepting duplicate requests.

## Important limitation

The held-out suite is **not** a claim of adversarial completeness. It is a deterministic generalization check over policy dimensions represented by the repository's documented gateway rules. It should not be described as proof of security against arbitrary attacks.

## Experimental protocol

For each system:

- B0: direct execution
- B1: coarse-grained RBAC
- B2: Aegis policy gateway

run the same held-out scenarios for the same number of repetitions used for the core benchmark. Record the benchmark hash in every result and reject any run with an unexpected benchmark version/hash, transport errors, or unclassified scenarios.

Security metrics are computed over scenario classifications. Repeated executions demonstrate reproducibility of those classifications; they are not treated as independent attack scenarios. Latency statistics are aggregated across repetitions because latency is variable.

## Reporting guidance

Report core and held-out results separately. The strongest defensible claim is that Aegis achieved the measured enforcement result on the evaluated core and held-out suites. Do not generalize a perfect score into a claim of universal or formally proven security.

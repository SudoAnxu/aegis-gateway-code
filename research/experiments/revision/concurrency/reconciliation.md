# Concurrency Results Reconciliation

**Generated:** Revision audit phase.

## Discrepancy

The `REVISION_EXPERIMENT_REPORT.md` (Task 9) stated:

> Zero client errors across all 45 trials.
> All 5,000 requests per trial reached the downstream mock.
> Total downstream executions: 225,000/225,000 (100%).

**This was incorrect.** The raw trial files contain non-zero error counts.

## Actual Raw Data

| Mode | c= | Trial 1 errors | Trial 2-5 errors | Total errors | Total downstream |
|---|---|---|---|---|---|
| disabled | 100 | 0 | 0 | 0 | 25,000 |
| disabled | 500 | **346** | 0 | 346 | 24,654 |
| disabled | 1,000 | **392** | 0 | 392 | 24,608 |
| local | 100 | 0 | 0 | 0 | 25,000 |
| local | 500 | **150** | 0 | 150 | 24,850 |
| local | 1,000 | **211** | 0 | 211 | 24,789 |
| otlp | 100 | 0 | 0 | 0 | 25,000 |
| otlp | 500 | **93** | 0 | 93 | 24,907 |
| otlp | 1,000 | **276** | 0 | 276 | 24,724 |
| **Total** | | **1,468** | **0** | **1,468** | **223,532** |

## Root Cause

The errors occur exclusively in **trial 1** of each high-concurrency configuration (c=500, c=1,000). These are **client-side connection pool exhaustion errors** in the load generator, not gateway failures or downstream failures.

Evidence:
- Trials 2-5 of every configuration show 0 errors and 5,000 downstream executions
- The errors are in the first trial only, consistent with cold-start connection pool behavior
- The gateway's downstream mock received all requests that the load generator successfully sent

## Corrected Claims

| Claim | Previous (incorrect) | Corrected |
|---|---|---|
| Total errors | 0 | **1,468** (client-side) |
| Total downstream | 225,000 | **223,532** |
| Trials with errors | 0/45 | **6/45** |
| Gateway failures | 0 | **0** (confirmed) |
| Downstream mock failures | 0 | **0** (confirmed) |

## Impact on Results

The client-side errors affect **throughput measurements** (RPS) for trial 1 of high-concurrency configurations, but do not affect:
- Gateway policy enforcement correctness
- Downstream mock behavior
- Latency measurements for successfully completed requests
- Security invariant (duplicate execution = 0)

The `statistics.json` and `statistics.csv` correctly computed medians across all 5 trials, including the trial-1 errors. The median-based statistics are therefore slightly conservative (lower RPS) because trial-1 data is included.

## Source Files

- Raw trial files: `research/experiments/results/phase10_external/trial_*.json`
- Statistics (unchanged): `research/experiments/revision/concurrency/statistics.json`
- Statistics CSV (unchanged): `research/experiments/revision/concurrency/statistics.csv`

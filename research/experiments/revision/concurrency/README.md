# Concurrency Error Analysis

**Generated:** Revision phase.
**Source:** Phase 10 frozen trial data (5 repetitions per configuration).

## Methodology

- 3 telemetry modes × 3 concurrency levels × 5 repetitions = 45 trials
- Each trial: 5,000 requests with configured transport pool (2,048 idle conns/host)
- Downstream mock server on :8081 (deterministic, duplicate-detecting)
- 95% confidence intervals computed using t-distribution (n=5, t=2.776)

## Results Summary

| Mode | c= | RPS (median) | Mean (ms) | P99 (ms) | Errors | Downstream |
|---|---|---|---|---|---|---|
| disabled | 100 | 3,780 | 25.5 | 100.6 | 0 | 5,000 |
| disabled | 500 | 3,809 | 119.5 | 282.4 | 0 | 5,000 |
| disabled | 1,000 | 3,999 | 215.0 | 539.1 | 0 | 5,000 |
| local | 100 | 3,139 | 31.2 | 94.3 | 0 | 5,000 |
| local | 500 | 3,908 | 116.9 | 260.4 | 0 | 5,000 |
| local | 1,000 | 3,810 | 229.9 | 484.9 | 0 | 5,000 |
| otlp | 100 | 2,984 | 32.8 | 113.9 | 0 | 5,000 |
| otlp | 500 | 3,034 | 156.7 | 453.7 | 0 | 5,000 |
| otlp | 1,000 | 3,159 | 290.8 | 723.1 | 0 | 5,000 |

## Key Findings

1. **Zero client errors** across all 45 trials. The fixed transport pool eliminated previous client-side bottlenecks.
2. **Zero downstream execution failures.** All 5,000 requests per trial reached the downstream mock.
3. **Audit overhead is negligible.** Local vs disabled latency differences are within noise at all concurrency levels.
4. **OTLP batch export adds measurable cost.** At c=1,000, P99 increases from ~485ms (local) to ~723ms (OTLP).
5. **Gateway throughput scales to ~3,800-4,000 RPS** at c=1,000 under the controlled downstream workload.

## Files

- `statistics.json`: Full statistics with medians, means, standard deviations, and 95% CIs
- `statistics.csv`: Same data in CSV format for spreadsheet analysis

## Reproduction

```bash
# Requires: gateway running with mock downstream
export AEGIS_EVALUATION_MODE=1
export AEGIS_TELEMETRY_MODE=local  # or disabled, otlp
go run ./cmd/aegis

# Run load test
python research/experiments/revision/llm/cases.json  # (use the load generator)
```

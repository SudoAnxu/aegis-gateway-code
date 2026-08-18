# Metrics

`compute.py` is the Phase 6 metrics generator. It reads aggregate JSON result files and writes a deterministic CSV with security, utility, and latency metrics.

Example:

```bash
python research/experiments/metrics/compute.py \
  --results-root research/experiments/results \
  --output research/experiments/results/metrics.csv
```

The script does not hand-edit or recompute decisions; it is a pure projection of aggregate experiment artifacts.

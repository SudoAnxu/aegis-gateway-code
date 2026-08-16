#!/usr/bin/env python3
"""Generate paper-facing metrics from AegisBench aggregate JSON files."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

FIELDS = [
    "system", "benchmark_version", "benchmark_sha256", "scenario_count", "repetitions",
    "precision_mean", "precision_lower", "precision_upper",
    "recall_mean", "recall_lower", "recall_upper",
    "f1_mean", "f1_lower", "f1_upper",
    "unauthorized_execution_rate_mean", "legitimate_task_success_rate_mean",
    "latency_mean_ms", "latency_median_ms", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
]

def metric(summary: dict[str, Any], name: str, key: str) -> Any:
    return summary.get("metrics", {}).get(name, {}).get(key)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    aggregates = sorted(args.results_root.glob("**/*_aggregate.json"))
    if not aggregates:
        raise SystemExit(f"No aggregate JSON files found under {args.results_root}")

    rows: list[dict[str, Any]] = []
    for path in aggregates:
        data = json.loads(path.read_text(encoding="utf-8"))
        system = data.get("system")
        benchmark = data.get("benchmark", {})
        summary = data.get("summary", {})
        latency = summary.get("latency_ms", {})
        rows.append({
            "system": system,
            "benchmark_version": benchmark.get("version"),
            "benchmark_sha256": benchmark.get("sha256"),
            "scenario_count": benchmark.get("scenario_count"),
            "repetitions": data.get("repetitions"),
            "precision_mean": metric(summary, "precision", "mean"),
            "precision_lower": metric(summary, "precision", "lower"),
            "precision_upper": metric(summary, "precision", "upper"),
            "recall_mean": metric(summary, "recall", "mean"),
            "recall_lower": metric(summary, "recall", "lower"),
            "recall_upper": metric(summary, "recall", "upper"),
            "f1_mean": metric(summary, "f1", "mean"),
            "f1_lower": metric(summary, "f1", "lower"),
            "f1_upper": metric(summary, "f1", "upper"),
            "unauthorized_execution_rate_mean": metric(summary, "unauthorized_execution_rate", "mean"),
            "legitimate_task_success_rate_mean": metric(summary, "legitimate_task_success_rate", "mean"),
            "latency_mean_ms": latency.get("mean", {}).get("mean"),
            "latency_median_ms": latency.get("median", {}).get("mean"),
            "latency_p50_ms": latency.get("p50", {}).get("mean"),
            "latency_p95_ms": latency.get("p95", {}).get("mean"),
            "latency_p99_ms": latency.get("p99", {}).get("mean"),
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} metric rows to {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

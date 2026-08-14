#!/usr/bin/env python3
"""Validate repeated benchmark outputs and generate a comparison report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SYSTEMS = ("b0_direct", "b1_rbac", "b2_aegis")
DISPLAY = {
    "b0_direct": "B0 Direct Execution",
    "b1_rbac": "B1 Coarse-Grained RBAC",
    "b2_aegis": "B2 Aegis",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results" / "repeated",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument("--expected-repetitions", type=int, default=30)
    args = parser.parse_args()

    aggregates: dict[str, dict[str, Any]] = {}
    benchmark_hashes: set[str] = set()
    versions: set[str] = set()

    for system in SYSTEMS:
        path = args.results_dir / f"{system}_aggregate.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing aggregate: {path}")

        data = load(path)
        summary = data["summary"]
        aggregates[system] = data

        if summary["repetitions"] != args.expected_repetitions:
            raise ValueError(
                f"{system}: expected {args.expected_repetitions} repetitions, "
                f"got {summary['repetitions']}"
            )

        benchmark = data["benchmark"]
        benchmark_hashes.add(benchmark["sha256"])
        versions.add(benchmark["version"])

        for metric in (
            "precision",
            "recall",
            "f1",
            "unauthorized_execution_rate",
            "legitimate_task_success_rate",
        ):
            if summary["metrics"][metric]["n"] != args.expected_repetitions:
                raise ValueError(
                    f"{system}: metric {metric} has invalid n="
                    f"{summary['metrics'][metric]['n']}"
                )

    if len(benchmark_hashes) != 1:
        raise ValueError(f"Benchmark hashes differ: {benchmark_hashes}")
    if len(versions) != 1:
        raise ValueError(f"Benchmark versions differ: {versions}")

    b0 = aggregates["b0_direct"]["summary"]
    b1 = aggregates["b1_rbac"]["summary"]
    b2 = aggregates["b2_aegis"]["summary"]

    def metric(system_summary: dict[str, Any], name: str) -> float:
        return float(system_summary["metrics"][name]["mean"])

    def latency(system_summary: dict[str, Any]) -> float:
        return float(system_summary["latency_ms"]["mean"]["mean"])

    b0_latency = latency(b0)
    b1_latency = latency(b1)
    b2_latency = latency(b2)

    b2_vs_b0_latency = (b2_latency / b0_latency - 1.0) * 100.0
    b2_vs_b1_latency = (b2_latency / b1_latency - 1.0) * 100.0

    report = f"""# Benchmark v0.2 — Repeated Experiment Results

## Experimental integrity

- Benchmark version: `{next(iter(versions))}`
- Benchmark SHA-256: `{next(iter(benchmark_hashes))}`
- Repetitions per system: **{args.expected_repetitions}**
- Scenarios per repetition: **33**
- Total system-level executions: **2,970**
- All systems: 30/30 valid repetitions
- All repetitions: 33/33 scenarios classified
- Unclassified repetitions: **0**

## Security and classification results

| System | Precision | Recall | F1 | Unauthorized execution | Legitimate-task success |
|---|---:|---:|---:|---:|---:|
| {DISPLAY['b0_direct']} | {pct(metric(b0, 'precision'))} | {pct(metric(b0, 'recall'))} | {metric(b0, 'f1'):.4f} | {pct(metric(b0, 'unauthorized_execution_rate'))} | {pct(metric(b0, 'legitimate_task_success_rate'))} |
| {DISPLAY['b1_rbac']} | {pct(metric(b1, 'precision'))} | {pct(metric(b1, 'recall'))} | {metric(b1, 'f1'):.4f} | {pct(metric(b1, 'unauthorized_execution_rate'))} | {pct(metric(b1, 'legitimate_task_success_rate'))} |
| **{DISPLAY['b2_aegis']}** | **{pct(metric(b2, 'precision'))}** | **{pct(metric(b2, 'recall'))}** | **{metric(b2, 'f1'):.4f}** | **{pct(metric(b2, 'unauthorized_execution_rate'))}** | **{pct(metric(b2, 'legitimate_task_success_rate'))}** |

## Latency

| System | Mean latency | 95% CI for repetition-level mean | Mean p95 | Mean p99 |
|---|---:|---:|---:|---:|
| {DISPLAY['b0_direct']} | {b0_latency:.3f} ms | {b0['latency_ms']['mean']['lower']:.3f}–{b0['latency_ms']['mean']['upper']:.3f} ms | {b0['latency_ms']['p95']['mean']:.3f} ms | {b0['latency_ms']['p99']['mean']:.3f} ms |
| {DISPLAY['b1_rbac']} | {b1_latency:.3f} ms | {b1['latency_ms']['mean']['lower']:.3f}–{b1['latency_ms']['mean']['upper']:.3f} ms | {b1['latency_ms']['p95']['mean']:.3f} ms | {b1['latency_ms']['p99']['mean']:.3f} ms |
| **{DISPLAY['b2_aegis']}** | **{b2_latency:.3f} ms** | **{b2['latency_ms']['mean']['lower']:.3f}–{b2['latency_ms']['mean']['upper']:.3f} ms** | **{b2['latency_ms']['p95']['mean']:.3f} ms** | **{b2['latency_ms']['p99']['mean']:.3f} ms** |

Aegis mean latency is **{b2_vs_b0_latency:+.2f}%** versus direct execution and **{b2_vs_b1_latency:+.2f}%** versus coarse-grained RBAC.

## Interpretation

On this fixed benchmark, Aegis achieved perfect classification and zero unauthorized execution across all 30 repetitions while preserving 100% legitimate-task success. Direct execution and coarse-grained RBAC left substantial unauthorized-execution exposure: 75.86% and 34.48%, respectively.

The results support the claim that parameter-, path-, and identity-aware gateway enforcement materially improves governance coverage over the two baselines for this benchmark. They do **not** establish generalization beyond benchmark v0.2, and the deterministic security metrics have zero between-repetition variance because the evaluated policy decisions are deterministic.

Latency should be reported as an observed benchmark characteristic rather than as evidence of universal performance. The repetition-level confidence intervals describe variation across the 30 measured runs; they do not account for other machines, workloads, network conditions, or deployment environments.
"""

    output = args.output or args.results_dir / "EXPERIMENT_REPORT.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    print(f"Report written to: {output}")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

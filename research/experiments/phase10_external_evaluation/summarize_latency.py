#!/usr/bin/env python3
"""Build the paper-ready latency table from frozen Phase 10 artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def normalized_stats(data: dict) -> dict:
    stats = data["latency_ms"]
    # v1 local-command artifacts used flat keys. v2 HTTP artifacts store the
    # same statistics under latency_ms.all with explicit *_ms names.
    if "mean" in stats:
        return {
            "mean": stats["mean"],
            "p50": stats["p50"],
            "p95": stats["p95"],
            "p99": stats["p99"],
        }
    all_stats = stats["all"]
    return {
        "mean": all_stats["mean_ms"],
        "p50": all_stats["p50_ms"],
        "p95": all_stats["p95_ms"],
        "p99": all_stats["p99_ms"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="latency JSON artifacts")
    args = ap.parse_args()

    rows = []
    baseline = None
    for raw in args.files:
        p = Path(raw)
        data = json.loads(p.read_text(encoding="utf-8"))
        stats = normalized_stats(data)
        system = data["system"]
        if system == "b0":
            baseline = stats
        rows.append((system, data["sample_count"], stats))

    if baseline is None:
        raise SystemExit("at least one artifact with system=b0 is required")

    print("| System | Samples | Mean (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Overhead vs B0 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for system, n, stats in sorted(rows):
        overhead = "—"
        if system != "b0":
            overhead = f"{(stats['mean'] - baseline['mean']) / baseline['mean'] * 100:.2f}%"
        print(
            f"| {system.upper()} | {n} | {stats['mean']:.3f} | "
            f"{stats['p50']:.3f} | {stats['p95']:.3f} | "
            f"{stats['p99']:.3f} | {overhead} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

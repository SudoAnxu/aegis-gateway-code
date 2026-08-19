#!/usr/bin/env python3
"""Build the paper-ready latency table from frozen latency JSON artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="latency JSON artifacts")
    args = ap.parse_args()

    rows = []
    baseline = None
    for raw in args.files:
        p = Path(raw)
        data = json.loads(p.read_text(encoding="utf-8"))
        stats = data["latency_ms"]
        system = data["system"]
        if system == "b0":
            baseline = stats
        rows.append((system, data["sample_count"], stats))

    print("| System | Samples | Mean (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Overhead vs B0 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for system, n, stats in sorted(rows):
        overhead = "—"
        if baseline and system != "b0":
            overhead = f"{(stats['mean'] - baseline['mean']) / baseline['mean'] * 100:.2f}%"
        print(f"| {system.upper()} | {n} | {stats['mean']:.3f} | {stats['p50']:.3f} | {stats['p95']:.3f} | {stats['p99']:.3f} | {overhead} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

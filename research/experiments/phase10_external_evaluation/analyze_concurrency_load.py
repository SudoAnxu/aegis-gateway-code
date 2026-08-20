#!/usr/bin/env python3
"""Summarize Phase 10 concurrency/load-test results for paper reporting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.result).read_text(encoding="utf-8"))

    print("Phase 10 concurrency/load summary")
    print(f"protocol: {data.get('protocol')}")
    print("\nUnique-request workload")
    print("concurrency  requests  RPS       mean_ms   p50_ms    p95_ms    p99_ms    errors  downstream")
    for r in data.get("levels", []):
        print(
            f"{r['concurrency']:>11}  {r['requests']:>8}  "
            f"{r['throughput_rps']:>8.2f}  {r['mean_ms']:>8.2f}  "
            f"{r['p50_ms']:>8.2f}  {r['p95_ms']:>8.2f}  {r['p99_ms']:>8.2f}  "
            f"{r['request_errors']:>6}  {r['downstream_executed']:>10}"
        )

    races = data.get("duplicate_race", [])
    if races:
        print("\nDuplicate-race state-safety workload")
        print("concurrency  decisions                         downstream  safety_pass  errors")
        for r in races:
            print(
                f"{r['concurrency']:>11}  {str(r['decisions']):<34} "
                f"{r['downstream_executed']:>10}  {str(r['state_safety_pass']):>11}  {r['request_errors']:>6}"
            )
        failures = [r for r in races if not r.get("state_safety_pass")]
        print(f"duplicate-race safety failures: {len(failures)}/{len(races)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

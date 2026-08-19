#!/usr/bin/env python3
"""Latency benchmark scaffolding for B0/B1/B2.

This runner is intentionally provider-agnostic. It executes a command per
system/scenario and records wall-clock latency without modifying the frozen
Phase 8 artifacts. Use --command to provide the actual system invocation.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("no latency samples")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p / 100.0
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--system", required=True, choices=["b0", "b1", "b2", "opa"])
    ap.add_argument("--repetitions", type=int, default=30)
    ap.add_argument("--command", required=True, help="Shell command template; {case_json} is replaced with a temp JSON path")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = data.get("scenarios", data.get("cases", []))
    if not isinstance(cases, list):
        raise SystemExit("cases file must contain a scenarios/cases array")

    all_ms: list[float] = []
    rows = []
    tmp_dir = Path(args.output).resolve().parent / ".latency_cases"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        for rep in range(args.repetitions):
            for idx, case in enumerate(cases):
                case_path = tmp_dir / f"case_{idx}.json"
                case_path.write_text(json.dumps(case), encoding="utf-8")
                command = args.command.format(case_json=str(case_path))
                start = time.perf_counter_ns()
                completed = subprocess.run(command, shell=True, capture_output=True, text=True)
                elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
                all_ms.append(elapsed_ms)
                rows.append({
                    "system": args.system,
                    "repetition": rep,
                    "scenario_id": case.get("id", case.get("scenario_id")),
                    "latency_ms": elapsed_ms,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                })
    finally:
        for path in tmp_dir.glob("case_*.json"):
            path.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass

    report = {
        "protocol": "phase10-latency-v1",
        "system": args.system,
        "case_count": len(cases),
        "repetitions": args.repetitions,
        "sample_count": len(all_ms),
        "latency_ms": {
            "mean": statistics.fmean(all_ms),
            "p50": percentile(all_ms, 50),
            "p95": percentile(all_ms, 95),
            "p99": percentile(all_ms, 99),
        },
        "samples": rows,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["latency_ms"], indent=2, sort_keys=True))
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Summarize Aegis decision and forwarding timings from a controlled run.

Run Aegis with AEGIS_FORWARD_TIMING_LOG=1 and clear its log before the run.
DecisionLog latency is the gateway's pre-forward decision path. ForwardLog
latency is the downstream tool HTTP path. The script intentionally reports
these as separate measurements rather than subtracting unrelated samples.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def pct(values: list[int], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    rank = (len(xs) - 1) * p / 100
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (rank - lo)


def stats(values: list[int]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values) if values else None,
        "p50_ms": pct(values, 50),
        "p95_ms": pct(values, 95),
        "p99_ms": pct(values, 99),
        "min_ms": min(values) if values else None,
        "max_ms": max(values) if values else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="logs/aegis.log")
    ap.add_argument("--expected-decisions", type=int, default=8400)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    decisions: list[dict[str, Any]] = []
    forwards: list[dict[str, Any]] = []
    for line in Path(args.log).read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") == "tool.forward":
            forwards.append(row)
        elif "decision.allow" in row and "latency.ms" in row:
            decisions.append(row)

    decision_all = [int(x["latency.ms"]) for x in decisions]
    decision_allow = [int(x["latency.ms"]) for x in decisions if str(x.get("decision.allow")).lower() == "true"]
    decision_deny = [int(x["latency.ms"]) for x in decisions if str(x.get("decision.allow")).lower() == "false"]
    forward_all = [int(x["latency.ms"]) for x in forwards]

    report = {
        "protocol": "phase10-gateway-timing-decomposition-v1",
        "log": args.log,
        "expected_decision_records": args.expected_decisions,
        "decision_records": len(decisions),
        "forward_records": len(forwards),
        "decision_record_complete": len(decisions) == args.expected_decisions,
        "decision_latency_ms": {
            "all": stats(decision_all),
            "allow": stats(decision_allow),
            "deny": stats(decision_deny),
        },
        "forward_latency_ms": stats(forward_all),
        "note": "Decision latency is gateway pre-forward work as instrumented by policy.evaluate; forward latency is downstream tool HTTP work as instrumented by tool.forward. They are not subtracted from client wall-clock samples because the log entries are independently timed.",
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

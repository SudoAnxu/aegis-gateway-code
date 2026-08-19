#!/usr/bin/env python3
"""Controlled HTTP latency benchmark for Phase 10 gateway/baseline systems.

The same benchmark driver is used for B0, B1, and B2/Aegis. It measures only
request/response wall-clock time, uses the same frozen corpus and HTTP contract,
performs warm-up requests, and records every sample. It never modifies the
benchmark corpus.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p / 100.0
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    fraction = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * fraction


def summarize(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values) if values else None,
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "p99_ms": percentile(values, 99),
        "min_ms": min(values) if values else None,
        "max_ms": max(values) if values else None,
    }


def load_cases(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = data.get("scenarios", data.get("cases", []))
    if not isinstance(cases, list) or not cases:
        raise SystemExit("cases file must contain a non-empty scenarios/cases array")
    return cases


def request_gateway(*, base_url: str, case: dict[str, Any], timeout: float) -> tuple[float, str, int, bool]:
    agent = case.get("agent")
    tool = case.get("tool")
    action = case.get("action")
    parameters = case.get("parameters", {})
    if not all(isinstance(value, str) and value for value in (agent, tool, action)):
        raise ValueError(f"Invalid case {case.get('id')}: agent/tool/action must be non-empty strings")
    if not isinstance(parameters, dict):
        raise ValueError(f"Invalid case {case.get('id')}: parameters must be an object")

    url = f"{base_url.rstrip('/')}/tools/{tool}/{action}"
    request = urllib.request.Request(
        url,
        data=json.dumps(parameters, separators=(",", ":")).encode("utf-8"),
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("X-Agent-ID", agent)
    request.add_header("User-Agent", "aegis-phase10-latency-benchmark/1.1")

    start = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
            decision = response.headers.get("X-Aegis-Gateway-Decision", "ALLOW").upper()
            return elapsed_ms, decision, response.status, True
    except urllib.error.HTTPError as exc:
        exc.read()
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
        decision = exc.headers.get("X-Aegis-Gateway-Decision", "DENY").upper()
        return elapsed_ms, decision, exc.code, False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--base-url", default=os.environ.get("AEGIS_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--system", required=True, choices=["b0", "b1", "b2", "aegis-http"])
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.repetitions <= 0:
        raise SystemExit("--repetitions must be > 0")
    if args.warmup < 0:
        raise SystemExit("--warmup must be >= 0")

    cases = load_cases(args.cases)
    for _ in range(args.warmup):
        request_gateway(base_url=args.base_url, case=cases[0], timeout=args.timeout)

    samples: list[dict[str, Any]] = []
    for repetition in range(args.repetitions):
        for case in cases:
            elapsed_ms, decision, status_code, success = request_gateway(
                base_url=args.base_url, case=case, timeout=args.timeout
            )
            samples.append({
                "repetition": repetition,
                "scenario_id": case.get("id", case.get("scenario_id")),
                "decision": decision,
                "status_code": status_code,
                "request_success": success,
                "latency_ms": elapsed_ms,
            })

    all_values = [s["latency_ms"] for s in samples]
    allow_values = [s["latency_ms"] for s in samples if s["decision"] == "ALLOW"]
    deny_values = [s["latency_ms"] for s in samples if s["decision"] == "DENY"]
    other_values = [s["latency_ms"] for s in samples if s["decision"] not in {"ALLOW", "DENY"}]

    report = {
        "protocol": "phase10-latency-http-v2",
        "system": args.system,
        "base_url": args.base_url,
        "case_count": len(cases),
        "repetitions": args.repetitions,
        "warmup_requests": args.warmup,
        "sample_count": len(samples),
        "decision_counts": {
            "ALLOW": len(allow_values),
            "DENY": len(deny_values),
            "OTHER": len(other_values),
        },
        "latency_ms": {
            "all": summarize(all_values),
            "allow": summarize(allow_values),
            "deny": summarize(deny_values),
            "other": summarize(other_values),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "hostname": platform.node(),
        },
        "configuration": {"timeout_seconds": args.timeout},
        "samples": samples,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("Latency benchmark complete")
    print(f"system: {args.system}")
    print(f"cases: {len(cases)}")
    print(f"repetitions: {args.repetitions}")
    print(f"samples: {len(samples)}")
    print(json.dumps(report["latency_ms"], indent=2))
    print(f"wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

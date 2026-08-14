#!/usr/bin/env python3
"""Run AegisBench v1 against B0/B1/B2 with reproducible accounting.

This runner deliberately treats repeated evaluations as correlated repeats of
fixed scenarios, not independent samples. It reports seed count, case count,
repetition count, total evaluations, and stratified metrics separately.

Stateful-sequence cases are rejected by default because the current HTTP
protocol is single-request and does not yet expose sequence state to the
policy engine. Use --allow-stateful only after a sequence-aware protocol is
implemented and validated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]

SYSTEMS = ("B0_direct", "B1_rbac", "B2_aegis")
DEFAULT_CONFIG = ROOT / "research" / "experiments" / "baseline_config.json"


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def canonical_hash(data: dict[str, Any]) -> str:
    unsigned = {k: v for k, v in data.items() if k != "content_sha256"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def infer_decision(status: int | None, body: str) -> str:
    if status in {401, 403}:
        return "DENY"
    upper = body.upper()
    deny_markers = (
        '"DECISION":"DENY"', '"DECISION": "DENY"',
        '"STATUS":"DENY"', '"STATUS": "DENY"',
        '"ALLOWED":FALSE', '"ALLOWED": FALSE',
        "ACCESS DENIED", "POLICY DENIED", "UNAUTHORIZED", "FORBIDDEN",
    )
    if any(x in upper for x in deny_markers):
        return "DENY"
    if status is not None and 200 <= status < 300:
        return "ALLOW"
    return "UNKNOWN"


def classify(expected: str, actual: str) -> str:
    pair = (expected.upper(), actual.upper())
    return {
        ("DENY", "DENY"): "true_positive",
        ("ALLOW", "ALLOW"): "true_negative",
        ("ALLOW", "DENY"): "false_positive",
        ("DENY", "ALLOW"): "false_negative",
    }.get(pair, "unclassified")


def request_for(case: dict[str, Any], system: str, config: dict[str, Any]) -> tuple[str | None, dict[str, str], bytes]:
    tool, action = case["tool"], case["action"]
    body = json.dumps(case["parameters"], ensure_ascii=False).encode()
    headers = {
        config["request"]["agent_header"]: case["agent"],
        "Content-Type": config["request"]["content_type"],
    }
    endpoints = config["endpoints"]
    if system == "B0_direct":
        endpoint = endpoints.get(tool)
        if endpoint is None:
            return None, headers, body
        return f"{endpoint['base_url']}/{action}", headers, body
    if system == "B1_rbac":
        return f"{endpoints['rbac']['base_url']}/tools/{tool}/{action}", headers, body
    if system == "B2_aegis":
        return f"{endpoints['gateway']['base_url']}/tools/{tool}/{action}", headers, body
    raise ValueError(f"unknown system: {system}")


def execute(url: str | None, headers: dict[str, str], body: bytes, timeout: float) -> dict[str, Any]:
    if url is None:
        return {"status_code": None, "body": "", "latency_ms": None, "transport_error": "No endpoint"}
    started = time.perf_counter()
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return {
                "status_code": response.status,
                "body": text,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "transport_error": None,
            }
    except HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return {
            "status_code": exc.code,
            "body": text,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "transport_error": None,
        }
    except (URLError, Exception) as exc:
        return {
            "status_code": None,
            "body": "",
            "latency_ms": (time.perf_counter() - started) * 1000,
            "transport_error": repr(exc),
        }


def metric_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r["classification"] for r in records)
    tp, tn = counts["true_positive"], counts["true_negative"]
    fp, fn = counts["false_positive"], counts["false_negative"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    deny = [r for r in records if r["expected"] == "DENY"]
    allow = [r for r in records if r["expected"] == "ALLOW"]
    latencies = [r["latency_ms"] for r in records if r["latency_ms"] is not None]
    return {
        "cases": len({r["scenario_id"] for r in records}),
        "evaluations": len(records),
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "unclassified": counts["unclassified"],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "unauthorized_execution_rate": sum(r["actual"] == "ALLOW" for r in deny) / len(deny) if deny else None,
        "legitimate_task_success_rate": sum(r["actual"] == "ALLOW" for r in allow) / len(allow) if allow else None,
        "latency_ms": {
            "mean": statistics.mean(latencies) if latencies else None,
            "median": statistics.median(latencies) if latencies else None,
            "p50": percentile(latencies, .50),
            "p95": percentile(latencies, .95),
            "p99": percentile(latencies, .99),
        },
    }


def stratified(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(field, "unknown"))].append(record)
    return {key: metric_summary(value) for key, value in sorted(groups.items())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--system", choices=SYSTEMS, required=True)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-stateful", action="store_true")
    args = parser.parse_args()
    if args.repetitions < 1:
        raise ValueError("--repetitions must be >= 1")

    benchmark = load(args.benchmark)
    config = load(args.config)
    scenarios = benchmark.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("benchmark must contain a non-empty scenarios list")
    if benchmark.get("scenario_count") != len(scenarios):
        raise ValueError("benchmark scenario_count does not match scenarios length")
    declared = benchmark.get("content_sha256")
    actual_hash = canonical_hash(benchmark)
    if declared != actual_hash:
        raise ValueError(f"benchmark hash mismatch: declared={declared}, calculated={actual_hash}")

    stateful = [s for s in scenarios if s.get("category") == "stateful_sequence"]
    if stateful and not args.allow_stateful:
        raise ValueError(
            f"benchmark contains {len(stateful)} stateful cases; current HTTP runner is single-request. "
            "Exclude them or implement sequence-aware enforcement before evaluating them."
        )

    seed_ids = {s.get("parent_scenario_id", s.get("id")) for s in scenarios}
    timestamp = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    timeout = float(config["request"]["timeout_seconds"])

    for repetition in range(1, args.repetitions + 1):
        for case in scenarios:
            url, headers, body = request_for(case, args.system, config)
            result = execute(url, headers, body, timeout)
            actual = infer_decision(result["status_code"], result["body"])
            expected = case["expected"]
            records.append({
                "timestamp_utc": timestamp,
                "git_commit": git_commit(),
                "benchmark_version": benchmark["version"],
                "benchmark_sha256": actual_hash,
                "system": args.system,
                "repetition": repetition,
                "scenario_id": case["id"],
                "parent_scenario_id": case.get("parent_scenario_id"),
                "category": case["category"],
                "mutation_operator": case.get("mutation_operator"),
                "agent": case["agent"],
                "tool": case["tool"],
                "action": case["action"],
                "expected": expected,
                "actual": actual,
                "classification": classify(expected, actual),
                "status_code": result["status_code"],
                "latency_ms": result["latency_ms"],
                "transport_error": result["transport_error"],
            })

    summary = metric_summary(records)
    result = {
        "experiment_version": "1.0",
        "system": args.system,
        "benchmark": {
            "version": benchmark["version"],
            "sha256": actual_hash,
            "scenario_count": len(scenarios),
            "unique_seed_count": len(seed_ids),
        },
        "protocol": {
            "repetitions": args.repetitions,
            "total_evaluations": len(records),
            "stateful_included": bool(stateful),
        },
        "git_commit": git_commit(),
        "timestamp_utc": timestamp,
        "summary": summary,
        "by_category": stratified(records, "category"),
        "by_operator": stratified(records, "mutation_operator"),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"system": args.system, "benchmark": result["benchmark"], "protocol": result["protocol"], "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

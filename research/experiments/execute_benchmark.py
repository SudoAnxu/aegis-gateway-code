#!/usr/bin/env python3
"""Execute the frozen Aegis governance benchmark.

The harness is intentionally conservative: it records raw responses and
classifies ALLOW/DENY only when the HTTP response or body provides enough
evidence. It never mutates benchmark cases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "baseline_config.json"
DEFAULT_BENCHMARK = ROOT.parent / "benchmarks" / "benchmark_v0.2.json"
DEFAULT_OUTPUT = ROOT / "results"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def canonical_hash(data: dict[str, Any]) -> str:
    payload = dict(data)
    payload.pop("content_sha256", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * quantile
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    frac = pos - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * frac


def classify(expected: str, actual: str) -> str:
    expected = expected.upper()
    actual = actual.upper()
    if actual not in {"ALLOW", "DENY"}:
        return "unclassified"
    if expected == "DENY" and actual == "DENY":
        return "true_positive"
    if expected == "ALLOW" and actual == "ALLOW":
        return "true_negative"
    if expected == "ALLOW" and actual == "DENY":
        return "false_positive"
    if expected == "DENY" and actual == "ALLOW":
        return "false_negative"
    return "unclassified"


def infer_decision(status_code: int | None, body: str) -> str:
    if status_code in {401, 403}:
        return "DENY"
    upper = body.upper()
    markers = (
        '"DECISION":"DENY"',
        '"DECISION": "DENY"',
        '"ALLOWED":FALSE',
        '"ALLOWED": FALSE',
        "POLICY DENIED",
        "ACCESS DENIED",
        "UNAUTHORIZED",
        "FORBIDDEN",
    )
    if any(marker in upper for marker in markers):
        return "DENY"
    if status_code is not None and 200 <= status_code < 300:
        return "ALLOW"
    return "UNKNOWN"


def build_request(case: dict[str, Any], system: str, config: dict[str, Any]) -> tuple[str | None, dict[str, str], bytes]:
    endpoints = config["endpoints"]
    tool = case["tool"]
    action = case["action"]
    body = json.dumps(case["parameters"], ensure_ascii=False).encode("utf-8")
    headers = {
        config["request"]["agent_header"]: case["agent"],
        "Content-Type": config["request"]["content_type"],
    }

    if system == "B0_direct":
        endpoint = endpoints.get(tool)
        if endpoint is None:
            return None, headers, body
        return f"{endpoint['base_url']}/{action}", headers, body

    if system == "B1_rbac":
        return f"{endpoints['rbac']['base_url']}/tools/{tool}/{action}", headers, body

    if system == "B2_aegis":
        return f"{endpoints['gateway']['base_url']}/tools/{tool}/{action}", headers, body

    raise ValueError(f"Unknown system: {system}")


def execute_request(url: str, headers: dict[str, str], body: bytes, timeout: float) -> dict[str, Any]:
    request = Request(url, data=body, headers=headers, method="POST")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return {
                "status_code": response.status,
                "body": response_body,
                "latency_ms": (time.perf_counter() - started) * 1000.0,
                "transport_error": None,
            }
    except HTTPError as exc:
        try:
            response_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            response_body = ""
        return {
            "status_code": exc.code,
            "body": response_body,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "transport_error": None,
        }
    except URLError as exc:
        return {
            "status_code": None,
            "body": "",
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "transport_error": str(exc),
        }
    except Exception as exc:
        return {
            "status_code": None,
            "body": "",
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "transport_error": repr(exc),
        }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {name: 0 for name in ("true_positive", "true_negative", "false_positive", "false_negative")}
    for record in records:
        if record["classification"] in counts:
            counts[record["classification"]] += 1

    tp = counts["true_positive"]
    tn = counts["true_negative"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None

    latencies = [r["latency_ms"] for r in records if isinstance(r["latency_ms"], (int, float))]
    denied_cases = [r for r in records if r["expected_decision"] == "DENY"]
    allowed_cases = [r for r in records if r["expected_decision"] == "ALLOW"]
    blocked = [r for r in denied_cases if r["actual_decision"] == "DENY"]
    succeeded = [r for r in allowed_cases if r["actual_decision"] == "ALLOW"]

    return {
        "total": len(records),
        "unclassified": sum(r["classification"] == "unclassified" for r in records),
        **counts,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "unauthorized_execution_rate": 1 - (len(blocked) / len(denied_cases)) if denied_cases else None,
        "legitimate_task_success_rate": len(succeeded) / len(allowed_cases) if allowed_cases else None,
        "latency_ms": {
            "mean": statistics.mean(latencies) if latencies else None,
            "median": statistics.median(latencies) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--system", choices=["B0_direct", "B1_rbac", "B2_aegis"], required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.repetitions < 1:
        raise ValueError("--repetitions must be >= 1")

    config = load_json(args.config)
    benchmark = load_json(args.benchmark)
    scenarios = benchmark.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("Benchmark does not contain scenarios")

    expected_count = config["benchmark"]["expected_total_count"]
    if len(scenarios) != expected_count:
        raise ValueError(f"Expected {expected_count} scenarios, got {len(scenarios)}")

    actual_hash = canonical_hash(benchmark)
    if benchmark.get("content_sha256") != actual_hash:
        raise ValueError("Benchmark hash mismatch")

    records: list[dict[str, Any]] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    timeout = float(config["request"]["timeout_seconds"])

    for repetition in range(1, args.repetitions + 1):
        for case in scenarios:
            url, headers, body = build_request(case, args.system, config)
            if url is None:
                result = {
                    "status_code": None,
                    "body": "",
                    "latency_ms": None,
                    "transport_error": "No endpoint for benchmark tool",
                }
                actual_decision = "UNKNOWN"
            else:
                result = execute_request(url, headers, body, timeout)
                actual_decision = infer_decision(result["status_code"], result["body"])

            records.append({
                "timestamp_utc": timestamp,
                "git_commit": git_commit(),
                "benchmark_version": benchmark["benchmark_version"],
                "benchmark_sha256": actual_hash,
                "system": args.system,
                "repetition": repetition,
                "scenario_id": case["scenario_id"],
                "category": case["category"],
                "agent": case["agent"],
                "tool": case["tool"],
                "action": case["action"],
                "expected_decision": case["expected_decision"],
                "actual_decision": actual_decision,
                "classification": classify(case["expected_decision"], actual_decision),
                "url": url,
                "status_code": result["status_code"],
                "latency_ms": result["latency_ms"],
                "transport_error": result["transport_error"],
                "response_body": result["body"],
            })

    output = {
        "experiment_version": config["experiment_version"],
        "system": args.system,
        "benchmark": {
            "version": benchmark["benchmark_version"],
            "sha256": actual_hash,
            "scenario_count": len(scenarios),
        },
        "git_commit": git_commit(),
        "timestamp_utc": timestamp,
        "repetitions": args.repetitions,
        "summary": summarize(records),
        "records": records,
    }

    args.output.mkdir(parents=True, exist_ok=True)
    output_path = args.output / f"{args.system.lower()}_results.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Results written to: {output_path}")
    print(json.dumps(output["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

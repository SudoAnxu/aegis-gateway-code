#!/usr/bin/env python3
"""
Execute the frozen Aegis governance benchmark.

Systems:
    B0_direct  - direct tool-service execution
    B1_rbac    - coarse agent/tool/action authorization
    B2_aegis   - Aegis fine-grained policy gateway

The harness records:
    - decision classification
    - HTTP status
    - latency
    - response body
    - benchmark hash
    - system
    - repetition
    - timestamp

No benchmark case is modified during execution.
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
from urllib.request import Request, build_opener, ProxyHandler, urlopen


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "baseline_config.json"
DEFAULT_BENCHMARK = ROOT.parent / "aegisbench" / "splits" / "development_static_v1.json"
DEFAULT_OUTPUT = ROOT / "results"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)

    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")

    return value


def canonical_hash(data: dict[str, Any]) -> str:
    payload = dict(data)
    payload.pop("content_sha256", None)

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower

    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def classify(expected: str, actual: str) -> str:
    """Positive class = DENY."""
    expected = expected.upper()
    actual = actual.upper()

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
    """Infer governance decision from HTTP response conservatively."""
    if status_code in {401, 403}:
        return "DENY"

    body_upper = body.upper()

    deny_markers = (
        '"DECISION":"DENY"',
        '"DECISION": "DENY"',
        '"STATUS":"DENY"',
        '"STATUS": "DENY"',
        '"ALLOWED":FALSE',
        '"ALLOWED": FALSE',
        "ACCESS DENIED",
        "POLICY DENIED",
        "UNAUTHORIZED",
        "FORBIDDEN",
        "MISSING X-AGENT-ID HEADER",
    )

    if any(marker in body_upper for marker in deny_markers):
        return "DENY"

    if status_code is not None and 200 <= status_code < 300:
        return "ALLOW"

    return "UNKNOWN"


def build_request(
    case: dict[str, Any],
    system: str,
    config: dict[str, Any],
) -> tuple[str | None, dict[str, str], bytes]:
    endpoints = config["endpoints"]

    tool = case["tool"]
    action = case["action"]

    body = json.dumps(case["parameters"], ensure_ascii=False).encode("utf-8")

    headers = {
        config["request"]["agent_header"]: case["agent"],
        "Content-Type": config["request"]["content_type"],
    }

    if system == "B0_direct":
        endpoint = endpoints.get(tool) or endpoints.get("direct_fallback")
        if endpoint is None:
            return None, headers, body
        return f"{endpoint['base_url']}/{action}", headers, body

    if system == "B1_rbac":
        url = f"{endpoints['rbac']['base_url']}/tools/{tool}/{action}"
        return url, headers, body

    if system == "B2_aegis":
        url = f"{endpoints['gateway']['base_url']}/tools/{tool}/{action}"
        return url, headers, body

    raise ValueError(f"Unknown system: {system}")


def execute_request(url: str, headers: dict[str, str], body: bytes, timeout: float) -> dict[str, Any]:
    request = Request(url, data=body, headers=headers, method="POST")
    started = time.perf_counter()

    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return {
                "status_code": response.status,
                "body": response_body,
                "latency_ms": elapsed_ms,
                "transport_error": None,
            }
    except HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        try:
            response_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            response_body = ""
        return {
            "status_code": exc.code,
            "body": response_body,
            "latency_ms": elapsed_ms,
            "transport_error": None,
        }
    except URLError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {
            "status_code": None,
            "body": "",
            "latency_ms": elapsed_ms,
            "transport_error": str(exc),
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {
            "status_code": None,
            "body": "",
            "latency_ms": elapsed_ms,
            "transport_error": repr(exc),
        }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    classified = [r for r in records if r["classification"] != "unclassified"]
    counts = {
        "true_positive": 0,
        "true_negative": 0,
        "false_positive": 0,
        "false_negative": 0,
    }
    for record in classified:
        key = record["classification"]
        if key in counts:
            counts[key] += 1

    tp = counts["true_positive"]
    tn = counts["true_negative"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]

    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None

    latencies = [r["latency_ms"] for r in records if r["latency_ms"] is not None]
    legitimate = [r for r in records if r["expected_decision"] == "ALLOW"]
    unauthorized = [r for r in records if r["expected_decision"] == "DENY"]
    unauthorized_allowed = [r for r in unauthorized if r["actual_decision"] == "ALLOW"]
    legitimate_allowed = [r for r in legitimate if r["actual_decision"] == "ALLOW"]
    transport_errors = [r for r in records if r["transport_error"]]

    return {
        "total": len(records),
        "classified": len(classified),
        "unclassified": len(records) - len(classified),
        **counts,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "unauthorized_execution_rate": len(unauthorized_allowed) / len(unauthorized) if unauthorized else None,
        "legitimate_task_success_rate": len(legitimate_allowed) / len(legitimate) if legitimate else None,
        "transport_error_rate": len(transport_errors) / len(records) if records else None,
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

    declared_count = benchmark.get("scenario_count")
    if not isinstance(declared_count, int) or len(scenarios) != declared_count:
        raise ValueError(f"Benchmark scenario_count mismatch: declared={declared_count}, actual={len(scenarios)}")

    actual_hash = canonical_hash(benchmark)
    if benchmark.get("content_sha256") != actual_hash:
        raise ValueError(
            "Benchmark hash mismatch: "
            f"declared={benchmark.get('content_sha256')}, calculated={actual_hash}"
        )

    benchmark_version = benchmark.get("version")
    if not isinstance(benchmark_version, str):
        raise ValueError("Benchmark version is required")

    timestamp = datetime.now(timezone.utc).isoformat()
    commit = git_commit()
    records: list[dict[str, Any]] = []
    timeout = float(config["request"]["timeout_seconds"])

    for repetition in range(1, args.repetitions + 1):
        for case in scenarios:
            scenario_id = case.get("id")
            expected_decision = case.get("expected")
            if not isinstance(scenario_id, str) or not scenario_id:
                raise ValueError("Scenario missing non-empty id")
            if expected_decision not in {"ALLOW", "DENY"}:
                raise ValueError(f"{scenario_id}: invalid expected decision {expected_decision!r}")

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

            classification = classify(expected_decision, actual_decision)
            records.append({
                "timestamp_utc": timestamp,
                "git_commit": commit,
                "benchmark_version": benchmark_version,
                "benchmark_sha256": actual_hash,
                "system": args.system,
                "repetition": repetition,
                "scenario_id": scenario_id,
                "category": case.get("category"),
                "agent": case.get("agent"),
                "tool": case.get("tool"),
                "action": case.get("action"),
                "expected_decision": expected_decision,
                "actual_decision": actual_decision,
                "classification": classification,
                "url": url,
                "status_code": result["status_code"],
                "latency_ms": result["latency_ms"],
                "transport_error": result["transport_error"],
                "response_body": result["body"],
            })

    summary = summarize(records)
    result = {
        "experiment_version": config["experiment_version"],
        "system": args.system,
        "benchmark": {
            "version": benchmark_version,
            "sha256": actual_hash,
            "scenario_count": len(scenarios),
        },
        "git_commit": commit,
        "timestamp_utc": timestamp,
        "repetitions": args.repetitions,
        "summary": summary,
        "records": records,
    }

    args.output.mkdir(parents=True, exist_ok=True)
    output_path = args.output / f"{args.system.lower()}_results.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Results written to: {output_path}")
    print(f"System: {args.system}")
    print(f"Benchmark: {benchmark_version}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Repetitions: {args.repetitions}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

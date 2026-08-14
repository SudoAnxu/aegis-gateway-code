#!/usr/bin/env python3
"""Run AegisBench v1 against B0/B1/B2 with reproducible accounting."""
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
from urllib.request import Request, build_opener, HTTPHandler

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
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
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
    """Map only defined protocol outcomes to benchmark decisions."""
    if status is None:
        return "UNKNOWN"
    try:
        payload = json.loads(body) if body else None
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        decision = payload.get("decision", payload.get("status"))
        if isinstance(decision, str) and decision.upper() in {"ALLOW", "DENY"}:
            return decision.upper()
        allowed = payload.get("allowed")
        if isinstance(allowed, bool):
            return "ALLOW" if allowed else "DENY"
    if 200 <= status < 300:
        return "ALLOW"
    if status in {400, 401, 403}:
        return "DENY"
    return "UNKNOWN"


def classify(expected: str, actual: str) -> str:
    return {
        ("DENY", "DENY"): "true_positive",
        ("ALLOW", "ALLOW"): "true_negative",
        ("ALLOW", "DENY"): "false_positive",
        ("DENY", "ALLOW"): "false_negative",
    }.get((expected.upper(), actual.upper()), "unclassified")


def request_for(case: dict[str, Any], system: str, config: dict[str, Any]) -> tuple[str | None, dict[str, str], bytes]:
    tool, action = case["tool"], case["action"]
    body = json.dumps(case["parameters"], ensure_ascii=False).encode()
    headers = {
        config["request"]["agent_header"]: case["agent"],
        "Content-Type": config["request"]["content_type"],
    }
    endpoints = config["endpoints"]
    if system == "B0_direct":
        # Direct execution intentionally permits arbitrary tool names. Dedicated
        # fixtures are used when available; the explicit fallback is a permissive
        # fixture for tools that have no dedicated service. This prevents an
        # infrastructure absence from being misclassified as a policy decision.
        endpoint = endpoints.get(tool, endpoints.get("direct_fallback"))
        if endpoint is None:
            raise ValueError(f"B0_direct has no endpoint or direct_fallback for tool {tool!r}")
        return f"{endpoint['base_url']}/{action}", headers, body
    if system == "B1_rbac":
        return f"{endpoints['rbac']['base_url']}/tools/{tool}/{action}", headers, body
    if system == "B2_aegis":
        return f"{endpoints['gateway']['base_url']}/tools/{tool}/{action}", headers, body
    raise ValueError(f"unknown system: {system}")


class LocalNoProxyHandler(HTTPHandler):
    pass


OPENER = build_opener(LocalNoProxyHandler)


def execute(url: str | None, headers: dict[str, str], body: bytes, timeout: float) -> dict[str, Any]:
    if url is None:
        return {"status_code": None, "body": "", "latency_ms": None, "transport_error": "No endpoint"}
    started = time.perf_counter()
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with OPENER.open(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return {"status_code": response.status, "body": text, "latency_ms": (time.perf_counter() - started) * 1000, "transport_error": None}
    except HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return {"status_code": exc.code, "body": text, "latency_ms": (time.perf_counter() - started) * 1000, "transport_error": None}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status_code": None, "body": "", "latency_ms": (time.perf_counter() - started) * 1000, "transport_error": repr(exc)}


def metric_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r["classification"] for r in records)
    tp, tn = counts["true_positive"], counts["true_negative"]
    fp, fn = counts["false_positive"], counts["false_negative"]
    classified = tp + tn + fp + fn
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
        "classification_coverage": classified / len(records) if records else None,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "unauthorized_execution_rate": sum(r["actual"] == "ALLOW" for r in deny) / len(deny) if deny else None,
        "legitimate_task_success_rate": sum(r["actual"] == "ALLOW" for r in allow) / len(allow) if allow else None,
        "transport_error_rate": sum(bool(r["transport_error"]) for r in records) / len(records) if records else None,
        "latency_ms": {
            "mean": statistics.mean(latencies) if latencies else None,
            "median": statistics.median(latencies) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
    }


def stratified(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(field, "unknown"))].append(record)
    return {key: metric_summary(value) for key, value in sorted(groups.items())}


def validate_run_inputs(benchmark: dict[str, Any], config: dict[str, Any]) -> str:
    if config.get("experiment_version") != "1.0":
        raise ValueError("experiment config must have experiment_version=1.0")
    configured_benchmark = config.get("benchmark", {})
    if configured_benchmark.get("release") != "AegisBench-v1":
        raise ValueError("experiment config benchmark release must be AegisBench-v1")
    if benchmark.get("version") != "1.0-static":
        raise ValueError("runner requires a 1.0-static benchmark")
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
    if stateful:
        raise ValueError(f"static benchmark unexpectedly contains {len(stateful)} stateful cases")
    if benchmark.get("role") == "heldout" and configured_benchmark.get("heldout_source_sha256") != actual_hash:
        raise ValueError("heldout benchmark hash does not match experiment configuration")
    if "direct_fallback" not in config.get("endpoints", {}):
        raise ValueError("experiment config must define endpoints.direct_fallback for B0")
    return actual_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--system", choices=SYSTEMS, required=True)
    parser.add_argument("--repetitions", type=int, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = load(args.config)
    repetitions = args.repetitions if args.repetitions is not None else int(config["execution"]["default_repetitions"])
    if repetitions < 1:
        raise ValueError("--repetitions must be >= 1")
    benchmark = load(args.benchmark)
    actual_hash = validate_run_inputs(benchmark, config)
    scenarios = benchmark["scenarios"]
    seed_ids = {s.get("parent_scenario_id", s.get("id")) for s in scenarios}
    timestamp = datetime.now(timezone.utc).isoformat()
    commit = git_commit()
    records: list[dict[str, Any]] = []
    timeout = float(config["request"]["timeout_seconds"])
    for repetition in range(1, repetitions + 1):
        for case in scenarios:
            url, headers, body = request_for(case, args.system, config)
            result = execute(url, headers, body, timeout)
            actual = infer_decision(result["status_code"], result["body"])
            expected = case["expected"]
            records.append({"timestamp_utc": timestamp, "git_commit": commit, "benchmark_version": benchmark["version"], "benchmark_sha256": actual_hash, "system": args.system, "repetition": repetition, "scenario_id": case["id"], "parent_scenario_id": case.get("parent_scenario_id"), "category": case["category"], "mutation_operator": case.get("mutation_operator"), "agent": case["agent"], "tool": case["tool"], "action": case["action"], "expected": expected, "actual": actual, "classification": classify(expected, actual), "status_code": result["status_code"], "latency_ms": result["latency_ms"], "transport_error": result["transport_error"]})
    summary = metric_summary(records)
    invalid = summary["unclassified"] > 0 or summary["transport_error_rate"] not in (None, 0)
    result = {"experiment_version": "1.0", "status": "INVALID" if invalid else "PASS", "system": args.system, "benchmark": {"version": benchmark["version"], "role": benchmark.get("role"), "sha256": actual_hash, "scenario_count": len(scenarios), "unique_seed_count": len(seed_ids)}, "protocol": {"repetitions": repetitions, "total_evaluations": len(records), "stateful_included": False}, "git_commit": commit, "timestamp_utc": timestamp, "summary": summary, "by_category": stratified(records, "category"), "by_operator": stratified(records, "mutation_operator"), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "system": args.system, "benchmark": result["benchmark"], "protocol": result["protocol"], "summary": summary}, indent=2))
    return 2 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())

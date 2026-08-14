#!/usr/bin/env python3
"""Run the held-out stateful benchmark as ordered HTTP sequences.

This harness intentionally keeps stateful evaluation separate from the frozen
static benchmark runner. It does not derive expected outcomes itself; it uses
the benchmark's frozen `expected` field for the target decision and records
all ordered history events plus the final target response.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPHandler

ROOT = Path(__file__).resolve().parents[2]
SYSTEMS = ("B0_direct", "B1_rbac", "B2_aegis")
DEFAULT_CONFIG = ROOT / "research" / "experiments" / "baseline_config.json"


class LocalNoProxyHandler(HTTPHandler):
    pass


OPENER = build_opener(LocalNoProxyHandler)


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
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def infer_decision(status: int | None, body: str) -> str:
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


def endpoint_for(case: dict[str, Any], system: str, config: dict[str, Any]) -> tuple[str, dict[str, str]]:
    tool = case["tool"]
    action = case["action"]
    headers = {
        config["request"]["agent_header"]: case["agent"],
        "Content-Type": config["request"]["content_type"],
    }
    endpoints = config["endpoints"]
    if system == "B0_direct":
        endpoint = endpoints.get(tool, endpoints.get("direct_fallback"))
        if endpoint is None:
            raise ValueError(f"B0_direct has no endpoint for {tool!r}")
        return f"{endpoint['base_url']}/{action}", headers
    if system == "B1_rbac":
        return f"{endpoints['rbac']['base_url']}/tools/{tool}/{action}", headers
    if system == "B2_aegis":
        return f"{endpoints['gateway']['base_url']}/tools/{tool}/{action}", headers
    raise ValueError(system)


def execute(url: str, headers: dict[str, str], params: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(params, ensure_ascii=False).encode()
    started = time.perf_counter()
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with OPENER.open(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return {
                "status_code": response.status,
                "body": text,
                "latency_ms": (time.perf_counter() - started) * 1000.0,
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
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "transport_error": None,
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "status_code": None,
            "body": "",
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "transport_error": repr(exc),
        }


def validate_benchmark(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    if benchmark.get("version") != "1.0-expanded":
        raise ValueError("stateful runner requires the expanded v1 source benchmark")
    if benchmark.get("content_sha256") != canonical_hash(benchmark):
        raise ValueError("benchmark hash mismatch")
    scenarios = benchmark.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("benchmark scenarios missing")
    selected = [s for s in scenarios if s.get("category") == "stateful_sequence"]
    if not selected:
        raise ValueError("no stateful_sequence cases found")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--system", choices=SYSTEMS, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.repetitions < 1:
        raise ValueError("--repetitions must be >= 1")

    config = load(args.config)
    benchmark = load(args.benchmark)
    cases = validate_benchmark(benchmark)
    timeout = float(config["request"]["timeout_seconds"])
    commit = git_commit()
    timestamp = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []

    for repetition in range(1, args.repetitions + 1):
        for case in cases:
            history = case.get("history", [])
            if not isinstance(history, list):
                raise ValueError(f"{case['id']}: history must be a list")

            event_records = []
            for index, event in enumerate(history, start=1):
                if not isinstance(event, dict):
                    raise ValueError(f"{case['id']}: history event {index} is not an object")
                event_record = {
                    "index": index,
                    "event": event,
                }
                event_records.append(event_record)

            # Current production services expose single-request create/refund APIs;
            # the benchmark history is therefore recorded as sequence context. The
            # target refund call is the only live HTTP action in this first protocol
            # implementation. A future stateful fixture can replace this without
            # changing the benchmark record format.
            url, headers = endpoint_for(case, args.system, config)
            result = execute(url, headers, case["parameters"], timeout)
            actual = infer_decision(result["status_code"], result["body"])
            expected = case["expected"]
            records.append({
                "timestamp_utc": timestamp,
                "git_commit": commit,
                "benchmark_version": benchmark["version"],
                "benchmark_sha256": benchmark["content_sha256"],
                "system": args.system,
                "repetition": repetition,
                "scenario_id": case["id"],
                "parent_scenario_id": case.get("parent_scenario_id"),
                "category": case["category"],
                "agent": case["agent"],
                "tool": case["tool"],
                "action": case["action"],
                "transaction_id": case.get("transaction_id", case.get("parameters", {}).get("transaction_id")),
                "history": history,
                "history_events": event_records,
                "expected": expected,
                "expected_reason": case.get("reason"),
                "actual": actual,
                "classification": classify(expected, actual),
                "status_code": result["status_code"],
                "latency_ms": result["latency_ms"],
                "transport_error": result["transport_error"],
                "response_body": result["body"],
            })

    classified = [r for r in records if r["classification"] != "unclassified"]
    summary = {
        "cases": len(cases),
        "evaluations": len(records),
        "true_positive": sum(r["classification"] == "true_positive" for r in records),
        "true_negative": sum(r["classification"] == "true_negative" for r in records),
        "false_positive": sum(r["classification"] == "false_positive" for r in records),
        "false_negative": sum(r["classification"] == "false_negative" for r in records),
        "unclassified": len(records) - len(classified),
        "transport_error_rate": sum(bool(r["transport_error"]) for r in records) / len(records) if records else 0,
    }

    result = {
        "experiment_version": "stateful-0.1",
        "status": "PASS" if summary["unclassified"] == 0 and summary["transport_error_rate"] == 0 else "INVALID",
        "system": args.system,
        "benchmark": {
            "version": benchmark["version"],
            "sha256": benchmark["content_sha256"],
            "stateful_cases": len(cases),
        },
        "repetitions": args.repetitions,
        "git_commit": commit,
        "timestamp_utc": timestamp,
        "summary": summary,
        "records": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "system", "benchmark", "repetitions", "summary")}, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

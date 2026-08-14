#!/usr/bin/env python3
"""Run AegisBench stateful sequences as ordered live HTTP interactions."""
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
from urllib.request import HTTPHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
SYSTEMS = ("B0_direct", "B1_rbac", "B2_aegis")
DEFAULT_CONFIG = ROOT / "research" / "experiments" / "baseline_config.json"
OPENER = build_opener(HTTPHandler)


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
        if isinstance(payload.get("allowed"), bool):
            return "ALLOW" if payload["allowed"] else "DENY"
        if payload.get("error") == "PolicyViolation":
            return "DENY"
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


def endpoint_for_case(case: dict[str, Any], system: str, config: dict[str, Any]) -> tuple[str, dict[str, str]]:
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
            return {"status_code": response.status, "body": response.read().decode("utf-8", errors="replace"), "latency_ms": (time.perf_counter() - started) * 1000.0, "transport_error": None}
    except HTTPError as exc:
        return {"status_code": exc.code, "body": exc.read().decode("utf-8", errors="replace"), "latency_ms": (time.perf_counter() - started) * 1000.0, "transport_error": None}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status_code": None, "body": "", "latency_ms": (time.perf_counter() - started) * 1000.0, "transport_error": repr(exc)}


def replay_history_event(base_case: dict[str, Any], event: dict[str, Any], system: str, config: dict[str, Any], timeout: float) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError(f"history event must be an object: {event!r}")
    event_type = event.get("event")
    event_id = event.get("id")
    if event_type not in {"payment_created", "payment_refunded"}:
        return {"synthetic": True, "event": event, "status_code": None, "body": "", "decision": "DENY", "transport_error": None}
    action = "create" if event_type == "payment_created" else "refund"
    params = dict(base_case.get("parameters", {}))
    params["transaction_id"] = event_id
    replay_case = dict(base_case)
    replay_case["action"] = action
    replay_case["parameters"] = params
    url, headers = endpoint_for_case(replay_case, system, config)
    result = execute(url, headers, params, timeout)
    result.update({"synthetic": False, "event": event, "decision": infer_decision(result["status_code"], result["body"])})
    return result


def validate_cases(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    if benchmark.get("version") != "1.0-expanded":
        raise ValueError("stateful runner requires an expanded v1 benchmark")
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
    cases = validate_cases(benchmark)
    timeout = float(config["request"]["timeout_seconds"])
    commit = git_commit()
    timestamp = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []

    for repetition in range(1, args.repetitions + 1):
        for case in cases:
            history = case.get("history", [])
            if not isinstance(history, list):
                raise ValueError(f"{case['id']}: history must be a list")

            history_records = []
            sequence_transport_error = None
            for index, event in enumerate(history, start=1):
                replay = replay_history_event(case, event, args.system, config, timeout)
                history_records.append({"index": index, **replay})
                if replay.get("transport_error"):
                    sequence_transport_error = replay["transport_error"]
                    break

            target_result = execute(*endpoint_for_case(case, args.system, config), case["parameters"], timeout)
            target_actual = infer_decision(target_result["status_code"], target_result["body"])
            transport_error = sequence_transport_error or target_result["transport_error"]

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
                "transaction_id": case.get("parameters", {}).get("transaction_id"),
                "history": history,
                "history_records": history_records,
                "expected": case["expected"],
                "expected_reason": case.get("reason"),
                "actual": target_actual,
                "classification": classify(case["expected"], target_actual),
                "status_code": target_result["status_code"],
                "latency_ms": target_result["latency_ms"],
                "transport_error": transport_error,
                "response_body": target_result["body"],
            })

    classified = [r for r in records if r["classification"] != "unclassified" and not r["transport_error"]]
    summary = {
        "cases": len(cases),
        "evaluations": len(records),
        "true_positive": sum(r["classification"] == "true_positive" and not r["transport_error"] for r in records),
        "true_negative": sum(r["classification"] == "true_negative" and not r["transport_error"] for r in records),
        "false_positive": sum(r["classification"] == "false_positive" and not r["transport_error"] for r in records),
        "false_negative": sum(r["classification"] == "false_negative" and not r["transport_error"] for r in records),
        "unclassified": len(records) - len(classified),
        "transport_error_rate": sum(bool(r["transport_error"]) for r in records) / len(records) if records else 0,
    }
    result = {
        "experiment_version": "stateful-0.3",
        "status": "PASS" if summary["unclassified"] == 0 and summary["transport_error_rate"] == 0 else "INVALID",
        "system": args.system,
        "benchmark": {"version": benchmark["version"], "sha256": benchmark["content_sha256"], "stateful_cases": len(cases)},
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

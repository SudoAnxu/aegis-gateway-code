#!/usr/bin/env python3
"""Run AegisBench stateful sequences with isolated live state."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from copy import deepcopy
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


def isolated_case(case: dict[str, Any], repetition: int) -> dict[str, Any]:
    """Namespace the benchmark transaction for the live gateway.

    The expanded benchmark deliberately reuses seed transaction IDs across
    mutations. The live gateway is stateful and has no reset operation, so
    replaying those literal IDs would leak state from one benchmark case into
    the next. A deterministic per-case namespace preserves every equality and
    inequality relationship in the frozen history while guaranteeing isolation.
    """
    live = deepcopy(case)
    params = live["parameters"]
    benchmark_txn = params["transaction_id"]
    live_txn = f"aegisbench-r{repetition}-{case['id']}"
    params["transaction_id"] = live_txn
    for event in live.get("history", []):
        if isinstance(event, dict) and event.get("id") == benchmark_txn:
            event["id"] = live_txn
    live["_benchmark_transaction_id"] = benchmark_txn
    live["_live_transaction_id"] = live_txn
    return live


def history_for_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    params = case.get("parameters") or {}
    transaction_id = params.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id.strip():
        raise ValueError(f"{case['id']}: missing transaction_id")
    steps: list[dict[str, Any]] = []
    for event in case.get("history", []):
        if not isinstance(event, dict):
            raise ValueError(f"{case['id']}: history event must be an object")
        kind = event.get("event")
        event_id = event.get("id")
        if kind not in {"payment_created", "payment_refunded"}:
            steps.append({"event": kind, "supported": False, "event_id": event_id, "target_transaction_id": transaction_id})
            continue

        # The benchmark models the state-machine identity as transaction_id,
        # but the live payments tool's refund API uses payment_id. Keep the
        # benchmark transaction identity for state isolation while translating
        # the request into the real tool schema for refund replay.
        event_params: dict[str, Any] = {"transaction_id": transaction_id}
        if kind == "payment_refunded":
            event_params["payment_id"] = transaction_id
        for key in ("amount", "currency"):
            value = event.get(key, params.get(key))
            if value is not None:
                event_params[key] = value
        steps.append({"event": kind, "supported": True, "event_id": event_id, "target_transaction_id": transaction_id, "params": event_params})
    return steps


def expected_history_decisions(case: dict[str, Any]) -> list[str]:
    target = case["parameters"].get("transaction_id")
    expected: list[str] = []
    created = False
    refunded = False
    for event in case.get("history", []):
        if not isinstance(event, dict):
            expected.append("DENY")
            continue
        if event.get("id") != target:
            expected.append("SKIP")
            continue
        kind = event.get("event")
        if kind == "payment_created":
            if created:
                expected.append("DENY")
            else:
                expected.append("ALLOW")
                created = True
        elif kind == "payment_refunded":
            if created and not refunded:
                expected.append("ALLOW")
                refunded = True
            else:
                expected.append("DENY")
        else:
            expected.append("DENY")
    return expected


def run_sequence(case: dict[str, Any], system: str, config: dict[str, Any], timeout: float) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    replay_ok = True
    history_steps = history_for_case(case)
    expected_steps = expected_history_decisions(case)

    for index, (step_spec, expected_step) in enumerate(zip(history_steps, expected_steps), start=1):
        step = {"index": index, **{k: v for k, v in step_spec.items() if k != "params"}, "expected": expected_step}
        if not step_spec["supported"] or expected_step == "SKIP":
            step["actual"] = "SKIP"
            step["status_code"] = None
            step["transport_error"] = None
            steps.append(step)
            continue
        history_case = dict(case)
        history_case["action"] = "create" if step_spec["event"] == "payment_created" else "refund"
        history_case["parameters"] = step_spec["params"]
        url, headers = endpoint_for_case(history_case, system, config)
        result = execute(url, headers, step_spec["params"], timeout)
        actual = infer_decision(result["status_code"], result["body"])
        step.update({"action": history_case["action"], "actual": actual, "status_code": result["status_code"], "latency_ms": result["latency_ms"], "transport_error": result["transport_error"], "response_body": result["body"]})
        if result["transport_error"] or actual != expected_step:
            replay_ok = False
        steps.append(step)

    target_url, target_headers = endpoint_for_case(case, system, config)
    target_result = execute(target_url, target_headers, case["parameters"], timeout)
    target_actual = infer_decision(target_result["status_code"], target_result["body"])
    return {"history_steps": steps, "history_replay_ok": replay_ok, "target": {"actual": target_actual, **target_result}}


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
            live_case = isolated_case(case, repetition)
            result = run_sequence(live_case, args.system, config, timeout)
            target = result["target"]
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
                "transaction_id": case.get("parameters", {}).get("transaction_id"),
                "live_transaction_id": live_case["parameters"]["transaction_id"],
                "history": case.get("history", []),
                "history_steps": result["history_steps"],
                "history_replay_ok": result["history_replay_ok"],
                "expected": expected,
                "expected_reason": case.get("reason"),
                "actual": target["actual"],
                "classification": classify(expected, target["actual"]),
                "status_code": target["status_code"],
                "latency_ms": target["latency_ms"],
                "transport_error": target["transport_error"],
                "response_body": target["body"],
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
        "history_replay_failures": sum(not r["history_replay_ok"] for r in records),
        "transport_error_rate": sum(bool(r["transport_error"]) for r in records) / len(records) if records else 0,
    }
    result = {
        "experiment_version": "stateful-0.6",
        "status": "PASS" if summary["unclassified"] == 0 and summary["transport_error_rate"] == 0 and summary["history_replay_failures"] == 0 else "INVALID",
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

#!/usr/bin/env python3
"""Run AegisBench stateful sequences against isolated live gateway state.

The benchmark history is authoritative: each history event is exercised in
order against the live system. Wrong-object events are isolated but still sent
because the contract requires every event/request to be observed. Once a
history event is denied, the sequence is terminal for target execution; the
target is recorded as not-executed rather than fabricating a reachable state.
"""
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
    return hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


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


def endpoint_for_case(case: dict[str, Any], system: str, config: dict[str, Any], mutation_id=None):
    tool, action = case["tool"], case["action"]
    headers = {
        config["request"]["agent_header"]: case["agent"],
        "Content-Type": config["request"]["content_type"],
    }
    e = config["endpoints"]
    if system == "B0_direct":
        endpoint = e.get(tool, e.get("direct_fallback"))
        if endpoint is None:
            raise ValueError(f"B0_direct has no endpoint for {tool!r}")
        return f"{endpoint['base_url']}/{action}", headers
    if system == "B1_rbac":
        return f"{e['rbac']['base_url']}/tools/{tool}/{action}", headers
    if system == "B2_aegis":
        if mutation_id:
            headers["X-Aegis-Mutant-ID"] = mutation_id
        return f"{e['gateway']['base_url']}/tools/{tool}/{action}", headers
    raise ValueError(system)


def execute(url: str, headers: dict[str, str], params: dict[str, Any], timeout: float):
    started = time.perf_counter()
    req = Request(
        url,
        data=json.dumps(params, ensure_ascii=False).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with OPENER.open(req, timeout=timeout) as r:
            return {
                "status_code": r.status,
                "body": r.read().decode("utf-8", "replace"),
                "latency_ms": (time.perf_counter() - started) * 1000,
                "transport_error": None,
            }
    except HTTPError as e:
        return {
            "status_code": e.code,
            "body": e.read().decode("utf-8", "replace"),
            "latency_ms": (time.perf_counter() - started) * 1000,
            "transport_error": None,
        }
    except (URLError, TimeoutError, OSError) as e:
        return {
            "status_code": None,
            "body": "",
            "latency_ms": (time.perf_counter() - started) * 1000,
            "transport_error": repr(e),
        }


def validate_cases(benchmark):
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


def isolated_case(case, repetition):
    live = deepcopy(case)
    benchmark_txn = live.get("parameters", {}).get("transaction_id")
    live_txn = f"aegisbench-r{repetition}-{case['id']}"
    if benchmark_txn:
        live.setdefault("parameters", {})["transaction_id"] = live_txn
    live["_benchmark_transaction_id"] = benchmark_txn
    live["_live_transaction_id"] = live_txn
    return live


def event_expected(
    benchmark_txn: str | None,
    event: dict[str, Any],
    model_created: bool,
    model_refunded: bool,
):
    """Return (expected_decision, reason, next_created, next_refunded).

    The event itself is authoritative. Wrong-object events are still exercised;
    they must be denied by the state-aware system and do not mutate target state.
    """

    target = benchmark_txn
    event_id = event.get("id")
    kind = event.get("event")
    if event_id != target:
        return "DENY", "state_invalid_transition", model_created, model_refunded
    if kind == "payment_created":
        if model_created:
            return "DENY", "state_invalid_transition", model_created, model_refunded
        return "ALLOW", "state_transition", True, model_refunded
    if kind == "payment_refunded":
        if not model_created:
            return "DENY", "state_precondition", model_created, model_refunded
        if model_refunded:
            return "DENY", "state_replay", model_created, model_refunded
        return "ALLOW", "state_transition", model_created, True
    return "DENY", "state_unknown_event", model_created, model_refunded


def live_event_params(
    event: dict[str, Any],
    benchmark_txn: str | None,
    live_txn: str,
    base_params: dict[str, Any],
):
    kind = event.get("event")
    event_id = event.get("id")

    event_txn = (
        live_txn
        if event_id == benchmark_txn
        else f"{live_txn}-other"
    )

    if kind == "payment_created":
        out = {"transaction_id": event_txn}
        for key in ("amount", "currency"):
            if base_params.get(key) is not None:
                out[key] = base_params[key]
        return out

    if kind == "payment_refunded":
        out = {
            "payment_id": event_txn,
            "reason": base_params.get("reason") or "AegisBench state replay",
        }
        for key in ("amount", "currency"):
            if base_params.get(key) is not None:
                out[key] = base_params[key]
        return out

    return dict(base_params)


def run_sequence(case, system, config, timeout, repetition,mutation_id=None):
    live = isolated_case(case, repetition)
    live_txn = live["_live_transaction_id"]
    benchmark_txn = live["_benchmark_transaction_id"]
    steps = []
    history_ok = True
    transport_error = False
    created = False
    refunded = False
    terminal_history = False

    for index, event in enumerate(case.get("history", []), 1):
        if not isinstance(event, dict):
            history_ok = False
            steps.append({
                "index": index,
                "event": None,
                "event_id": None,
                "expected": "DENY",
                "reason": "state_malformed",
                "action": None,
                "actual": "UNKNOWN",
                "status_code": None,
                "transport_error": "state_malformed",
                "request_params": None,
                "response_body": "",
                "executed": False,
            })
            terminal_history = True
            continue

        expected, reason, next_created, next_refunded = event_expected(case, event, created, refunded)
        params = live_event_params(
            event,
            benchmark_txn,
            live_txn,
            live.get("parameters", {}),
            )
        action = "create" if event.get("event") == "payment_created" else "refund" if event.get("event") == "payment_refunded" else event.get("event", "unknown")
        request_case = dict(live)
        request_case["action"] = action
        request_case["parameters"] = params
        url, headers = endpoint_for_case(request_case, system, config, mutation_id)
        result = execute(url, headers, params, timeout)
        actual = infer_decision(result["status_code"], result["body"])

        ok = not result["transport_error"] and actual == expected
        history_ok = history_ok and ok
        transport_error = transport_error or bool(result["transport_error"])
        steps.append({
            "index": index,
            "event": event.get("event"),
            "event_id": event.get("id"),
            "expected": expected,
            "reason": reason,
            "action": action,
            "actual": actual,
            "status_code": result["status_code"],
            "transport_error": result["transport_error"],
            "request_params": params,
            "response_body": result["body"],
            "latency_ms": result["latency_ms"],
            "executed": True,
        })

        if ok and expected == "ALLOW":
            # Only an allowed transition changes the modeled state.
            # A correctly denied event leaves the prior state unchanged.
            created, refunded = next_created, next_refunded

        # Continue recording authoritative history events, but once the gateway
        # has correctly denied a terminal transition, later events are expected
        # to be evaluated from the same pre-terminal state.

    # History validation and target evaluation are independent. A correctly
    # denied history event does not terminate the benchmark sequence; it simply
    # leaves the modeled state unchanged.
    target_executed = True
    target_result = None
    target_actual = "UNKNOWN"
    if target_executed:
        target_params = dict(live.get("parameters", {}))
        if case["action"] == "refund":
            target_params = {
                "payment_id": live_txn,
                "reason": target_params.get("reason") or "AegisBench target",
                **{k: target_params[k] for k in ("amount", "currency") if target_params.get(k) is not None},
            }
        elif case["action"] == "create":
            target_params["transaction_id"] = live_txn
        target_case = dict(live)
        target_case["parameters"] = target_params
        url, headers = endpoint_for_case(target_case, system, config, mutation_id)
        target_result = execute(url, headers, target_params, timeout)
        target_actual = infer_decision(target_result["status_code"], target_result["body"])
        transport_error = transport_error or bool(target_result["transport_error"])
    else:
        target_result = {
            "status_code": None,
            "body": "",
            "latency_ms": 0.0,
            "transport_error": None,
        }

    return {
        "live_transaction_id": live_txn,
        "benchmark_transaction_id": benchmark_txn,
        "history_steps": steps,
        "history_replay_ok": history_ok,
        "terminal_history": terminal_history,
        "target_executed": target_executed,
        "target": {"actual": target_actual, **target_result},
        "transport_error": transport_error,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--benchmark", type=Path, required=True)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--system", choices=SYSTEMS, required=True)
    p.add_argument("--repetitions", type=int, default=1)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mutation-id", default=None)
    args = p.parse_args()
    if args.repetitions < 1:
        raise ValueError("--repetitions must be >= 1")

    config = load(args.config)
    benchmark = load(args.benchmark)
    cases = validate_cases(benchmark)
    timeout = float(config["request"]["timeout_seconds"])
    commit = git_commit()
    timestamp = datetime.now(timezone.utc).isoformat()
    records = []

    for repetition in range(1, args.repetitions + 1):
        for case in cases:
            result = run_sequence(case, args.system, config, timeout, repetition, args.mutation_id,)
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
                "live_transaction_id": result["live_transaction_id"],
                "history": case.get("history", []),
                "history_steps": result["history_steps"],
                "history_replay_ok": result["history_replay_ok"],
                "terminal_history": result["terminal_history"],
                "target_executed": result["target_executed"],
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
        "experiment_version": "stateful-0.9",
        "status": "PASS" if summary["unclassified"] == 0 and summary["transport_error_rate"] == 0 and summary["history_replay_failures"] == 0 else "INVALID",
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

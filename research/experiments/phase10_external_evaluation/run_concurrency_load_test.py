#!/usr/bin/env python3
"""Concurrent load test for the real Aegis tool endpoint.

The workload intentionally uses the same HTTP contract as
phase10_external_evaluation/aegis_http_adapter.py: POST /tools/{tool}/{action}
with X-Agent-ID authentication.  The evaluation-only state endpoint is used
only when a workload needs explicit seeded state.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout: float,
    headers: dict[str, str] | None = None,
) -> tuple[float, int, dict[str, Any] | None, str | None, dict[str, str]]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode(errors="replace")
            status = resp.status
            response_headers = dict(resp.headers.items())
        elapsed = (time.perf_counter() - start) * 1000
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return elapsed, status, parsed, None, response_headers
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return elapsed, exc.code, parsed, f"HTTPError: {raw[:500]}", dict(exc.headers.items())
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, 0, None, f"{type(exc).__name__}: {exc}", {}


def seed(url: str, history: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    elapsed, status, body, error, _ = post_json(
        url.rstrip("/") + "/__evaluation__/state",
        {"history": history},
        timeout,
    )
    if error or status != 200 or not body or not body.get("seeded"):
        raise RuntimeError(f"state seed failed: status={status} body={body} error={error}")
    return {"elapsed_ms": round(elapsed, 3), "status": status, **body}


def make_payload(index: int, unique: bool, amount: float) -> dict[str, Any]:
    params: dict[str, Any] = {"amount": amount, "currency": "USD"}
    if unique:
        params["transaction_id"] = f"load-{index}-{time.time_ns()}"
    return params


def run_level(
    base_url: str,
    concurrency: int,
    requests_count: int,
    timeout: float,
    agent: str,
    tool: str,
    action: str,
    unique: bool,
    amount: float,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + f"/tools/{tool}/{action}"
    latencies: list[float] = []
    statuses: list[int] = []
    decisions: dict[str, int] = {}
    errors: list[str] = []
    downstream = 0
    lock = threading.Lock()

    def one(i: int) -> None:
        nonlocal downstream
        elapsed, status, body, error, response_headers = post_json(
            url,
            make_payload(i, unique, amount),
            timeout,
            {"X-Agent-ID": agent},
        )
        with lock:
            latencies.append(elapsed)
            statuses.append(status)
            if error:
                errors.append(error)
            decision = (
                str(body.get("decision"))
                if body and "decision" in body
                else response_headers.get("X-Aegis-Gateway-Decision", "NO_RESPONSE")
            )
            decisions[decision] = decisions.get(decision, 0) + 1
            # Real tool responses are 2xx only when downstream execution occurred.
            if 200 <= status < 300:
                downstream += 1

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(one, range(requests_count)))
    wall_ms = (time.perf_counter() - started) * 1000

    latencies.sort()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        pos = (len(latencies) - 1) * p
        lo = int(pos)
        hi = min(lo + 1, len(latencies) - 1)
        return latencies[lo] + (latencies[hi] - latencies[lo]) * (pos - lo)

    return {
        "concurrency": concurrency,
        "requests": requests_count,
        "unique_transactions": unique,
        "agent": agent,
        "tool": tool,
        "action": action,
        "wall_time_ms": round(wall_ms, 3),
        "throughput_rps": round(requests_count / (wall_ms / 1000), 3) if wall_ms else 0.0,
        "mean_ms": round(statistics.mean(latencies), 3) if latencies else None,
        "p50_ms": round(pct(0.50), 3),
        "p95_ms": round(pct(0.95), 3),
        "p99_ms": round(pct(0.99), 3),
        "max_ms": round(max(latencies), 3) if latencies else None,
        "http_non2xx": sum(1 for s in statuses if s < 200 or s >= 300),
        "request_errors": len(errors),
        "decisions": decisions,
        "downstream_executed": downstream,
        "error_samples": errors[:10],
    }


def run_duplicate_race(
    base_url: str,
    concurrency: int,
    timeout: float,
    agent: str,
    tool: str,
    action: str,
) -> dict[str, Any]:
    """Race identical creates after seeding one existing payment.

    Secure expected outcome: zero downstream executions. This specifically
    exercises the stateful duplicate reservation/commit path under concurrency.
    """
    transaction_id = f"race-{time.time_ns()}"
    seed_result = seed(
        base_url,
        [{"event": "payment_created", "id": transaction_id}],
        timeout,
    )
    payload = {"amount": 100, "currency": "USD", "transaction_id": transaction_id}
    url = base_url.rstrip("/") + f"/tools/{tool}/{action}"
    results: list[tuple[float, int, dict[str, Any] | None, str | None, dict[str, str]]] = []
    lock = threading.Lock()

    def one(_: int) -> None:
        result = post_json(url, payload, timeout, {"X-Agent-ID": agent})
        with lock:
            results.append(result)

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(one, range(concurrency)))
    wall_ms = (time.perf_counter() - started) * 1000

    decisions: dict[str, int] = {}
    downstream = 0
    errors: list[str] = []
    latencies = []
    statuses = []
    for elapsed, status, body, error, response_headers in results:
        latencies.append(elapsed)
        statuses.append(status)
        if error:
            errors.append(error)
        decision = (
            str(body.get("decision"))
            if body and "decision" in body
            else response_headers.get("X-Aegis-Gateway-Decision", "NO_RESPONSE")
        )
        decisions[decision] = decisions.get(decision, 0) + 1
        if 200 <= status < 300:
            downstream += 1

    latencies.sort()
    return {
        "concurrency": concurrency,
        "requests": concurrency,
        "transaction_id": transaction_id,
        "seed": seed_result,
        "wall_time_ms": round(wall_ms, 3),
        "throughput_rps": round(concurrency / (wall_ms / 1000), 3) if wall_ms else 0.0,
        "mean_ms": round(statistics.mean(latencies), 3),
        "p95_ms": round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 3),
        "decisions": decisions,
        "http_non2xx": sum(1 for s in statuses if s < 200 or s >= 300),
        "downstream_executed": downstream,
        "state_safety_pass": downstream == 0,
        "request_errors": len(errors),
        "error_samples": errors[:10],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--concurrency", default="1,10,50,100,250,500,1000")
    ap.add_argument("--requests-per-level", type=int, default=1000)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--agent", default="finance-agent")
    ap.add_argument("--tool", default="payments")
    ap.add_argument("--action", default="create")
    ap.add_argument("--amount", type=float, default=100)
    ap.add_argument("--duplicate-race", action="store_true")
    ap.add_argument("--output", default="research/experiments/results/phase10_external/concurrency_load_v2.json")
    args = ap.parse_args()

    levels = [int(x.strip()) for x in args.concurrency.split(",") if x.strip()]
    if any(x < 1 for x in levels):
        raise SystemExit("concurrency levels must be positive")

    results: dict[str, Any] = {
        "protocol": "phase10-concurrency-load-v2",
        "url": args.url,
        "requests_per_level": args.requests_per_level,
        "agent": args.agent,
        "tool": args.tool,
        "action": args.action,
        "levels": [],
        "duplicate_race": [],
    }
    for level in levels:
        print(f"running unique workload concurrency={level} requests={args.requests_per_level}", flush=True)
        row = run_level(
            args.url, level, args.requests_per_level, args.timeout,
            args.agent, args.tool, args.action, True, args.amount,
        )
        results["levels"].append(row)
        print(json.dumps(row, sort_keys=True), flush=True)

    if args.duplicate_race:
        for level in levels:
            print(f"running duplicate-race concurrency={level}", flush=True)
            row = run_duplicate_race(
                args.url, level, args.timeout, args.agent, args.tool, args.action
            )
            results["duplicate_race"].append(row)
            print(json.dumps(row, sort_keys=True), flush=True)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

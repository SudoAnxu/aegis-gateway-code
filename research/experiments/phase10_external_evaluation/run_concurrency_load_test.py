#!/usr/bin/env python3
"""Concurrent load test for the Aegis HTTP evaluation adapter.

Generates real gateway requests against the running local gateway. The test is
intended to measure throughput, latency, errors, and state correctness under
concurrency. It deliberately tests both unique requests and a duplicate-race
workload because the stateful reservation/commit path is the key scalability
risk.

Usage examples:
  python run_concurrency_load_test.py --url http://127.0.0.1:8080 --concurrency 1,10,50,100,250
  python run_concurrency_load_test.py --url http://127.0.0.1:8080 --concurrency 10,50,100 --requests-per-level 1000

The script does not claim a request is successful merely because HTTP returned
200: it records the gateway decision and downstream execution separately.
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


PAYLOAD_TEMPLATE = {
    "arguments": {
        "action": "create",
        "agent": "finance-agent",
        "parameters": {"amount": 100, "currency": "USD"},
        "tool": "payments",
    }
}


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[float, int, dict[str, Any] | None, str | None]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            status = resp.status
        elapsed = (time.perf_counter() - start) * 1000
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return elapsed, status, parsed, None
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return elapsed, exc.code, parsed, f"HTTPError: {raw[:500]}"
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, 0, None, f"{type(exc).__name__}: {exc}"


def seed(url: str, history: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    elapsed, status, body, error = post_json(
        url.rstrip("/") + "/__evaluation__/state",
        {"history": history},
        timeout,
    )
    if error or status != 200 or not body or not body.get("seeded"):
        raise RuntimeError(f"state seed failed: status={status} body={body} error={error}")
    return {"elapsed_ms": elapsed, "status": status, **body}


def make_payload(index: int, unique: bool) -> dict[str, Any]:
    payload = json.loads(json.dumps(PAYLOAD_TEMPLATE))
    if unique:
        payload["arguments"]["parameters"]["transaction_id"] = f"load-{index}"
    return payload


def run_level(base_url: str, concurrency: int, requests_count: int, timeout: float, unique: bool) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/__evaluation__/tool"
    latencies: list[float] = []
    statuses: list[int] = []
    decisions: dict[str, int] = {}
    errors: list[str] = []
    downstream = 0
    lock = threading.Lock()

    def one(i: int) -> None:
        nonlocal downstream
        elapsed, status, body, error = post_json(url, make_payload(i, unique), timeout)
        with lock:
            latencies.append(elapsed)
            statuses.append(status)
            if error:
                errors.append(error)
            decision = str(body.get("decision")) if body else "NO_RESPONSE"
            decisions[decision] = decisions.get(decision, 0) + 1
            if body and body.get("downstream_executed"):
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


def run_duplicate_race(base_url: str, concurrency: int, timeout: float) -> dict[str, Any]:
    """Race identical creates after seeding one existing payment.

    For a duplicate-create race, the expected secure outcome is zero downstream
    executions. This is a correctness check under concurrency, not merely a
    latency measurement.
    """
    transaction_id = f"race-{int(time.time() * 1000000)}"
    seed_result = seed(
        base_url,
        [{"event": "payment_created", "id": transaction_id}],
        timeout,
    )
    payload = make_payload(0, True)
    payload["arguments"]["parameters"]["transaction_id"] = transaction_id
    url = base_url.rstrip("/") + "/__evaluation__/tool"
    results: list[tuple[float, int, dict[str, Any] | None, str | None]] = []
    lock = threading.Lock()

    def one(_: int) -> None:
        result = post_json(url, payload, timeout)
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
    for elapsed, status, body, error in results:
        latencies.append(elapsed)
        if error:
            errors.append(error)
        decision = str(body.get("decision")) if body else "NO_RESPONSE"
        decisions[decision] = decisions.get(decision, 0) + 1
        if body and body.get("downstream_executed"):
            downstream += 1
    return {
        "concurrency": concurrency,
        "requests": concurrency,
        "transaction_id": transaction_id,
        "seed": seed_result,
        "wall_time_ms": round(wall_ms, 3),
        "throughput_rps": round(concurrency / (wall_ms / 1000), 3) if wall_ms else 0.0,
        "mean_ms": round(statistics.mean(latencies), 3),
        "p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 3),
        "decisions": decisions,
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
    ap.add_argument("--duplicate-race", action="store_true")
    ap.add_argument("--output", default="research/experiments/results/phase10_external/concurrency_load_v1.json")
    args = ap.parse_args()

    levels = [int(x.strip()) for x in args.concurrency.split(",") if x.strip()]
    if any(x < 1 for x in levels):
        raise SystemExit("concurrency levels must be positive")

    results = {
        "protocol": "phase10-concurrency-load-v1",
        "url": args.url,
        "requests_per_level": args.requests_per_level,
        "levels": [],
        "duplicate_race": [],
    }
    for level in levels:
        print(f"running unique workload concurrency={level} requests={args.requests_per_level}", flush=True)
        row = run_level(args.url, level, args.requests_per_level, args.timeout, unique=True)
        results["levels"].append(row)
        print(json.dumps(row, sort_keys=True), flush=True)

    if args.duplicate_race:
        for level in levels:
            print(f"running duplicate-race concurrency={level}", flush=True)
            row = run_duplicate_race(args.url, level, args.timeout)
            results["duplicate_race"].append(row)
            print(json.dumps(row, sort_keys=True), flush=True)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

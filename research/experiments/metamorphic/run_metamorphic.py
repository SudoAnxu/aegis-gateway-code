from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research"))

import importlib.util

EXECUTE_BENCHMARK = ROOT / "research" / "experiments" / "execute_benchmark.py"

spec = importlib.util.spec_from_file_location(
    "execute_benchmark",
    EXECUTE_BENCHMARK,
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

infer_decision = module.infer_decision


CONFIG_PATH = ROOT / "research" / "experiments" / "baseline_config.json"
BENCHMARK_PATH = ROOT / "research" / "aegisbench" / "splits" / "development_v1.json"
RELATIONSHIPS_PATH = ROOT / "research" / "experiments" / "metamorphic" / "relationships.json"
OUTPUT_PATH = ROOT / "research" / "experiments" / "results" / "metamorphic.csv"


BASES = {
    "INV01": "S080",
    "INV02": "S080",
    "INV03": "S080",
    "SEC01": "S080",
    "SEC02": "S011",
}

def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def request(config: dict, case: dict, parameters: dict) -> dict:
    endpoint = config["endpoints"]["gateway"]["base_url"]
    url = f"{endpoint}/tools/{case['tool']}/{case['action']}"

    body = json.dumps(
        parameters,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    headers = {
        config["request"]["agent_header"]: case["agent"],
        "Content-Type": config["request"]["content_type"],
    }

    req = Request(url, data=body, headers=headers, method="POST")

    started = time.perf_counter()

    try:
        with urlopen(req, timeout=float(config["request"]["timeout_seconds"])) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            headers_out = dict(response.headers.items())
            status = response.status

    except HTTPError as exc:
        status = exc.code
        headers_out = dict(exc.headers.items()) if exc.headers else {}
        response_body = exc.read().decode("utf-8", errors="replace")

    except (URLError, TimeoutError) as exc:
        return {
            "decision": "UNKNOWN",
            "status": None,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "error": str(exc),
            "body": "",
        }

    decision = infer_decision(status, response_body, headers_out)

    return {
        "decision": decision,
        "status": status,
        "latency_ms": (time.perf_counter() - started) * 1000,
        "error": "",
        "body": response_body,
    }


def transform(case: dict, transformation: str) -> dict:
    out = json.loads(json.dumps(case))
    params = out["parameters"]

    if transformation == "INV01":
        out["parameters"] = dict(reversed(list(params.items())))

    elif transformation == "INV02":
        # Formatting is a wire-level property. Parameters remain identical;
        # request() serializes them with alternate whitespace below.
        out["_metamorphic_formatting"] = True

    elif transformation == "INV03":
        out["parameters"] = {
            **params,
            "_irrelevant": "metamorphic-test",
        }

    elif transformation == "SEC01":
        out["parameters"]["amount"] = 5001

    elif transformation == "SEC02":
        out["parameters"]["path"] = "/hr-docs/../finance/foo.txt"

    else:
        raise ValueError(transformation)

    return out


def request_with_formatting(config: dict, case: dict) -> dict:
    """INV02: same semantic JSON, different wire formatting."""

    endpoint = config["endpoints"]["gateway"]["base_url"]
    url = f"{endpoint}/tools/{case['tool']}/{case['action']}"

    params = case["parameters"]

    body = (
        "{\n"
        + ",\n".join(
            f'  {json.dumps(k)} : {json.dumps(v, ensure_ascii=False)}'
            for k, v in params.items()
        )
        + "\n}"
    ).encode("utf-8")

    headers = {
        config["request"]["agent_header"]: case["agent"],
        "Content-Type": config["request"]["content_type"],
    }

    req = Request(url, data=body, headers=headers)
    started = time.perf_counter()

    try:
        with urlopen(req, timeout=float(config["request"]["timeout_seconds"])) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status = response.status
            response_headers = dict(response.headers.items())
    except HTTPError as exc:
        status = exc.code
        response_body = exc.read().decode("utf-8", errors="replace")
        response_headers = dict(exc.headers.items()) if exc.headers else {}
    except (URLError, TimeoutError) as exc:
        return {
            "decision": "UNKNOWN",
            "status": None,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "error": str(exc),
            "body": "",
        }

    return {
        "decision": infer_decision(status, response_body, response_headers),
        "status": status,
        "latency_ms": (time.perf_counter() - started) * 1000,
        "error": "",
        "body": response_body,
    }


def main() -> int:
    config = load_json(CONFIG_PATH)
    benchmark = load_json(BENCHMARK_PATH)
    relationships = load_json(RELATIONSHIPS_PATH)

    scenarios = {s["id"]: s for s in benchmark["scenarios"]}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    rows = []

    for rel in relationships["transformations"]:
        rel_id = rel["id"]
        base_id = BASES.get(rel_id)

        if not base_id:
            raise ValueError(f"No base configured for {rel_id}")

        base = scenarios[base_id]

        base_result = request(config, base, base["parameters"])

        if rel_id == "INV02":
            transformed_result = request_with_formatting(config, base)
        else:
            transformed = transform(base, rel_id)
            transformed_result = request(
                config,
                transformed,
                transformed["parameters"],
            )

        if rel["expected_relationship"] == "same":
            passed = base_result["decision"] == transformed_result["decision"]

        elif rel["expected_relationship"] == "flip_to_deny":
            passed = (
                base_result["decision"] == "ALLOW"
                and transformed_result["decision"] == "DENY"
            )

        else:
            raise ValueError(
                f"Unknown relationship: {rel['expected_relationship']}"
            )

        rows.append({
            "transformation_id": rel_id,
            "type": rel["type"],
            "base_scenario_id": base_id,
            "expected_relationship": rel["expected_relationship"],
            "base_decision": base_result["decision"],
            "transformed_decision": transformed_result["decision"],
            "passed": passed,
            "base_status": base_result["status"],
            "transformed_status": transformed_result["status"],
            "base_latency_ms": base_result["latency_ms"],
            "transformed_latency_ms": transformed_result["latency_ms"],
        })

    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {OUTPUT_PATH}")

    invariant = [
        r for r in rows
        if r["type"] == "invariant"
    ]

    security = [
        r for r in rows
        if r["type"] == "security_sensitive"
    ]

    print(
        "invariants:",
        sum(r["passed"] for r in invariant),
        "/",
        len(invariant),
        "passed",
    )

    print(
        "security-sensitive:",
        sum(r["passed"] for r in security),
        "/",
        len(security),
        "passed",
    )

    for r in rows:
        print(
            r["transformation_id"],
            r["base_scenario_id"],
            r["base_decision"],
            "->",
            r["transformed_decision"],
            "PASS" if r["passed"] else "FAIL",
        )

    if not all(r["passed"] for r in invariant):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
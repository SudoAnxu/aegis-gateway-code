#!/usr/bin/env python3
"""Dry-run request builder for the Aegis governance benchmark.

This version never contacts any service. It validates the frozen
benchmark and prints the exact request representation for each system.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "baseline_config.json"
DEFAULT_BENCHMARK = ROOT.parent / "benchmarks" / "benchmark_v0.1.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")

    return data


def canonical_hash(data: dict[str, Any]) -> str:
    payload = dict(data)
    payload.pop("content_sha256", None)

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_request(
    case: dict[str, Any],
    system: str,
    config: dict[str, Any],
) -> dict[str, Any]:

    endpoints = config["endpoints"]

    tool = case["tool"]
    action = case["action"]

    # ------------------------------------------------------------------
    # B0: direct execution
    # ------------------------------------------------------------------
    if system == "B0_direct":

        # Some benchmark cases intentionally reference an undeclared
        # tool. There is no physical endpoint for such a tool.
        # Represent this explicitly instead of crashing the runner.
        if tool not in endpoints:

            return {
                "system": system,
                "scenario_id": case["scenario_id"],
                "method": "POST",
                "url": None,
                "headers": {
                    config["request"]["agent_header"]:
                        case["agent"],
                    "Content-Type":
                        config["request"]["content_type"],
                },
                "json": case["parameters"],
                "expected_decision":
                    case["expected_decision"],
                "execution_status":
                    "NO_ENDPOINT",
                "execution_note":
                    "Benchmark references an undeclared tool; "
                    "no direct service endpoint exists."
            }

        base_url = endpoints[tool]["base_url"]
        path = f"/{action}"

    # ------------------------------------------------------------------
    # B1: coarse-grained RBAC
    # ------------------------------------------------------------------
    elif system == "B1_rbac":

        base_url = endpoints["gateway"]["base_url"]
        path = f"/research/rbac/tools/{tool}/{action}"

    # ------------------------------------------------------------------
    # B2: Aegis
    # ------------------------------------------------------------------
    elif system == "B2_aegis":

        base_url = endpoints["gateway"]["base_url"]
        path = f"/tools/{tool}/{action}"

    else:
        raise ValueError(
            f"Unknown system: {system}"
        )

    return {
        "system": system,
        "scenario_id": case["scenario_id"],
        "method": "POST",
        "url": base_url + path,
        "headers": {
            config["request"]["agent_header"]:
                case["agent"],
            "Content-Type":
                config["request"]["content_type"],
        },
        "json": case["parameters"],
        "expected_decision":
            case["expected_decision"],
        "execution_status":
            "READY"
    }

def main() -> int:

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    parser.add_argument(
        "--benchmark",
        type=Path,
        default=DEFAULT_BENCHMARK,
    )

    parser.add_argument(
        "--system",
        choices=[
            "B0_direct",
            "B1_rbac",
            "B2_aegis",
        ],
        default=None,
    )

    args = parser.parse_args()

    config = load_json(args.config)
    benchmark = load_json(args.benchmark)

    scenarios = benchmark.get("scenarios")

    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError(
            "Frozen benchmark must contain a "
            "non-empty scenarios array"
        )

    expected_count = (
        config["benchmark"]["expected_total_count"]
    )

    if len(scenarios) != expected_count:
        raise ValueError(
            f"Benchmark count mismatch: "
            f"expected {expected_count}, "
            f"got {len(scenarios)}"
        )

    actual_hash = canonical_hash(benchmark)

    declared_hash = benchmark.get(
        "content_sha256"
    )

    if declared_hash != actual_hash:
        raise ValueError(
            "Frozen benchmark hash mismatch: "
            f"declared={declared_hash}, "
            f"calculated={actual_hash}"
        )

    systems = (
        [args.system]
        if args.system
        else [
            "B0_direct",
            "B1_rbac",
            "B2_aegis",
        ]
    )

    print(
        "DRY RUN — no network requests will be sent"
    )

    print(
        f"Benchmark version: "
        f"{benchmark.get('benchmark_version')}"
    )

    print(
        f"Benchmark scenarios: "
        f"{len(scenarios)}"
    )

    print(
        f"Benchmark SHA-256: "
        f"{actual_hash}"
    )

    print()

    for system in systems:

        print(f"=== {system} ===")

        for case in scenarios:

            request = build_request(
                case,
                system,
                config,
            )

            print(
                json.dumps(
                    request,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
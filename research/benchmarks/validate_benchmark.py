#!/usr/bin/env python3
"""Validate Aegis research benchmark files without consulting Aegis."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA = ROOT / "schema.json"
DEFAULT_BENCHMARK = ROOT / "seed_cases.json"

CATEGORIES = {
    "legitimate",
    "unauthorized_tool",
    "unauthorized_action",
    "parameter_violation",
    "path_violation",
    "identity_violation",
    "malformed",
}
REASONS = {
    "authorized",
    "tool_not_allowed",
    "action_not_allowed",
    "parameter_constraint",
    "path_constraint",
    "identity_mismatch",
    "malformed_request",
}
SOURCES = {"seed", "mutation", "held_out", "independent_review"}
DECISIONS = {"ALLOW", "DENY"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return data


def canonical_hash(data: dict[str, Any]) -> str:
    payload = dict(data)
    payload.pop("content_sha256", None)
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate(
    data: dict[str, Any],
    label: str,
    parent_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return [f"{label}: scenarios must be a non-empty array"]

    ids: set[str] = set()
    for index, case in enumerate(scenarios):
        prefix = f"{label}[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix}: scenario must be an object")
            continue

        required = {
            "scenario_id", "category", "agent", "tool", "action",
            "parameters", "expected_decision", "source",
        }
        missing = required - case.keys()
        if missing:
            errors.append(f"{prefix}: missing fields: {sorted(missing)}")
            continue

        sid = case["scenario_id"]
        if not isinstance(sid, str) or not sid:
            errors.append(f"{prefix}: scenario_id must be non-empty string")
        elif sid in ids:
            errors.append(f"{prefix}: duplicate scenario_id: {sid}")
        else:
            ids.add(sid)

        if case["category"] not in CATEGORIES:
            errors.append(f"{prefix}: invalid category {case['category']!r}")
        if case["expected_decision"] not in DECISIONS:
            errors.append(f"{prefix}: invalid decision {case['expected_decision']!r}")
        if case["source"] not in SOURCES:
            errors.append(f"{prefix}: invalid source {case['source']!r}")
        if not isinstance(case["parameters"], dict):
            errors.append(f"{prefix}: parameters must be an object")

        reason = case.get("expected_reason_class")
        if reason is not None and reason not in REASONS:
            errors.append(f"{prefix}: invalid expected_reason_class {reason!r}")
        if case["expected_decision"] == "ALLOW" and reason not in {None, "authorized"}:
            errors.append(f"{prefix}: ALLOW case cannot have denial reason {reason!r}")
        if case["expected_decision"] == "DENY" and reason == "authorized":
            errors.append(f"{prefix}: DENY case cannot use authorized reason")

        parent = case.get("parent_scenario_id")
        if case["source"] == "mutation":
            if not isinstance(parent, str) or not parent:
                errors.append(f"{prefix}: mutation requires parent_scenario_id")
            elif parent == sid:
                errors.append(f"{prefix}: mutation cannot parent itself")
            elif parent_ids is not None and parent not in parent_ids:
                errors.append(f"{prefix}: missing mutation parent {parent!r}")
        elif parent is not None and not isinstance(parent, str):
            errors.append(f"{prefix}: parent_scenario_id must be string or null")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path, nargs="?", default=DEFAULT_BENCHMARK)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--parent-benchmark", type=Path, default=None)
    args = parser.parse_args()

    load_json(args.schema)

    parent_ids: set[str] | None = None
    if args.parent_benchmark is not None:
        parent_data = load_json(args.parent_benchmark)
        parent_scenarios = parent_data.get("scenarios")
        if not isinstance(parent_scenarios, list):
            print("VALIDATION FAILED")
            print("- parent benchmark has no valid scenarios array")
            return 1
        parent_ids = {
            case["scenario_id"]
            for case in parent_scenarios
            if isinstance(case, dict) and isinstance(case.get("scenario_id"), str)
        }

    data = load_json(args.benchmark)
    errors = validate(data, args.benchmark.name, parent_ids)

    declared_hash = data.get("content_sha256")
    calculated_hash = canonical_hash(data)
    if declared_hash is not None and declared_hash != calculated_hash:
        errors.append("content_sha256 does not match canonical benchmark content")

    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("VALIDATION PASSED")
    print(f"Scenarios: {len(data['scenarios'])}")
    print(f"Benchmark version: {data.get('benchmark_version')}")
    print(f"SHA-256: {calculated_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

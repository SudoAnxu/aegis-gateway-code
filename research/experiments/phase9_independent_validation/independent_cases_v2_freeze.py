#!/usr/bin/env python3
"""Freeze Track-B v2 cases by validating schema and computing content SHA-256.

This script intentionally does not invoke Aegis or aegisbench.oracle. Run it
before any oracle comparison. The output is copied verbatim to
independent_cases_v2.json and the content hash is recorded separately.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "independent_cases_v2.json"

REQUIRED = {
    "id", "category", "agent", "tool", "action", "parameters", "history",
    "expected_decision", "reason", "independent_labeler_version",
}
FORBIDDEN = {"oracle_expected", "oracle_reason", "expected", "parent_scenario_id", "mutation_operator"}
TARGETS = {
    "legitimate": 40,
    "parameter_constraints": 55,
    "identity_violation": 45,
    "action_authorization": 40,
    "path_constraints": 40,
    "malformed": 55,
    "unauthorized_tool": 15,
    "stateful_sequence": 10,
}


def canonical_without_hash(data: dict) -> bytes:
    data = dict(data)
    data.pop("content_sha256", None)
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    cases = data.get("scenarios")
    if not isinstance(cases, list) or len(cases) != 300:
        raise SystemExit("independent_cases_v2.json must contain exactly 300 scenarios")

    ids = []
    counts = {k: 0 for k in TARGETS}
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            raise SystemExit(f"case {index} is not an object")
        missing = REQUIRED - case.keys()
        extra = FORBIDDEN & case.keys()
        if missing:
            raise SystemExit(f"case {index} missing fields: {sorted(missing)}")
        if extra:
            raise SystemExit(f"case {index} contains forbidden fields: {sorted(extra)}")
        if case["id"] in ids:
            raise SystemExit(f"duplicate id: {case['id']}")
        ids.append(case["id"])
        if case["expected_decision"] not in {"ALLOW", "DENY"}:
            raise SystemExit(f"invalid decision for {case['id']}")
        if not isinstance(case["history"], list):
            raise SystemExit(f"history must be a list for {case['id']}")
        if case["category"] not in TARGETS:
            raise SystemExit(f"unexpected category for {case['id']}: {case['category']}")
        counts[case["category"]] += 1

    if counts != TARGETS:
        raise SystemExit(f"category counts mismatch: {counts} != {TARGETS}")

    content_sha256 = hashlib.sha256(canonical_without_hash(data)).hexdigest()
    data["content_sha256"] = content_sha256
    SOURCE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"scenario_count: {len(cases)}")
    print(f"category_counts: {counts}")
    print(f"content_sha256: {content_sha256}")
    print(f"wrote: {SOURCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

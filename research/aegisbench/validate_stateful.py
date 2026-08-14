#!/usr/bin/env python3
"""Validate a stateful AegisBench result artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--benchmark", type=Path, required=True)
    args = parser.parse_args()

    result = load(args.result)
    benchmark = load(args.benchmark)

    assert result["experiment_version"] == "stateful-0.1"
    assert result["benchmark"]["sha256"] == benchmark["content_sha256"]
    assert result["benchmark"]["version"] == benchmark["version"]

    expected_cases = [s for s in benchmark["scenarios"] if s.get("category") == "stateful_sequence"]
    assert result["summary"]["cases"] == len(expected_cases)
    assert result["summary"]["evaluations"] == len(expected_cases) * result["repetitions"]

    ids = {s["id"] for s in expected_cases}
    seen = []
    for record in result["records"]:
        assert record["scenario_id"] in ids
        assert isinstance(record["history"], list)
        seen.append((record["repetition"], record["scenario_id"]))

    expected_pairs = {
        (rep, scenario_id)
        for rep in range(1, result["repetitions"] + 1)
        for scenario_id in ids
    }
    assert set(seen) == expected_pairs
    assert len(seen) == len(set(seen))

    print("AegisBench stateful validation PASS")
    print("cases:", len(expected_cases))
    print("repetitions:", result["repetitions"])
    print("evaluations:", result["summary"]["evaluations"])
    print("status:", result["status"])
    print("transport_error_rate:", result["summary"]["transport_error_rate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

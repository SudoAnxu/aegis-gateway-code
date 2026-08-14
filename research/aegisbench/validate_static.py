#!/usr/bin/env python3
"""Validate a frozen single-request AegisBench release."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from aegisbench.oracle import decide  # noqa: E402


def canonical_hash(data: dict) -> str:
    unsigned = {k: v for k, v in data.items() if k != "content_sha256"}
    raw = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark", type=Path)
    args = parser.parse_args()

    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))

    if benchmark.get("version") != "1.0-static":
        raise ValueError(f"unexpected version: {benchmark.get('version')!r}")

    scenarios = benchmark.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("scenarios must be a list")

    if benchmark.get("scenario_count") != len(scenarios):
        raise ValueError("scenario_count does not match scenarios length")

    actual_hash = canonical_hash(benchmark)
    if benchmark.get("content_sha256") != actual_hash:
        raise ValueError(
            "content hash mismatch: "
            f"declared={benchmark.get('content_sha256')}, calculated={actual_hash}"
        )

    # Expanded cases use the canonical `id` and `expected` fields. Keep the
    # validator aligned with the producer rather than inventing a second schema.
    ids = [s.get("id") for s in scenarios]
    if any(not isinstance(x, str) or not x for x in ids):
        raise ValueError("every scenario must have a non-empty id")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate id detected")

    stateful = [
        s for s in scenarios if s.get("category") == "stateful_sequence"
    ]
    if stateful:
        raise ValueError(f"static benchmark contains {len(stateful)} stateful cases")

    for scenario in scenarios:
        scenario_id = scenario["id"]
        if scenario.get("source") != "generated":
            raise ValueError(f"{scenario_id}: expected generated source")

        expected = scenario.get("expected")
        if expected not in {"ALLOW", "DENY"}:
            raise ValueError(f"{scenario_id}: invalid expected decision")

        oracle_expected, _ = decide(scenario)
        if expected != oracle_expected:
            raise ValueError(
                f"{scenario_id}: oracle mismatch "
                f"expected={expected} oracle={oracle_expected}"
            )

    print("AegisBench static validation PASS")
    print("role:", benchmark.get("role"))
    print("cases:", len(scenarios))
    print("stateful:", len(stateful))
    print("content hash:", actual_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

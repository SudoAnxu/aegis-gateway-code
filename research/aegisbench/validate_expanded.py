"""Validate an expanded AegisBench artifact independently."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
from aegisbench.oracle import decide  # noqa: E402


def content_hash(payload: dict) -> str:
    unsigned = {k: v for k, v in payload.items() if k != "content_sha256"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("--seeds", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    benchmark = json.loads(args.benchmark.read_text())
    seeds = json.loads(args.seeds.read_text())

    assert benchmark["version"] == "1.0-expanded"
    assert benchmark["generator_version"] == "aegisbench-expand-v3"
    assert benchmark["oracle_version"] == "independent-v1"
    assert benchmark["seed_sha256"] == seeds["content_sha256"]
    assert benchmark["seed_scenario_count"] == len(seeds["scenarios"])
    assert benchmark["scenario_count"] == len(benchmark["scenarios"])
    assert benchmark["content_sha256"] == content_hash(benchmark)

    seed_by_id = {x["id"]: x for x in seeds["scenarios"]}
    assert len(seed_by_id) == len(seeds["scenarios"])

    ids = [x["id"] for x in benchmark["scenarios"]]
    assert len(ids) == len(set(ids))

    parents = Counter()
    operators = Counter()
    categories = Counter()
    decisions = Counter()

    for scenario in benchmark["scenarios"]:
        assert scenario["source"] == "generated"
        parent_id = scenario.get("parent_scenario_id")
        assert parent_id in seed_by_id
        assert scenario["id"].startswith(parent_id + "::")
        assert scenario["generator_version"] == "aegisbench-expand-v3"
        if "raw_body" in scenario:
            assert scenario["expected"] == "DENY"
            assert scenario["reason"] == "malformed_request"
        else:
            expected, reason = decide(scenario)
            assert (scenario["expected"], scenario["reason"]) == (expected, reason)
        parents[parent_id] += 1
        operators[scenario["mutation_operator"]] += 1
        categories[scenario["category"]] += 1
        decisions[scenario["expected"]] += 1

    print("AegisBench expanded validation PASS")
    print("role:", benchmark.get("role", "full"))
    print("seeds:", len(seeds["scenarios"]))
    print("generated:", len(benchmark["scenarios"]))
    print("unique parents:", len(parents))
    print("categories:", dict(categories))
    print("decisions:", dict(decisions))
    print("operators:", dict(operators))
    print("content hash:", benchmark["content_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

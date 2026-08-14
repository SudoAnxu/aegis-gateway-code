"""Validate the curated AegisBench seed release independently of Aegis."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from aegisbench.oracle import decide  # noqa: E402

SEED = ROOT / "research" / "aegisbench" / "seed_cases_v1.json"
EXPECTED_COUNTS = {
    "legitimate": 20,
    "identity_violation": 20,
    "action_authorization": 20,
    "parameter_constraints": 25,
    "path_constraints": 20,
    "malformed": 15,
    "unauthorized_tool": 10,
    "stateful_sequence": 20,
}


def main() -> int:
    d = json.loads(SEED.read_text())
    scenarios = d["scenarios"]

    assert d["scenario_count"] == 150
    assert len(scenarios) == 150
    assert len({s["id"] for s in scenarios}) == 150

    counts = Counter(s["category"] for s in scenarios)
    assert counts == Counter(EXPECTED_COUNTS)

    mismatches = []
    for s in scenarios:
        expected, reason = decide(s)
        if (s["expected"], s["reason"]) != (expected, reason):
            mismatches.append((s["id"], s["expected"], expected, s["reason"], reason))

    assert not mismatches, mismatches[:5]

    for s in scenarios:
        assert s["source"] == "curated"
        assert s["generator_version"] == "aegisbench-seed-v1"
        assert isinstance(s["history"], list)
        assert isinstance(s["state"], dict)

    print("AegisBench seed validation PASS")
    print("scenarios:", len(scenarios))
    print("categories:", dict(counts))
    print("oracle agreement: 150/150")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

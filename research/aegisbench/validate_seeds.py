"""Validate the curated AegisBench seed release independently of Aegis."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
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

    # Verify the stored release hash independently of the generator.
    unsigned = {k: v for k, v in d.items() if k != "content_sha256"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == d["content_sha256"]

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

    stateful = [s for s in scenarios if s["category"] == "stateful_sequence"]
    assert len(stateful) == 20
    state_reasons = Counter(s["reason"] for s in stateful)
    assert state_reasons["state_transition"] == 4
    assert state_reasons["state_replay"] == 4
    assert state_reasons["state_precondition"] == 8
    assert state_reasons["state_invalid_transition"] == 4

    print("AegisBench seed validation PASS")
    print("scenarios:", len(scenarios))
    print("categories:", dict(counts))
    print("stateful reasons:", dict(state_reasons))
    print("oracle agreement: 150/150")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

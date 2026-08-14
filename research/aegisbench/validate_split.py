"""Validate AegisBench v1 development/held-out split integrity."""
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
DEV = ROOT / "research" / "aegisbench" / "splits" / "development_v1.json"
HELDOUT = ROOT / "research" / "aegisbench" / "splits" / "heldout_v1.json"


def content_hash(path: Path) -> str:
    data = json.loads(path.read_text())
    unsigned = {k: v for k, v in data.items() if k != "content_sha256"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    seed = json.loads(SEED.read_text())
    dev = json.loads(DEV.read_text())
    heldout = json.loads(HELDOUT.read_text())

    assert seed["scenario_count"] == 150
    assert len(dev["scenarios"]) == 100
    assert len(heldout["scenarios"]) == 50
    assert dev["content_sha256"] == content_hash(DEV)
    assert heldout["content_sha256"] == content_hash(HELDOUT)
    assert dev["source_seed_sha256"] == seed["content_sha256"]
    assert heldout["source_seed_sha256"] == seed["content_sha256"]

    seed_ids = {x["id"] for x in seed["scenarios"]}
    dev_ids = {x["id"] for x in dev["scenarios"]}
    heldout_ids = {x["id"] for x in heldout["scenarios"]}
    assert dev_ids | heldout_ids == seed_ids
    assert not dev_ids & heldout_ids

    for scenario in dev["scenarios"] + heldout["scenarios"]:
        expected, reason = decide(scenario)
        assert (scenario["expected"], scenario["reason"]) == (expected, reason)

    assert Counter(x["category"] for x in heldout["scenarios"]) == Counter({
        "legitimate": 7,
        "identity_violation": 7,
        "action_authorization": 7,
        "parameter_constraints": 8,
        "path_constraints": 7,
        "malformed": 5,
        "unauthorized_tool": 3,
        "stateful_sequence": 7,
    })
    assert Counter(x["reason"] for x in heldout["scenarios"] if x["category"] == "stateful_sequence") == Counter({
        "state_transition": 2,
        "state_replay": 1,
        "state_precondition": 1,
        "state_invalid_transition": 3,
    })

    print("AegisBench split validation PASS")
    print("development:", len(dev["scenarios"]))
    print("heldout:", len(heldout["scenarios"]))
    print("seed-level overlap: 0")
    print("heldout hash:", heldout["content_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

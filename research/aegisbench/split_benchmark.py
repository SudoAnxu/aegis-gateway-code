"""Create a seed-level development/held-out AegisBench split.

The split is performed at the curated-seed level so no generated mutation of a
seed can leak across development and held-out evaluation. The held-out set is
stratified by category and, for stateful seeds, by oracle reason.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
from aegisbench.oracle import decide  # noqa: E402

SEED = ROOT / "research" / "aegisbench" / "seed_cases_v1.json"
OUT_DIR = ROOT / "research" / "aegisbench" / "splits"

# Explicitly define the desired held-out distribution. This table is checked
# against the source benchmark before any files are written.
TARGET_HELDOUT = {
    "legitimate": 7,
    "identity_violation": 7,
    "action_authorization": 7,
    "parameter_constraints": 8,
    "path_constraints": 7,
    "malformed": 5,
    "unauthorized_tool": 3,
}

STATEFUL_HELDOUT = {
    "state_transition": 2,
    "state_replay": 1,
    "state_precondition": 1,
    "state_invalid_transition": 3,
}

EXPECTED_TOTAL = 150
EXPECTED_HELDOUT = 50
EXPECTED_DEVELOPMENT = EXPECTED_TOTAL - EXPECTED_HELDOUT


def canonical_hash(payload: dict) -> str:
    unsigned = {k: v for k, v in payload.items() if k != "content_sha256"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def requested_heldout_count() -> int:
    return sum(TARGET_HELDOUT.values()) + sum(STATEFUL_HELDOUT.values())


def validate_split_targets(source_scenarios: list[dict]) -> None:
    if len(source_scenarios) != EXPECTED_TOTAL:
        raise ValueError(
            f"Expected exactly {EXPECTED_TOTAL} curated seeds, got {len(source_scenarios)}"
        )

    counts = Counter(s["category"] for s in source_scenarios)
    expected_categories = {
        **{k: v for k, v in TARGET_HELDOUT.items()},
        "stateful_sequence": sum(STATEFUL_HELDOUT.values()),
    }

    for category, heldout_count in expected_categories.items():
        available = counts.get(category, 0)
        if heldout_count > available:
            raise ValueError(
                f"Held-out target for {category}={heldout_count} exceeds available seeds={available}"
            )

    if requested_heldout_count() != EXPECTED_HELDOUT:
        raise ValueError(
            "Split configuration error: held-out targets sum to "
            f"{requested_heldout_count()}, expected {EXPECTED_HELDOUT}"
        )

    stateful_counts = Counter(
        s["reason"] for s in source_scenarios if s["category"] == "stateful_sequence"
    )
    for reason, target in STATEFUL_HELDOUT.items():
        if target > stateful_counts.get(reason, 0):
            raise ValueError(
                f"Stateful held-out target for {reason}={target} exceeds available seeds="
                f"{stateful_counts.get(reason, 0)}"
            )


def stratified_split(scenarios: list[dict]) -> tuple[list[dict], list[dict]]:
    validate_split_targets(scenarios)

    groups: dict[tuple[str, str | None], list[dict]] = defaultdict(list)
    for scenario in scenarios:
        reason = scenario["reason"] if scenario["category"] == "stateful_sequence" else None
        groups[(scenario["category"], reason)].append(scenario)

    heldout: list[dict] = []
    development: list[dict] = []

    for (category, reason), items in sorted(groups.items()):
        if category == "stateful_sequence":
            target = STATEFUL_HELDOUT[reason]
        else:
            target = TARGET_HELDOUT[category]

        ordered = sorted(items, key=lambda x: x["id"])
        heldout.extend(ordered[:target])
        development.extend(ordered[target:])

    return development, heldout


def write_release(path: Path, version: str, source: dict, scenarios: list[dict], role: str) -> None:
    payload = {
        "version": version,
        "role": role,
        "source_seed_version": source["version"],
        "source_seed_sha256": source["content_sha256"],
        "generator_version": "aegisbench-split-v1",
        "oracle_version": source["oracle_version"],
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }
    payload["content_sha256"] = canonical_hash(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    source = json.loads(SEED.read_text())
    scenarios = source["scenarios"]
    development, heldout = stratified_split(scenarios)

    assert len(development) + len(heldout) == len(scenarios), (
        len(development),
        len(heldout),
        len(scenarios),
    )
    assert len(scenarios) == EXPECTED_TOTAL
    assert len(development) == EXPECTED_DEVELOPMENT, len(development)
    assert len(heldout) == EXPECTED_HELDOUT, len(heldout)
    assert not ({x["id"] for x in development} & {x["id"] for x in heldout})

    for scenario in development + heldout:
        expected, reason = decide(scenario)
        assert (scenario["expected"], scenario["reason"]) == (expected, reason)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_release(OUT_DIR / "development_v1.json", "1.0-development", source, development, "development")
    write_release(OUT_DIR / "heldout_v1.json", "1.0-heldout", source, heldout, "heldout")

    print("AegisBench split PASS")
    print("development:", len(development))
    print("heldout:", len(heldout))
    print("development categories:", dict(Counter(x["category"] for x in development)))
    print("heldout categories:", dict(Counter(x["category"] for x in heldout)))
    print("heldout stateful reasons:", dict(Counter(x["reason"] for x in heldout if x["category"] == "stateful_sequence")))
    print("heldout hash:", json.loads((OUT_DIR / "heldout_v1.json").read_text())["content_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

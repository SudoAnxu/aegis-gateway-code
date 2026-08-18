#!/usr/bin/env python3

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "research" / "experiments" / "results"
OUTPUT = RESULTS / "evaluation_records_final.csv"

COMMON_FIELDS = [
    "record_id",
    "experiment_family",
    "mutation_id",
    "source_file",
    "timestamp_utc",
    "git_commit",
    "benchmark_version",
    "benchmark_sha256",
    "system",
    "repetition",
    "scenario_id",
    "parent_scenario_id",
    "category",
    "agent",
    "tool",
    "action",
    "expected_decision",
    "actual_decision",
    "classification",
    "status_code",
    "latency_ms",
    "transport_error",
    "url",
    "response_body",
    "response_headers",
    "transaction_id",
    "live_transaction_id",
    "history",
    "history_steps",
    "history_replay_ok",
    "terminal_history",
    "target_executed",
    "expected",
    "expected_reason",
    "actual",
]


def discover_records():
    sources = []

    for family in ("heldout_final", "mutations_final"):
        root = RESULTS / family

        for path in sorted(root.rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue

            records = data.get("records")
            if not isinstance(records, list):
                continue

            mutation_id = None
            if family == "mutations_final":
                rel = path.relative_to(root)
                if rel.parts:
                    mutation_id = rel.parts[0]

            sources.append((family, mutation_id, path, records))

    return sources


def normalize(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    return value


def main():
    sources = discover_records()

    rows = []
    expected_source_counts = {}

    for family, mutation_id, path, records in sources:
        key = (family, mutation_id)
        expected_source_counts[key] = expected_source_counts.get(key, 0) + len(records)

        for index, record in enumerate(records, start=1):
            row = {
                field: normalize(record.get(field))
                for field in COMMON_FIELDS
            }

            row["record_id"] = (
                f"{family}:"
                f"{mutation_id or 'none'}:"
                f"{path.stem}:"
                f"{index:05d}"
            )

            row["experiment_family"] = family
            row["mutation_id"] = mutation_id or ""

            # Preserve exact source provenance.
            row["source_file"] = str(path.relative_to(ROOT))

            rows.append(row)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=COMMON_FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    # Integrity checks.
    assert len(rows) == 75860, (
        f"Expected 75,860 records, got {len(rows)}"
    )

    ids = [r["record_id"] for r in rows]
    assert len(ids) == len(set(ids)), "Duplicate record_id values found"

    heldout = sum(r["experiment_family"] == "heldout_final" for r in rows)
    mutations = sum(r["experiment_family"] == "mutations_final" for r in rows)

    assert heldout == 46980, f"Heldout count mismatch: {heldout}"
    assert mutations == 28880, f"Mutation count mismatch: {mutations}"

    mutation_counts = {}
    for r in rows:
        if r["experiment_family"] == "mutations_final":
            mid = r["mutation_id"]
            mutation_counts[mid] = mutation_counts.get(mid, 0) + 1

    expected_mutations = {
        **{f"M{i:02d}": 1882 for i in range(1, 14)},
        "M18": 1882,
        "M19": 1882,
        "M14": 130,
        "M15": 130,
        "M16": 130,
        "M17": 130,
        "M20": 130,
    }

    assert mutation_counts == expected_mutations, (
        f"Mutation counts mismatch:\n"
        f"expected={expected_mutations}\n"
        f"actual={mutation_counts}"
    )

    print(f"wrote: {OUTPUT}")
    print(f"records: {len(rows):,}")
    print(f"heldout: {heldout:,}")
    print(f"mutations: {mutations:,}")
    print("unique record IDs: PASS")
    print("mutation counts: PASS")
    print("integrity: PASS")


if __name__ == "__main__":
    main()

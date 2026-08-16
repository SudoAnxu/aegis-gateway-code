#!/usr/bin/env python3
"""Validate the Phase 8 mutant catalog and emit a run manifest.

This is intentionally a planning/run-manifest tool. It does not mutate the
clean B2 code. Actual mutant application must happen through explicit,
reversible configuration/build variants.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = ["mutant_id", "description", "stage"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    data = json.loads(args.catalog.read_text(encoding="utf-8"))
    mutants = data.get("mutants", [])
    if len(mutants) < 15 or len(mutants) > 20:
        raise SystemExit(f"Expected 15-20 mutants, found {len(mutants)}")

    rows = []
    ids = []
    for mutant in mutants:
        if not isinstance(mutant, dict):
            raise SystemExit("Each mutant must be an object")
        mutant_id = mutant.get("id")
        description = mutant.get("description")
        stage = mutant.get("stage")
        if not isinstance(mutant_id, str) or not mutant_id:
            raise SystemExit("Mutant IDs must be unique and non-empty")
        if not isinstance(description, str) or not description:
            raise SystemExit(f"Mutant {mutant_id} has no description")
        if not isinstance(stage, str) or not stage:
            raise SystemExit(f"Mutant {mutant_id} has no stage")
        ids.append(mutant_id)
        rows.append({
            "mutant_id": mutant_id,
            "description": description,
            "stage": stage,
        })

    if len(ids) != len(set(ids)):
        raise SystemExit("Mutant IDs must be unique and non-empty")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Validated {len(rows)} mutants")
    print(f"Manifest written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

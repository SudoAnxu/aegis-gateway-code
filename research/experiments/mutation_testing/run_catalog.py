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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    data = json.loads(args.catalog.read_text(encoding="utf-8"))
    mutants = data.get("mutants", [])
    if len(mutants) < 15 or len(mutants) > 20:
        raise SystemExit(f"Expected 15-20 mutants, found {len(mutants)}")

    ids = [m.get("id") for m in mutants]
    if len(ids) != len(set(ids)) or any(not x for x in ids):
        raise SystemExit("Mutant IDs must be unique and non-empty")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["mutant_id", "description", "stage"])
        writer.writeheader()
        writer.writerows(mutants)

    print(f"Validated {len(mutants)} mutants")
    print(f"Manifest written to {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

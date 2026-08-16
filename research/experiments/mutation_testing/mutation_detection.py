#!/usr/bin/env python3
"""Compare mutant aggregate results against clean B2.

The script is intentionally configuration-agnostic: each mutant run is
expected to live under --mutants-root/<mutant-id>/ with a B2 aggregate JSON.
It records whether any security metric worsened enough to demonstrate that
at least one benchmark case caught the mutant.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_delta(clean: dict[str, Any], mutant: dict[str, Any]) -> tuple[bool, float, list[str]]:
    clean_f1 = float(clean["summary"]["metrics"]["f1"]["mean"])
    mutant_f1 = float(mutant["summary"]["metrics"]["f1"]["mean"])
    delta = mutant_f1 - clean_f1
    caught: list[str] = []

    for path in mutant.get("replicate_files", []):
        # Scenario-level evidence is preserved in replicate JSON files; the
        # optional scan below is intentionally tolerant of absent files.
        p = Path(mutant.get("_aggregate_dir", "")) / path
        if not p.exists():
            continue
        data = load(p)
        for record in data.get("records", []):
            if record.get("classification") in {"false_positive", "false_negative"}:
                caught.append(str(record.get("scenario_id")))

    return bool(caught) or delta < 0.0, delta, sorted(set(caught))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--mutants-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    clean = load(args.clean)
    rows: list[dict[str, Any]] = []
    for aggregate in sorted(args.mutants_root.glob("*/b2_aegis_aggregate.json")):
        mutant = load(aggregate)
        mutant["_aggregate_dir"] = str(aggregate.parent)
        mutant_id = aggregate.parent.name
        detected, delta, caught = summarize_delta(clean, mutant)
        rows.append({
            "mutant_id": mutant_id,
            "description": mutant.get("description", mutant_id),
            "detected": str(detected).lower(),
            "scenario_ids_that_caught_it": ";".join(caught),
            "f1_delta_vs_b2": delta,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "mutant_id",
                "description",
                "detected",
                "scenario_ids_that_caught_it",
                "f1_delta_vs_b2",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} mutation rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

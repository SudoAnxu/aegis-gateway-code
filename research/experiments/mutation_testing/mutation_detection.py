#!/usr/bin/env python3
"""Compare mutant results against clean B2, including stateful mutations."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def f1_mean(result: dict[str, Any]) -> float:
    summary = result.get("summary", {})
    metrics = summary.get("metrics")

    if isinstance(metrics, dict) and isinstance(metrics.get("f1"), dict):
        return float(metrics["f1"]["mean"])

    if "f1" in summary:
        return float(summary["f1"])

    raise KeyError("result does not contain a supported F1 metric schema")


def summarize_delta(
    clean: dict[str, Any],
    mutant: dict[str, Any],
) -> tuple[bool, float, list[str]]:
    clean_f1 = f1_mean(clean)
    mutant_f1 = f1_mean(mutant)
    delta = mutant_f1 - clean_f1

    caught: list[str] = []

    aggregate_dir = Path(mutant.get("_aggregate_dir", ""))

    for path in mutant.get("replicate_files", []):
        p = aggregate_dir / path
        if not p.exists():
            continue

        data = load(p)

        for record in data.get("records", []):
            if record.get("classification") in {"false_positive", "false_negative"}:
                caught.append(str(record.get("scenario_id")))

    return bool(caught) or delta < 0.0, delta, sorted(set(caught))


def summarize_stateful(
    mutant: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Stateful mutations are evaluated by stateful_runner.py.

    run_mutations.py records the authoritative mutation outcome as:
        mutation_status = KILLED | SURVIVED | ERROR

    F1-delta comparison is not applicable because stateful results do not
    use the ordinary repeated aggregate schema.
    """
    status = mutant.get("mutation_status")

    detected = status == "KILLED"

    caught: list[str] = []

    for record in mutant.get("records", []):
        if record.get("classification") in {"false_positive", "false_negative"}:
            scenario_id = record.get("scenario_id")
            if scenario_id is not None:
                caught.append(str(scenario_id))

    return detected, sorted(set(caught))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--mutants-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    clean = load(args.clean)
    rows: list[dict[str, Any]] = []

    # Ordinary request/policy mutants.
    for aggregate in sorted(args.mutants_root.glob("*/b2_aegis_aggregate.json")):
        mutant = load(aggregate)
        mutant["_aggregate_dir"] = str(aggregate.parent)

        mutant_id = aggregate.parent.name
        detected, delta, caught = summarize_delta(clean, mutant)

        rows.append(
            {
                "mutant_id": mutant_id,
                "description": mutant.get("description", mutant_id),
                "detected": str(detected).lower(),
                "scenario_ids_that_caught_it": ";".join(caught),
                "f1_delta_vs_b2": delta,
            }
        )

    # Stateful mutants (M14-M17/M20).
    for stateful in sorted(args.mutants_root.glob("*/b2_aegis_stateful.json")):
        mutant = load(stateful)

        mutant_id = stateful.parent.name
        detected, caught = summarize_stateful(mutant)

        rows.append(
            {
                "mutant_id": mutant_id,
                "description": mutant.get("description", mutant_id),
                "detected": str(detected).lower(),
                "scenario_ids_that_caught_it": ";".join(caught),
                "f1_delta_vs_b2": "",
            }
        )

    rows.sort(key=lambda row: row["mutant_id"])

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
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    detected_count = sum(row["detected"] == "true" for row in rows)

    print(f"Wrote {len(rows)} mutation rows to {args.output}")
    print(f"Detected: {detected_count}/{len(rows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

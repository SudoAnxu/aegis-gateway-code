#!/usr/bin/env python3
"""Run the declared mutation catalog with the appropriate benchmark runner.

Request/policy mutants use the repeated single-request benchmark runner.
State mutants use the stateful sequence runner so history-dependent mutations
are evaluated against ordered payment histories rather than isolated requests.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

STATE_STAGES = {"state"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    args = parser.parse_args()

    if args.repetitions < 1:
        raise ValueError("--repetitions must be >= 1")

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    mutants = catalog.get("mutants", [])
    args.output_root.mkdir(parents=True, exist_ok=True)

    for mutant in mutants:
        mutant_id = mutant["id"]
        stage = mutant.get("stage")
        output_dir = args.output_root / mutant_id
        output_dir.mkdir(parents=True, exist_ok=True)

        if stage in STATE_STAGES:
            output_path = output_dir / "b2_aegis_stateful.json"
            command = [
                sys.executable,
                "research/aegisbench/stateful_runner.py",
                "--system", "B2_aegis",
                "--repetitions", str(args.repetitions),
                "--benchmark", str(args.benchmark),
                "--mutation-id", mutant_id,
                "--output", str(output_path),
            ]
        else:
            if args.repetitions < 2:
                raise ValueError(
                    f"{mutant_id} ({stage}) uses run_repeated.py and requires --repetitions >= 2"
                )
            command = [
                sys.executable,
                "research/experiments/run_repeated.py",
                "--system", "B2_aegis",
                "--repetitions", str(args.repetitions),
                "--benchmark", str(args.benchmark),
                "--mutation-id", mutant_id,
                "--output-dir", str(output_dir),
            ]

        print(f"[{mutant_id}] stage={stage}: running")

        if stage in STATE_STAGES:
            completed = subprocess.run(command)
            if completed.returncode not in (0, 2):
                raise RuntimeError(
                    f"{mutant_id}: stateful runner failed with exit code "
                    f"{completed.returncode}"
                )
        else:
            subprocess.run(command, check=True)
        if stage in STATE_STAGES:
            result_path = output_dir / "b2_aegis_stateful.json"
        else:
            result_path = output_dir / "b2_aegis_aggregate.json"

        if result_path.exists():
            data = json.loads(result_path.read_text(encoding="utf-8"))
            summary = data.get("summary", {})

            if stage in STATE_STAGES:
                transport_errors = summary.get("transport_error_rate", 0)
                history_failures = summary.get("history_replay_failures", 0)
                unclassified = summary.get("unclassified", 0)
                false_positive = summary.get("false_positive", 0)
                false_negative = summary.get("false_negative", 0)

                if transport_errors or unclassified:
                    mutation_status = "ERROR"
                elif history_failures or false_positive or false_negative:
                    mutation_status = "KILLED"
                else:
                    mutation_status = "SURVIVED"

                data["mutation_status"] = mutation_status
            data["mutant_id"] = mutant_id
            data["description"] = mutant.get("description", mutant_id)
            data["stage"] = stage
            result_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

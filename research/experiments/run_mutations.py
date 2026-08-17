#!/usr/bin/env python3
"""Run a declared mutation catalog through the existing repeated runner.

This orchestrator assumes each mutant is represented by a reversible gateway
configuration/build variant selected by the requested config file. It never
modifies the clean benchmark or clean B2 source.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    # parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    mutants = catalog.get("mutants", [])
    args.output_root.mkdir(parents=True, exist_ok=True)

    for mutant in mutants:
        mutant_id = mutant["id"]

        output_dir = args.output_root / mutant_id
        command = [
    sys.executable,
    "research/experiments/run_repeated.py",
    "--system", "B2_aegis",
    "--repetitions", str(args.repetitions),
    "--benchmark", str(args.benchmark),
    "--mutation-id", mutant_id,
    "--output-dir", str(output_dir),
]
        print(f"[{mutant_id}] running")
        subprocess.run(command, check=True)

        aggregate = output_dir / "b2_aegis_aggregate.json"
        if aggregate.exists():
            data = json.loads(aggregate.read_text(encoding="utf-8"))
            data["mutant_id"] = mutant_id
            data["description"] = mutant.get("description", mutant_id)
            aggregate.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())

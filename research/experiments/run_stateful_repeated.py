#!/usr/bin/env python3
"""Run the dedicated stateful benchmark repeatedly, including a mutant header."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATEFUL = ROOT.parent / "aegisbench" / "stateful_runner.py"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=["B0_direct", "B1_rbac", "B2_aegis"], required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mutation-id", default=None)
    args = parser.parse_args()
    if args.repetitions < 1:
        raise ValueError("--repetitions must be >= 1")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for repetition in range(1, args.repetitions + 1):
        output = args.output_dir / f"stateful_{args.system.lower()}_rep{repetition:02d}.json"
        command = [
            sys.executable,
            str(STATEFUL),
            "--system", args.system,
            "--repetitions", "1",
            "--benchmark", str(args.benchmark),
            "--output", str(output),
        ]
        if args.mutation_id:
            command.extend(["--mutation-id", args.mutation_id])
        print(f"[{args.system}] stateful repetition {repetition}: running...")
        subprocess.run(command, check=True)
        results.append(load(output))

    aggregate = {
        "experiment_version": results[0].get("experiment_version"),
        "system": args.system,
        "benchmark": results[0].get("benchmark"),
        "repetitions": args.repetitions,
        "mutation_id": args.mutation_id,
        "statistics_unit": "complete stateful benchmark repetition",
        "replicate_files": [p.name for p in sorted(args.output_dir.glob("stateful_*.json"))],
        "summary": {
            "history_replay_failures": sum(r.get("summary", {}).get("history_replay_failures", 0) for r in results),
            "transport_error_rate_mean": sum(r.get("summary", {}).get("transport_error_rate", 0.0) for r in results) / len(results),
            "true_positive_mean": sum(r.get("summary", {}).get("true_positive", 0) for r in results) / len(results),
            "true_negative_mean": sum(r.get("summary", {}).get("true_negative", 0) for r in results) / len(results),
            "false_positive_mean": sum(r.get("summary", {}).get("false_positive", 0) for r in results) / len(results),
            "false_negative_mean": sum(r.get("summary", {}).get("false_negative", 0) for r in results) / len(results),
        },
    }
    (args.output_dir / "stateful_aggregate.json").write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

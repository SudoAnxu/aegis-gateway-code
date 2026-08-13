#!/usr/bin/env python3
"""Build a deterministic frozen benchmark from seed and mutation cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonical_hash(data: dict) -> str:
    payload = dict(data)
    payload.pop("content_sha256", None)

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--seed", type=Path, default=ROOT / "seed_cases.json")
    parser.add_argument("--mutations", type=Path, default=ROOT / "generated_cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark_v0.1.json")
    parser.add_argument("--version", default=None)

    args = parser.parse_args()

    seed = load(args.seed)
    mutations = load(args.mutations)

    seed_cases = seed.get("scenarios", [])
    mutation_cases = mutations.get("scenarios", [])
    scenarios = seed_cases + mutation_cases

    ids = [case.get("scenario_id") for case in scenarios]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate scenario_id detected; benchmark not frozen.")

    version = args.version or seed.get("benchmark_version") or "0.1"

    output = {
        "benchmark_version": version,
        "seed_version": seed.get("benchmark_version"),
        "mutation_version": mutations.get("benchmark_version"),
        "seed_count": len(seed_cases),
        "mutation_count": len(mutation_cases),
        "total_count": len(scenarios),
        "source_files": [args.seed.name, args.mutations.name],
        "scenarios": scenarios,
    }

    output["content_sha256"] = canonical_hash(output)

    args.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Frozen benchmark: {args.output}")
    print(f"Seed cases: {output['seed_count']}")
    print(f"Mutation cases: {output['mutation_count']}")
    print(f"Total cases: {output['total_count']}")
    print(f"Benchmark version: {output['benchmark_version']}")
    print(f"SHA-256: {output['content_sha256']}")


if __name__ == "__main__":
    main()

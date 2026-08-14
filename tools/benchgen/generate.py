#!/usr/bin/env python3
"""Expand curated AegisBench seeds deterministically.

The generator never derives expected labels from Aegis. Labels are recomputed
through tools.benchgen.oracle so the benchmark remains independent of the
implementation under test.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from pathlib import Path

from oracle import evaluate

GENERATOR_VERSION = "0.1"


def mutate_case(case: dict, rng: random.Random) -> list[dict]:
    out: list[dict] = []
    category = case["category"]
    params = case.get("parameters", {})

    if category == "parameter_constraints" and "amount" in params:
        amount = params["amount"]
        for operator, value in (
            ("amount_min_minus_one", -1),
            ("amount_min", 0),
            ("amount_max_minus_one", 4999),
            ("amount_max", 5000),
            ("amount_max_plus_one", 5001),
        ):
            c = copy.deepcopy(case)
            c["parameters"]["amount"] = value
            c["parent_scenario_id"] = case["id"]
            c["mutation_operator"] = operator
            c["generator_version"] = GENERATOR_VERSION
            c["expected"], c["reason"] = evaluate(c)
            out.append(c)

        c = copy.deepcopy(case)
        c["parameters"].pop("amount", None)
        c["parent_scenario_id"] = case["id"]
        c["mutation_operator"] = "amount_missing"
        c["generator_version"] = GENERATOR_VERSION
        c["expected"], c["reason"] = evaluate(c)
        out.append(c)

        c = copy.deepcopy(case)
        c["parameters"]["amount"] = "5000"
        c["parent_scenario_id"] = case["id"]
        c["mutation_operator"] = "amount_wrong_type"
        c["generator_version"] = GENERATOR_VERSION
        c["expected"], c["reason"] = evaluate(c)
        out.append(c)

    if category == "path_constraints" and "path" in params:
        for operator, value in (
            ("path_traversal", "/hr-docs/../finance/reports/q2.txt"),
            ("path_prefix_collision", "/hr-docs2/foo.txt"),
            ("path_sibling_collision", "/hr-documents/foo.txt"),
            ("path_valid", "/hr-docs/foo.txt"),
        ):
            c = copy.deepcopy(case)
            c["parameters"]["path"] = value
            c["parent_scenario_id"] = case["id"]
            c["mutation_operator"] = operator
            c["generator_version"] = GENERATOR_VERSION
            c["expected"], c["reason"] = evaluate(c)
            out.append(c)

    if category in {"legitimate", "parameter_constraints", "path_constraints"}:
        c = copy.deepcopy(case)
        c["parameters"] = dict(reversed(list(c.get("parameters", {}).items())))
        c["parent_scenario_id"] = case["id"]
        c["mutation_operator"] = "field_order_reversal"
        c["generator_version"] = GENERATOR_VERSION
        c["expected"], c["reason"] = evaluate(c)
        out.append(c)

    rng.shuffle(out)
    return out


def canonical_sha256(cases: list[dict]) -> str:
    payload = json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260814)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    seeds = []
    for path in sorted(args.seeds.glob("*.json")):
        seeds.extend(json.loads(path.read_text()))

    expanded = []
    for case in seeds:
        expected, reason = evaluate(case)
        if case.get("expected") != expected or case.get("reason") != reason:
            raise SystemExit(f"seed oracle mismatch: {case['id']}: {expected}/{reason}")
        expanded.append(case)
        expanded.extend(mutate_case(case, rng))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(expanded, indent=2, sort_keys=True) + "\n")
    print(f"seeds={len(seeds)} generated={len(expanded)}")
    print(f"generator_version={GENERATOR_VERSION} rng_seed={args.seed}")
    print(f"sha256={canonical_sha256(expanded)}")


if __name__ == "__main__":
    main()

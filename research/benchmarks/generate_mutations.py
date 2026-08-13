#!/usr/bin/env python3
"""Deterministically generate adversarial benchmark mutations from valid seeds.

The generator never consults Aegis' implementation or its decisions. It only
mutates legitimate seed requests into deliberately invalid requests whose
expected DENY labels follow the declared policy specification.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "seed_cases.json"
DEFAULT_OUTPUT = ROOT / "generated_cases.json"


def clone_case(case: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    out = copy.deepcopy(case)
    out["scenario_id"] = scenario_id
    out["source"] = "mutation"
    out["parent_scenario_id"] = case["scenario_id"]
    out["review_status"] = "pending"
    return out


def add(generated: list[dict[str, Any]], case: dict[str, Any], suffix: str,
        category: str, reason: str, notes: str) -> None:
    scenario = clone_case(case, f"{case['scenario_id']}-{suffix}")
    scenario["category"] = category
    scenario["expected_decision"] = "DENY"
    scenario["expected_reason_class"] = reason
    scenario["notes"] = notes
    generated.append(scenario)


def mutate(case: dict[str, Any]) -> list[dict[str, Any]]:
    # Mutations are generated only from legitimate seeds. This prevents
    # repeatedly mutating an already-invalid case into duplicate semantics.
    if case.get("category") != "legitimate":
        return []

    params = case["parameters"]
    generated: list[dict[str, Any]] = []

    if case["tool"] == "payments":
        # Amount violation: make a valid amount exceed the declared 5000 limit.
        if isinstance(params.get("amount"), (int, float)) and not isinstance(params.get("amount"), bool):
            m = clone_case(case, f"{case['scenario_id']}-M01")
            m["parameters"]["amount"] = 5001
            m["category"] = "parameter_violation"
            m["expected_decision"] = "DENY"
            m["expected_reason_class"] = "parameter_constraint"
            m["notes"] = "Mutation: amount exceeds the declared 5000 maximum."
            generated.append(m)

        # Currency violation: replace an allowed currency with a disallowed one.
        if "currency" in params:
            m = clone_case(case, f"{case['scenario_id']}-M02")
            m["parameters"]["currency"] = "GBP"
            m["category"] = "parameter_violation"
            m["expected_decision"] = "DENY"
            m["expected_reason_class"] = "parameter_constraint"
            m["notes"] = "Mutation: currency is outside the declared USD/EUR allowlist."
            generated.append(m)

        # Action violation: keep the valid tool and identity but request an undeclared action.
        m = clone_case(case, f"{case['scenario_id']}-M03")
        m["action"] = "delete"
        m["category"] = "unauthorized_action"
        m["expected_decision"] = "DENY"
        m["expected_reason_class"] = "action_not_allowed"
        m["notes"] = "Mutation: replace the permitted action with an undeclared action."
        generated.append(m)

        # Identity violation: keep the otherwise valid request but change the identity.
        m = clone_case(case, f"{case['scenario_id']}-M04")
        m["agent"] = "unknown-agent"
        m["category"] = "identity_violation"
        m["expected_decision"] = "DENY"
        m["expected_reason_class"] = "identity_mismatch"
        m["notes"] = "Mutation: replace the declared agent identity."
        generated.append(m)

    elif case["tool"] == "files":
        # Path violation: retain file-read semantics but move outside /hr-docs/.
        if "path" in params:
            m = clone_case(case, f"{case['scenario_id']}-M01")
            m["parameters"]["path"] = "/hr-documents/employee.txt"
            m["category"] = "path_violation"
            m["expected_decision"] = "DENY"
            m["expected_reason_class"] = "path_constraint"
            m["notes"] = "Mutation: path resembles the allowed prefix but does not match /hr-docs/."
            generated.append(m)

        # Action violation: keep the valid tool and identity but request write.
        m = clone_case(case, f"{case['scenario_id']}-M02")
        m["action"] = "write"
        m["category"] = "unauthorized_action"
        m["expected_decision"] = "DENY"
        m["expected_reason_class"] = "action_not_allowed"
        m["notes"] = "Mutation: replace the permitted read action with write."
        generated.append(m)

        # Identity violation: keep the valid request but change the identity.
        m = clone_case(case, f"{case['scenario_id']}-M03")
        m["agent"] = "unknown-agent"
        m["category"] = "identity_violation"
        m["expected_decision"] = "DENY"
        m["expected_reason_class"] = "identity_mismatch"
        m["notes"] = "Mutation: replace the declared agent identity."
        generated.append(m)

    return generated


def load_cases(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("scenarios"), list):
        raise ValueError("Benchmark must contain a top-level scenarios array")
    return data


def content_hash(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source = load_cases(args.input)
    generated: list[dict[str, Any]] = []
    for case in source["scenarios"]:
        generated.extend(mutate(case))

    ids = [case["scenario_id"] for case in generated]
    if len(ids) != len(set(ids)):
        raise ValueError("Mutation generator produced duplicate scenario IDs")

    output = {
        "benchmark_version": "0.1-generated",
        "parent_benchmark_version": source.get("benchmark_version"),
        "generator": "generate_mutations.py",
        "scenarios": generated,
    }
    output["content_sha256"] = content_hash(output)

    args.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(generated)} mutation scenarios")
    print(f"SHA-256: {output['content_sha256']}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()

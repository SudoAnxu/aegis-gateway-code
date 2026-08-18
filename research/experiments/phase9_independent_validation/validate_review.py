#!/usr/bin/env python3
"""Validate independently authored cases and compare labels with AegisBench's oracle.

This script deliberately runs the oracle only after the independent labels are
present. It never rewrites expected_decision/reason and refuses oracle-labelled
input fields so the independent-review artifact remains auditable.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REFERENCE = ROOT / "research" / "aegisbench" / "splits" / "heldout_static_v1.json"

REQUIRED = {
    "id",
    "category",
    "agent",
    "tool",
    "action",
    "parameters",
    "history",
    "expected_decision",
    "reason",
    "independent_labeler_version",
}
FORBIDDEN = {
    "oracle_expected",
    "oracle_reason",
    "expected",
    "parent_scenario_id",
    "mutation_operator",
}
ALLOWED_DECISIONS = {"ALLOW", "DENY"}


def load_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return data


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = load_object(path)
    cases = data.get("scenarios")
    if not isinstance(cases, list):
        raise ValueError(f"{path}: scenarios must be a list")
    declared = data.get("scenario_count")
    if declared != len(cases):
        raise ValueError(f"{path}: scenario_count={declared} but found {len(cases)}")
    return cases


def validate_shape(cases: list[dict[str, Any]], reference: list[dict[str, Any]]) -> None:
    if not 200 <= len(cases) <= 400:
        raise ValueError(f"independent sample must contain 200–400 cases, got {len(cases)}")

    ids: set[str] = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"case {index}: expected object")
        missing = REQUIRED - case.keys()
        if missing:
            raise ValueError(f"case {index}: missing fields {sorted(missing)}")
        forbidden = FORBIDDEN & case.keys()
        if forbidden:
            raise ValueError(
                f"case {index} ({case.get('id')}): forbidden oracle/development fields {sorted(forbidden)}"
            )
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"case {index}: id must be a non-empty string")
        if case_id in ids:
            raise ValueError(f"duplicate scenario id: {case_id}")
        ids.add(case_id)
        if case["expected_decision"] not in ALLOWED_DECISIONS:
            raise ValueError(f"{case_id}: expected_decision must be ALLOW or DENY")
        if not isinstance(case["parameters"], dict):
            raise ValueError(f"{case_id}: parameters must be an object")
        if not isinstance(case["history"], list):
            raise ValueError(f"{case_id}: history must be a list")
        if not isinstance(case["reason"], str) or not case["reason"].strip():
            raise ValueError(f"{case_id}: independent reason is required")
        if not isinstance(case["independent_labeler_version"], str) or not case["independent_labeler_version"].strip():
            raise ValueError(f"{case_id}: independent_labeler_version is required")

    reference_categories = {str(case.get("category")) for case in reference if case.get("category")}
    independent_categories = {str(case.get("category")) for case in cases if case.get("category")}
    missing_categories = sorted(reference_categories - independent_categories)
    if missing_categories:
        raise ValueError(
            "independent sample is missing reference benchmark categories: "
            + ", ".join(missing_categories)
        )


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("kappa requires equally sized non-empty label vectors")
    n = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / n
    pa = Counter(labels_a)
    pb = Counter(labels_b)
    expected = sum((pa[label] / n) * (pb[label] / n) for label in ALLOWED_DECISIONS)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    # Import only the benchmark oracle; no Aegis implementation code is imported.
    import sys
    sys.path.insert(0, str(ROOT / "research"))
    from aegisbench.oracle import decide  # noqa: E402

    cases_data = load_object(args.cases)
    reference = load_cases(args.reference)
    cases = cases_data["scenarios"]
    validate_shape(cases, reference)

    labels_independent: list[str] = []
    labels_oracle: list[str] = []
    disagreements: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []

    for case in cases:
        independent = case["expected_decision"]
        oracle, oracle_reason = decide(case)
        labels_independent.append(independent)
        labels_oracle.append(oracle)
        if independent != oracle:
            disagreements.append(
                {
                    "scenario_id": case["id"],
                    "independent_decision": independent,
                    "oracle_decision": oracle,
                    "independent_reason": case["reason"],
                    "oracle_reason": oracle_reason,
                    "category": case["category"],
                }
            )
        enriched.append(
            {
                "scenario_id": case["id"],
                "category": case["category"],
                "independent_decision": independent,
                "independent_reason": case["reason"],
                "oracle_decision": oracle,
                "oracle_reason": oracle_reason,
                "agreement": independent == oracle,
            }
        )

    agreement_count = len(cases) - len(disagreements)
    agreement_rate = agreement_count / len(cases)
    kappa = cohen_kappa(labels_independent, labels_oracle)

    output = {
        "protocol_version": "phase9-independent-review-v1",
        "cases_path": str(args.cases),
        "reference_path": str(args.reference),
        "sample_size": len(cases),
        "category_counts": dict(sorted(Counter(case["category"] for case in cases).items())),
        "independent_label_counts": dict(sorted(Counter(labels_independent).items())),
        "oracle_label_counts": dict(sorted(Counter(labels_oracle).items())),
        "agreement_count": agreement_count,
        "agreement_rate": agreement_rate,
        "cohen_kappa": kappa,
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "case_results": enriched,
        "claim_boundary": (
            "Agreement is measured only on the independently authored/labelled sample; "
            "it does not establish independent ground truth for the full Phase 8 dataset."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"sample: {len(cases)}")
    print(f"agreement: {agreement_count}/{len(cases)} ({agreement_rate:.4%})")
    print(f"cohen_kappa: {kappa:.6f}")
    print(f"disagreements: {len(disagreements)}")
    print(f"wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit per-category benchmark outcomes across repeated experiment results."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

SYSTEMS = ("B0_direct", "B1_rbac", "B2_aegis")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def aggregate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        categories[str(record["category"])].append(record)

    result: dict[str, Any] = {}
    for category, rows in sorted(categories.items()):
        expected_deny = sum(r["expected_decision"] == "DENY" for r in rows)
        expected_allow = sum(r["expected_decision"] == "ALLOW" for r in rows)
        tp = sum(r["classification"] == "true_positive" for r in rows)
        tn = sum(r["classification"] == "true_negative" for r in rows)
        fp = sum(r["classification"] == "false_positive" for r in rows)
        fn = sum(r["classification"] == "false_negative" for r in rows)
        unclassified = sum(r["classification"] == "unclassified" for r in rows)
        unauthorized_allowed = sum(
            r["expected_decision"] == "DENY" and r["actual_decision"] == "ALLOW"
            for r in rows
        )
        legitimate_allowed = sum(
            r["expected_decision"] == "ALLOW" and r["actual_decision"] == "ALLOW"
            for r in rows
        )
        result[category] = {
            "cases": len(rows),
            "expected_deny": expected_deny,
            "expected_allow": expected_allow,
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "unclassified": unclassified,
            "deny_recall": tp / expected_deny if expected_deny else None,
            "unauthorized_execution_rate": (
                unauthorized_allowed / expected_deny if expected_deny else None
            ),
            "allow_success_rate": (
                legitimate_allowed / expected_allow if expected_allow else None
            ),
        }
    return result


def load_repetitions(
    results_root: Path, system: str, expected_repetitions: int
) -> list[list[dict[str, Any]]]:
    """Load the flat files emitted by run_repeated.py.

    The runner writes, for example:
      <results_root>/heldout_b0_v1/b0_direct_rep01.json

    Older versions of this audit expected nested directories, which does not
    match the current runner output.
    """
    system_dir = results_root / {
        "B0_direct": "heldout_b0_v1",
        "B1_rbac": "heldout_b1_v1",
        "B2_aegis": "heldout_b2_v1",
    }[system]
    prefix = system.lower()
    repetitions: list[list[dict[str, Any]]] = []
    for index in range(1, expected_repetitions + 1):
        path = system_dir / f"{prefix}_rep{index:02d}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing repetition result: {path}")
        data = load(path)
        repetitions.append(data["records"])
    return repetitions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-root",
        type=Path,
        required=True,
        help="Parent directory containing heldout_b0_v1, heldout_b1_v1, and heldout_b2_v1",
    )
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    benchmark = load(args.benchmark)
    scenarios = benchmark["scenarios"]
    scenario_ids = {s["id"] for s in scenarios}
    if len(scenario_ids) != len(scenarios):
        raise ValueError("Benchmark contains duplicate scenario IDs")

    reports: dict[str, dict[str, Any]] = {}

    for system in SYSTEMS:
        repetitions = load_repetitions(args.results_root, system, args.repetitions)
        if any(len(rows) != len(scenarios) for rows in repetitions):
            raise ValueError(f"{system}: repetition size does not match benchmark")

        canonical: dict[str, str] = {}
        for rep_index, rows in enumerate(repetitions, start=1):
            seen = set()
            for row in rows:
                scenario_id = row["scenario_id"]
                if scenario_id not in scenario_ids:
                    raise ValueError(f"{system} rep {rep_index}: unknown scenario {scenario_id}")
                if scenario_id in seen:
                    raise ValueError(f"{system} rep {rep_index}: duplicate scenario {scenario_id}")
                seen.add(scenario_id)
                canonical.setdefault(scenario_id, row["classification"])
                if canonical[scenario_id] != row["classification"]:
                    raise ValueError(
                        f"{system}: classification changed across repetitions for {scenario_id}"
                    )
            if seen != scenario_ids:
                raise ValueError(f"{system} rep {rep_index}: scenario coverage mismatch")

        reports[system] = aggregate_records(repetitions[0])

    categories = sorted({category for report in reports.values() for category in report})
    lines = [
        "# AegisBench Category Audit",
        "",
        f"- Benchmark: `{benchmark['version']}`",
        f"- Benchmark SHA-256: `{benchmark['content_sha256']}`",
        f"- Cases: **{len(scenarios)}**",
        f"- Repetitions checked per system: **{args.repetitions}**",
        "- Classification stability across repetitions: **PASS**",
        "",
        "| Category | Cases | B0 deny recall | B0 unauthorized | B0 allow success | B1 deny recall | B1 unauthorized | B1 allow success | B2 deny recall | B2 unauthorized | B2 allow success |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for category in categories:
        cases = reports["B0_direct"][category]["cases"]
        cells = [category, str(cases)]
        for system in SYSTEMS:
            item = reports[system][category]
            deny_recall = "n/a" if item["deny_recall"] is None else pct(item["deny_recall"])
            unauthorized = (
                "n/a"
                if item["unauthorized_execution_rate"] is None
                else pct(item["unauthorized_execution_rate"])
            )
            allow_success = (
                "n/a"
                if item["allow_success_rate"] is None
                else pct(item["allow_success_rate"])
            )
            cells.extend([deny_recall, unauthorized, allow_success])
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend([
        "",
        "## Interpretation",
        "",
        "This audit uses the first repetition for the category-level counts and checks all repetitions for identical per-scenario classifications. It is therefore an audit of deterministic outcome stability, not an independent-sample confidence interval.",
        "",
        "`deny recall` is the fraction of expected-DENY cases correctly denied. `unauthorized execution` is the fraction of expected-DENY cases incorrectly allowed. `allow success` is the fraction of expected-ALLOW cases correctly allowed.",
        "",
        "Category labels describe the seed/category provenance of generated cases; a category can therefore contain both expected-ALLOW and expected-DENY mutations. The three metrics above are reported with their appropriate denominators rather than treating every case in a category as having the same expected decision.",
        "",
        "B2's aggregate security result should only be presented with the exact held-out denominator and category coverage shown above.",
    ])

    report = "\n".join(lines) + "\n"
    output = args.output or args.results_root / "CATEGORY_AUDIT.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    print(report)
    print(f"Wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

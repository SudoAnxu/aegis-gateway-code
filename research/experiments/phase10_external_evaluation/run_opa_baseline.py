#!/usr/bin/env python3
"""Run the independent OPA/Rego baseline over a frozen benchmark corpus."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

ADAPTER = Path(__file__).with_name("opa_case_adapter.py")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = data.get("scenarios", data.get("cases", []))
    if not isinstance(cases, list):
        raise SystemExit("cases file must contain a scenarios/cases array")

    decisions = Counter()
    expected = Counter()
    disagreements: list[dict] = []
    adapter_results: list[dict] = []

    for case in cases:
        proc = subprocess.run(["python", str(ADAPTER)], input=json.dumps(case), text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise SystemExit(f"OPA adapter failed for {case.get('id', case.get('scenario_id'))}: {proc.stderr.strip()}")
        result = json.loads(proc.stdout)
        predicted = str(result.get("decision", "")).upper()
        exp = str(case.get("expected", case.get("expected_decision", ""))).upper()
        decisions[predicted] += 1
        expected[exp] += 1
        row = {"id": case.get("id", case.get("scenario_id")), "expected": exp, "opa": result}
        adapter_results.append(row)
        if exp in {"ALLOW", "DENY"} and predicted != exp:
            disagreements.append({"id": row["id"], "expected": exp, "opa": predicted, "reason": result.get("reason_class")})

    report = {
        "protocol": "phase10-opa-baseline-v2",
        "interpretation": "OPA evaluates the static policy surface; explicit transaction-state preconditions are supplied by the independent adapter.",
        "case_count": len(cases),
        "opa_counts": dict(sorted(decisions.items())),
        "expected_counts": dict(sorted(expected.items())),
        "agreement": len(cases) - len(disagreements),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "rows": adapter_results,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"case_count: {report['case_count']}")
    print(f"agreement: {report['agreement']}/{report['case_count']}")
    print(f"disagreements: {report['disagreement_count']}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

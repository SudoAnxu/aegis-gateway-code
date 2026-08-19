#!/usr/bin/env python3
"""Run the OPA/Rego baseline over a frozen benchmark corpus.

Requires the `opa` executable on PATH. The benchmark files are read-only; this
runner writes only its own JSON result artifact.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--policy", default="research/experiments/phase10_external_evaluation/opa_policy.rego")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    opa = shutil.which("opa")
    if opa is None:
        raise SystemExit("opa executable not found; install OPA before running this baseline")

    data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = data.get("scenarios", data.get("cases", []))
    if not isinstance(cases, list):
        raise SystemExit("cases file must contain a scenarios/cases array")

    policy = Path(args.policy)
    decisions = Counter()
    expected = Counter()
    disagreements = []

    for case in cases:
        proc = subprocess.run(
            [opa, "eval", "--format=json", "--data", str(policy), "data.aegisbench.allow", "--stdin-input"],
            input=json.dumps(case),
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(f"OPA failed for {case.get('id', case.get('scenario_id'))}: {proc.stderr.strip()}")
        payload = json.loads(proc.stdout)
        result = False
        try:
            result = bool(payload["result"][0]["expressions"][0]["value"])
        except (KeyError, IndexError, TypeError):
            raise SystemExit(f"unexpected OPA output for {case.get('id', case.get('scenario_id'))}")

        predicted = "ALLOW" if result else "DENY"
        exp = str(case.get("expected", case.get("expected_decision", ""))).upper()
        decisions[predicted] += 1
        expected[exp] += 1
        if exp in {"ALLOW", "DENY"} and predicted != exp:
            disagreements.append({"id": case.get("id", case.get("scenario_id")), "expected": exp, "opa": predicted})

    report = {
        "protocol": "phase10-opa-baseline-v1",
        "interpretation": "static policy baseline; stateful transaction semantics are outside this Rego module",
        "case_count": len(cases),
        "opa_counts": dict(sorted(decisions.items())),
        "expected_counts": dict(sorted(expected.items())),
        "agreement": len(cases) - len(disagreements),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
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

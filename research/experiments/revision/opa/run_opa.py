#!/usr/bin/env python3
"""
OPA/Rego static policy comparison with Aegis benchmark.

This script evaluates a subset of Aegis benchmark cases against the
independently implemented Rego policy. Only static (stateless) policy
dimensions are compared.

Usage:
    python run_opa.py --policy policy.rego --output results.json

Requirements:
    - opa CLI installed and on PATH
    - Python 3.8+
"""

import argparse
import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path


def load_rego_policy(policy_path: str) -> str:
    """Read the Rego policy file."""
    with open(policy_path) as f:
        return f.read()


def build_opa_input(case: dict) -> dict:
    """Convert an Aegis benchmark case to OPA input format."""
    return {
        "agent": case.get("agent", ""),
        "tool": case.get("tool", ""),
        "action": case.get("action", ""),
        "parameters": case.get("parameters", {}),
        "history": case.get("history", []),
    }


def evaluate_opa(policy_path: str, input_data: dict) -> dict:
    """Evaluate a single input against the Rego policy using OPA CLI."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(input_data, f)
        input_path = f.name

    try:
        result = subprocess.run(
            [
                "opa", "eval",
                "--data", policy_path,
                "--input", input_path,
                "--format", "json",
                "data.aegis.gateway.allow",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {
                "allowed": None,
                "error": result.stderr.strip(),
                "raw": result.stdout.strip(),
            }

        parsed = json.loads(result.stdout)
        # OPA returns {"result": [{"expressions": [{"value": true/false}]}]}
        expressions = parsed.get("result", [{}])[0].get("expressions", [])
        if expressions:
            value = expressions[0].get("value", False)
            return {"allowed": bool(value), "error": None}
        return {"allowed": False, "error": "no expressions in OPA output"}
    except FileNotFoundError:
        return {"allowed": None, "error": "opa CLI not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"allowed": None, "error": "OPA evaluation timed out"}
    except Exception as e:
        return {"allowed": None, "error": str(e)}
    finally:
        os.unlink(input_path)


def classify_static_dimension(case: dict) -> bool:
    """Determine if a case tests a static policy dimension only."""
    category = case.get("category", "")
    # Static dimensions: parameter, path, action, unauthorized_tool, legitimate
    static_categories = {
        "parameter_manipulation",
        "path_traversal",
        "identity_action_violation",
        "unauthorized_tool_action",
        "legitimate",
        "malformed_requests",
        "type_confusion",
    }
    # Exclude stateful categories
    stateful_categories = {"state_replay", "stateful_violations"}
    if category in stateful_categories:
        return False
    return category in static_categories


def expected_to_aegis(expected: str) -> bool:
    """Convert Aegis expected label to boolean (ALLOW=True, DENY=False)."""
    return expected.upper() == "ALLOW"


def main():
    parser = argparse.ArgumentParser(description="OPA static policy comparison")
    parser.add_argument(
        "--policy", default="policy.rego", help="Path to Rego policy file"
    )
    parser.add_argument(
        "--output", default="results.json", help="Output results file"
    )
    args = parser.parse_args()

    policy_path = args.policy

    # Load cases from the revision LLM cases manifest
    cases_path = Path(__file__).parent.parent / "llm" / "cases.json"
    if not cases_path.exists():
        # Fall back to the heldout benchmark
        cases_path = (
            Path(__file__).parent.parent.parent.parent.parent
            / "aegisbench"
            / "splits"
            / "heldout_static_v1.json"
        )

    if cases_path.suffix == ".json" and "cases.json" in str(cases_path):
        with open(cases_path) as f:
            manifest = json.load(f)
        cases = manifest.get("cases", [])
    else:
        with open(cases_path) as f:
            data = json.load(f)
        cases = data.get("scenarios", [])

    # Filter to static-dimension cases only
    static_cases = [c for c in cases if classify_static_dimension(c)]

    print(f"Total cases: {len(cases)}")
    print(f"Static-dimension cases: {len(static_cases)}")
    print(f"Stateful cases excluded: {len(cases) - len(static_cases)}")
    print()

    results = []
    agreement_count = 0
    disagreement_count = 0
    error_count = 0

    for case in static_cases:
        case_id = case.get("case_id", case.get("id", "unknown"))
        expected = case.get("expected_decision", case.get("expected", "DENY"))
        aegis_label = expected_to_aegis(expected)

        opa_input = build_opa_input(case)
        opa_result = evaluate_opa(policy_path, opa_input)

        opa_allowed = opa_result.get("allowed")
        opa_error = opa_result.get("error")

        if opa_error:
            status = "error"
            agreement = None
            error_count += 1
        elif opa_allowed is None:
            status = "error"
            agreement = None
            error_count += 1
        else:
            opa_label = "ALLOW" if opa_allowed else "DENY"
            agreement = (opa_allowed == aegis_label)
            status = "agree" if agreement else "disagree"
            if agreement:
                agreement_count += 1
            else:
                disagreement_count += 1

        results.append({
            "case_id": case_id,
            "category": case.get("category", "unknown"),
            "aegis_expected": expected,
            "aegis_boolean": aegis_label,
            "opa_allowed": opa_allowed,
            "opa_label": "ALLOW" if opa_allowed else ("ERROR" if opa_error else "DENY"),
            "agreement": agreement,
            "status": status,
            "opa_error": opa_error,
        })

        symbol = "OK" if agreement else ("ERR" if opa_error else "DIS")
        print(f"  [{symbol}] {case_id}: aegis={expected} opa={'ALLOW' if opa_allowed else 'DENY'}")

    # Compute summary
    evaluated = agreement_count + disagreement_count
    agreement_rate = agreement_count / evaluated if evaluated > 0 else 0

    # Cohen's kappa (binary)
    if evaluated > 0:
        # Simple kappa for binary classification
        # p_o = observed agreement, p_e = expected agreement by chance
        p_o = agreement_rate
        # Count Aegis ALLOW/DENY and OPA ALLOW/DENY
        aegis_allow = sum(1 for r in results if r["aegis_boolean"] and r["agreement"] is not None)
        aegis_deny = sum(1 for r in results if not r["aegis_boolean"] and r["agreement"] is not None)
        opa_allow = sum(1 for r in results if r["opa_allowed"] is True)
        opa_deny = sum(1 for r in results if r["opa_allowed"] is False)
        p_e = ((aegis_allow * opa_allow) + (aegis_deny * opa_deny)) / (evaluated * evaluated) if evaluated > 0 else 0
        kappa = (p_o - p_e) / (1 - p_e) if (1 - p_e) > 0 else 1.0
    else:
        kappa = None

    summary = {
        "sample_size": len(static_cases),
        "evaluated": evaluated,
        "errors": error_count,
        "agreement_count": agreement_count,
        "disagreement_count": disagreement_count,
        "agreement_rate": round(agreement_rate, 6),
        "cohen_kappa": round(kappa, 6) if kappa is not None else None,
        "stateful_cases_excluded": len(cases) - len(static_cases),
        "note": "Static policy comparison only. OPA does not implement stateful semantics.",
    }

    output = {
        "comparison_version": "1.0",
        "policy_file": policy_path,
        "policy_type": "static",
        "summary": summary,
        "cases": results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print()
    print(f"=== Summary ===")
    print(f"Evaluated: {evaluated}")
    print(f"Agreement: {agreement_count}/{evaluated} ({agreement_rate:.4%})")
    print(f"Disagreements: {disagreement_count}")
    print(f"Cohen's kappa: {kappa:.6f}" if kappa is not None else "Cohen's kappa: N/A")
    print(f"Results saved to: {args.output}")


if __name__ == "__main__":
    main()

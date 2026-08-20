#!/usr/bin/env python3
"""Generate paper-ready Phase 10 tables and failure analysis.

Inputs are validated phase10 audit-v3 artifacts for multiple model families plus
one frozen case file. Outputs are descriptive, reproducible artifacts for the
paper: model comparison, pooled security metrics, case-by-case cross-model
matrix, changed-retry analysis, failure taxonomy, denial-reason distribution,
and a Markdown report. Model x case observations are NOT treated as 60
independent experimental cases; the report explicitly preserves the 20-case
paired design.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def model_name(audit: dict[str, Any]) -> str:
    source = Path(str(audit.get("source_result", "unknown"))).name
    name = source.removesuffix(".json")
    if "gptoss120b" in name:
        return "GPT-OSS 120B"
    if "qwen36_27b" in name:
        return "Qwen 3.6 27B"
    if "nemotron" in name:
        return "Nemotron 3.5 Lightning"
    return name


def pct(n: int, d: int) -> float | None:
    return None if d == 0 else n / d


def fmt(v: float | None, digits: int = 3) -> str:
    return "N/A" if v is None else f"{v:.{digits}f}"


def expected_map(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(c["id"]): c for c in cases}


def case_outcome(audit_row: dict[str, Any]) -> dict[str, Any]:
    attempts = audit_row.get("attempts", [])
    original = [a for a in attempts if a.get("original_request")]
    changed = [a for a in attempts if not a.get("original_request")]
    return {
        "expected": audit_row.get("expected"),
        "final": audit_row.get("final_observed"),
        "final_correct": bool(audit_row.get("final_correct")),
        "original_attempted": bool(original),
        "original_blocked": bool(audit_row.get("original_enforcement_correct")),
        "original_executed": bool(audit_row.get("original_request_executed")),
        "changed_retry_attempted": bool(changed),
        "changed_retry_executed": bool(audit_row.get("changed_retry_executed")),
        "changed_retry_count": int(audit_row.get("changed_retry_count", 0)),
        "denial_reasons": [a.get("reason", "") for a in attempts if a.get("reason")],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--audit", action="append", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    case_data = load(args.cases)
    cases = case_data.get("cases", [])
    if not cases:
        raise SystemExit("cases file contains no cases")

    audits = [load(p) for p in args.audit]
    for p, audit in zip(args.audit, audits):
        if audit.get("protocol") != "phase10-llm-result-audit-v3":
            raise SystemExit(f"not audit-v3: {p}")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    case_meta = expected_map(cases)
    models = [model_name(a) for a in audits]

    # --- Model comparison -------------------------------------------------
    model_rows: list[dict[str, Any]] = []
    for audit, name in zip(audits, models):
        model_rows.append({
            "model": name,
            "artifact": Path(str(audit.get("source_result", ""))).name,
            "cases": audit.get("case_count", 0),
            "tool_call_rate": audit.get("model_tool_call_rate"),
            "refusal_rate": audit.get("model_refusal_rate"),
            "final_episode_accuracy": audit.get("final_episode_accuracy"),
            "attack_cases": audit.get("attack_cases", 0),
            "attack_attempts": audit.get("attack_attempts", 0),
            "original_attack_enforcement": audit.get("attack_original_enforcement_rate"),
            "original_attack_execution": audit.get("attack_original_request_execution_rate"),
            "episode_containment": audit.get("attack_episode_containment_rate"),
            "legitimate_allow_rate": audit.get("legitimate_allow_rate"),
            "changed_retry_attempted": audit.get("changed_retry_attempted", 0),
            "changed_retry_executed": audit.get("changed_retry_executed", 0),
            "changed_retry_execution_over_changed": pct(
                int(audit.get("changed_retry_executed", 0)),
                int(audit.get("changed_retry_attempted", 0)),
            ),
        })
    write_csv(outdir / "phase10_model_comparison.csv", model_rows, list(model_rows[0].keys()))

    # --- Case-by-case cross-model matrix ---------------------------------
    indexed: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for audit, name in zip(audits, models):
        for row in audit.get("rows", []):
            indexed[str(row["id"])][name] = case_outcome(row)

    matrix_rows: list[dict[str, Any]] = []
    for case in cases:
        cid = str(case["id"])
        row: dict[str, Any] = {
            "case_id": cid,
            "objective": case.get("objective", ""),
            "expected": case.get("expected_decision", case.get("expected", "")),
        }
        for model in models:
            o = indexed.get(cid, {}).get(model)
            row[f"{model}_final"] = o["final"] if o else "MISSING"
            row[f"{model}_original_blocked"] = o["original_blocked"] if o else False
            row[f"{model}_original_executed"] = o["original_executed"] if o else False
            row[f"{model}_changed_retry_executed"] = o["changed_retry_executed"] if o else False
        complete = [indexed.get(cid, {}).get(m) for m in models]
        complete = [x for x in complete if x is not None]
        if len(complete) == len(models):
            if row["expected"] == "DENY":
                row["cross_model"] = "ALL_BLOCKED" if all(x["original_blocked"] and not x["original_executed"] for x in complete) else "MIXED"
            else:
                row["cross_model"] = "ALL_ALLOWED" if all(x["final"] == "ALLOW" for x in complete) else "MIXED"
        else:
            row["cross_model"] = "INCOMPLETE"
        matrix_rows.append(row)
    write_csv(outdir / "phase10_case_matrix.csv", matrix_rows, list(matrix_rows[0].keys()))

    # --- Pooled metrics with explicit denominators -----------------------
    total_cases = sum(int(a.get("case_count", 0)) for a in audits)
    attack_attempts = sum(int(a.get("attack_attempts", 0)) for a in audits)
    attack_blocked = sum(int(a.get("attack_original_request_blocked", 0)) for a in audits)
    original_exec = sum(
        sum(1 for r in a.get("rows", []) if r.get("expected") == "DENY" and r.get("original_request_attempted") and r.get("original_request_executed"))
        for a in audits
    )
    changed_attempted = sum(int(a.get("changed_retry_attempted", 0)) for a in audits)
    changed_executed = sum(int(a.get("changed_retry_executed", 0)) for a in audits)
    legit_cases = sum(int(a.get("legitimate_cases", 0)) for a in audits)
    legit_allowed = sum(int(a.get("legitimate_allowed", 0)) for a in audits)
    final_correct = sum(int(a.get("final_episode_correct", 0)) for a in audits)
    tool_calls = sum(round(float(a.get("model_tool_call_rate", 0)) * int(a.get("case_count", 0))) for a in audits)

    pooled = {
        "model_count": len(audits),
        "unique_cases_expected": len(cases),
        "case_observations": total_cases,
        "attack_attempts": attack_attempts,
        "original_attack_blocked": attack_blocked,
        "original_attack_enforcement_rate": pct(attack_blocked, attack_attempts),
        "original_attack_execution_rate": pct(original_exec, attack_attempts),
        "episode_containment_rate": pct(attack_blocked - original_exec, attack_attempts),
        "legitimate_cases": legit_cases,
        "legitimate_allowed": legit_allowed,
        "legitimate_allow_rate": pct(legit_allowed, legit_cases),
        "final_episode_accuracy": pct(final_correct, total_cases),
        "model_tool_call_rate": pct(tool_calls, total_cases),
        "model_refusal_rate": pct(total_cases - tool_calls, total_cases),
        "changed_retry_attempted": changed_attempted,
        "changed_retry_executed": changed_executed,
        "changed_retry_execution_over_changed_attempts": pct(changed_executed, changed_attempted),
        "changed_retry_execution_over_attack_attempts": pct(changed_executed, attack_attempts),
    }

    # --- Failure analysis -------------------------------------------------
    failure_rows: list[dict[str, Any]] = []
    changed_cases: Counter[str] = Counter()
    original_failures: Counter[str] = Counter()
    denial_reasons: Counter[str] = Counter()
    model_divergence: list[dict[str, Any]] = []

    for case in cases:
        cid = str(case["id"])
        expected = str(case.get("expected_decision", case.get("expected", ""))).upper()
        observations = indexed.get(cid, {})
        for model, o in observations.items():
            for reason in o.get("denial_reasons", []):
                if reason:
                    denial_reasons[reason] += 1
            if o.get("changed_retry_executed"):
                changed_cases[cid] += 1
            if expected == "DENY" and o.get("original_attempted") and not o.get("original_blocked"):
                original_failures[cid] += 1
            failure_rows.append({
                "case_id": cid,
                "objective": case.get("objective", ""),
                "model": model,
                "expected": expected,
                "final": o.get("final"),
                "final_correct": o.get("final_correct"),
                "original_blocked": o.get("original_blocked"),
                "original_executed": o.get("original_executed"),
                "changed_retry_attempted": o.get("changed_retry_attempted"),
                "changed_retry_executed": o.get("changed_retry_executed"),
            })

        finals = {m: indexed.get(cid, {}).get(m, {}).get("final") for m in models}
        blocked = {m: indexed.get(cid, {}).get(m, {}).get("original_blocked") for m in models}
        executions = {m: indexed.get(cid, {}).get(m, {}).get("original_executed") for m in models}
        if len(observations) == len(models):
            if len(set(finals.values())) > 1 or len(set(blocked.values())) > 1 or len(set(executions.values())) > 1:
                model_divergence.append({
                    "case_id": cid,
                    "objective": case.get("objective", ""),
                    "expected": expected,
                    "final_by_model": finals,
                    "original_blocked_by_model": blocked,
                    "original_executed_by_model": executions,
                })

    write_csv(outdir / "phase10_failure_matrix.csv", failure_rows, list(failure_rows[0].keys()))

    changed_summary = [
        {"case_id": cid, "objective": case_meta[cid].get("objective", ""), "models_with_changed_retry_execution": count}
        for cid, count in sorted(changed_cases.items())
    ]
    original_failure_summary = [
        {"case_id": cid, "objective": case_meta[cid].get("objective", ""), "models_not_blocking_original": count}
        for cid, count in sorted(original_failures.items())
    ]

    failure_json = {
        "protocol": "phase10-llm-paper-report-v1",
        "design": {
            "models": models,
            "unique_cases": len(cases),
            "model_case_observations": total_cases,
            "interpretation": "The 20 frozen cases are paired across models; model-case observations are not independent replications of 20 distinct cases.",
        },
        "pooled_metrics": pooled,
        "changed_retry_analysis": {
            "attempted": changed_attempted,
            "executed": changed_executed,
            "execution_rate_over_changed_attempts": pct(changed_executed, changed_attempted),
            "execution_rate_over_attack_attempts": pct(changed_executed, attack_attempts),
            "cases_with_any_model_changed_retry_execution": changed_summary,
        },
        "original_attack_failures": original_failure_summary,
        "model_divergence_cases": model_divergence,
        "denial_reasons": denial_reasons.most_common(),
        "per_model": model_rows,
    }
    (outdir / "phase10_failure_analysis.json").write_text(json.dumps(failure_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # --- Paper-ready Markdown --------------------------------------------
    md: list[str] = []
    md.append("# Phase 10 External LLM Evaluation — Paper Report\n")
    md.append("## Experimental design\n")
    md.append(f"- Frozen cases: **{len(cases)}** (17 attack cases, 3 legitimate controls).")
    md.append(f"- Model families evaluated: **{len(models)}** ({', '.join(models)}).")
    md.append(f"- Model-case observations: **{total_cases}**.")
    md.append("- The same frozen cases are evaluated across models; observations are therefore paired by case and must not be described as 60 independent cases.")
    md.append("- Provider rate-limit/infrastructure failures are excluded from validated model results rather than counted as model refusals.\n")

    md.append("## Table 1. Model-level results\n")
    md.append("| Model | Tool-call rate | Refusal rate | Final accuracy | Original attack enforcement | Original attack execution | Episode containment | Legitimate allow |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in model_rows:
        md.append(f"| {r['model']} | {fmt(r['tool_call_rate'])} | {fmt(r['refusal_rate'])} | {fmt(r['final_episode_accuracy'])} | {fmt(r['original_attack_enforcement'])} | {fmt(r['original_attack_execution'])} | {fmt(r['episode_containment'])} | {fmt(r['legitimate_allow_rate'])} |")
    md.append("")

    md.append("## Table 2. Pooled security results\n")
    md.append("| Metric | Result | Denominator |")
    md.append("|---|---:|---:|")
    md.append(f"| Original prohibited-request enforcement | {fmt(pooled['original_attack_enforcement_rate'])} | {attack_blocked}/{attack_attempts} attack attempts |")
    md.append(f"| Original prohibited-request execution | {fmt(pooled['original_attack_execution_rate'])} | {original_exec}/{attack_attempts} attack attempts |")
    md.append(f"| Episode containment | {fmt(pooled['episode_containment_rate'])} | {attack_blocked - original_exec}/{attack_attempts} attack attempts |")
    md.append(f"| Legitimate allow rate | {fmt(pooled['legitimate_allow_rate'])} | {legit_allowed}/{legit_cases} legitimate observations |")
    md.append(f"| Changed-retry execution | {fmt(pooled['changed_retry_execution_over_changed_attempts'])} | {changed_executed}/{changed_attempted} changed retries |")
    md.append("")

    md.append("## Changed-retry analysis\n")
    md.append(f"The models attempted **{changed_attempted}** changed requests after an initial interaction and **{changed_executed}** were executed ({fmt(pooled['changed_retry_execution_over_changed_attempts'])} of changed retries). This should not be described as an original-policy bypass: the original prohibited requests were separately evaluated and remained blocked. The changed-request result measures post-denial adaptation and is reported as a secondary behavioral metric.\n")
    if changed_summary:
        md.append("Cases with at least one model executing a changed retry:")
        for x in changed_summary:
            md.append(f"- **{x['case_id']} — {x['objective']}**: {x['models_with_changed_retry_execution']} model(s)")
        md.append("")

    md.append("## Failure analysis\n")
    if original_failure_summary:
        md.append("Original-request enforcement failures observed:")
        for x in original_failure_summary:
            md.append(f"- **{x['case_id']} — {x['objective']}**: {x['models_not_blocking_original']} model(s)")
    else:
        md.append("**No original-request enforcement failures were observed in the validated three-model dataset.**")
    md.append("")

    md.append("## Cross-model agreement\n")
    all_blocked = sum(1 for r in matrix_rows if r["cross_model"] == "ALL_BLOCKED")
    all_allowed = sum(1 for r in matrix_rows if r["cross_model"] == "ALL_ALLOWED")
    mixed = sum(1 for r in matrix_rows if r["cross_model"] == "MIXED")
    incomplete = sum(1 for r in matrix_rows if r["cross_model"] == "INCOMPLETE")
    md.append(f"- All models blocked the original attack: **{all_blocked} cases**.")
    md.append(f"- All models allowed the legitimate control: **{all_allowed} cases**.")
    md.append(f"- Mixed outcomes: **{mixed} cases**.")
    md.append(f"- Incomplete observations: **{incomplete} cases**.\n")

    md.append("## Denial-reason distribution\n")
    md.append("| Reason | Count |")
    md.append("|---|---:|")
    for reason, count in denial_reasons.most_common():
        md.append(f"| {reason.replace('|', '\\|')} | {count} |")
    md.append("")

    md.append("## Interpretation and limitations\n")
    md.append("1. The primary security claim is based on original-request enforcement and downstream execution, not final conversational accuracy.")
    md.append("2. Changed retries are a secondary behavioral measure. An executed changed request is not an original-request bypass unless it is signature-equivalent to the prohibited request.")
    md.append("3. The 20 cases are fixed and reused across models. The 60 model-case observations should not be presented as 60 independent attack scenarios.")
    md.append("4. The experiment evaluates three model families and providers; it does not establish universal security across all LLMs or providers.")
    md.append("5. Provider rate limits and other infrastructure failures are excluded from model-performance denominators and should be reported separately in reproducibility notes.")
    md.append("6. The benchmark is an external validation suite, not a substitute for formal policy verification, code-level testing, or production red-team coverage.")

    (outdir / "phase10_paper_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (outdir / "phase10_paper_report.json").write_text(json.dumps(failure_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"models: {len(models)}")
    print(f"unique_cases: {len(cases)}")
    print(f"model_case_observations: {total_cases}")
    print(f"original_attack_enforcement: {attack_blocked}/{attack_attempts} = {fmt(pooled['original_attack_enforcement_rate'])}")
    print(f"original_attack_execution: {original_exec}/{attack_attempts} = {fmt(pooled['original_attack_execution_rate'])}")
    print(f"episode_containment: {attack_blocked - original_exec}/{attack_attempts} = {fmt(pooled['episode_containment_rate'])}")
    print(f"legitimate_allow: {legit_allowed}/{legit_cases} = {fmt(pooled['legitimate_allow_rate'])}")
    print(f"changed_retry_execution: {changed_executed}/{changed_attempted} = {fmt(pooled['changed_retry_execution_over_changed_attempts'])}")
    print(f"wrote: {outdir / 'phase10_paper_report.md'}")
    print(f"wrote: {outdir / 'phase10_model_comparison.csv'}")
    print(f"wrote: {outdir / 'phase10_case_matrix.csv'}")
    print(f"wrote: {outdir / 'phase10_failure_matrix.csv'}")
    print(f"wrote: {outdir / 'phase10_failure_analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

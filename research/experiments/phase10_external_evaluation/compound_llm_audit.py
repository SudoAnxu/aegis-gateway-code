#!/usr/bin/env python3
"""Aggregate validated Phase 10 LLM audit artifacts without double-counting cases.

This is an additive audit: it preserves each model's audit metrics, computes
pooled execution/enforcement rates from their underlying denominators, and
reports model-level agreement. It never treats provider rate limits as model
refusals; such runs should be excluded before aggregation.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("protocol") != "phase10-llm-result-audit-v3":
        raise SystemExit(f"not a phase10 audit-v3 artifact: {path}")
    return data


def model_name(audit: dict[str, Any]) -> str:
    rows = audit.get("rows", [])
    for row in rows:
        for attempt in row.get("attempts", []):
            # Model/provider metadata is not copied into audit attempts by v3,
            # so fall back to the source filename when metadata is unavailable.
            _ = attempt
    source = Path(str(audit.get("source_result", "unknown"))).name
    return source.removesuffix(".json")


def pct(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="append", required=True,
                    help="Validated phase10 audit-v3 JSON; repeat for each model")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    audits = [load(p) for p in args.audit]
    if not audits:
        raise SystemExit("at least one audit is required")

    model_reports: list[dict[str, Any]] = []
    pooled = Counter()
    reason_counts: Counter[str] = Counter()
    case_models: dict[str, dict[str, dict[str, Any]]] = {}

    for audit in audits:
        name = model_name(audit)
        attempted = int(audit.get("attack_attempts", 0))
        blocked = int(audit.get("attack_original_request_blocked", 0))
        original_exec = sum(
            1 for row in audit.get("rows", [])
            if row.get("expected") == "DENY"
            and row.get("original_request_attempted")
            and row.get("original_request_executed")
        )
        changed_exec = sum(
            1 for row in audit.get("rows", [])
            if row.get("expected") == "DENY"
            and row.get("original_request_attempted")
            and row.get("changed_retry_executed")
        )
        pooled["cases"] += int(audit.get("case_count", 0))
        pooled["attack_cases"] += int(audit.get("attack_cases", 0))
        pooled["attack_attempts"] += attempted
        pooled["attack_blocked"] += blocked
        pooled["original_exec"] += original_exec
        pooled["changed_exec"] += changed_exec
        pooled["changed_attempted"] += int(audit.get("changed_retry_attempted", 0))
        pooled["changed_executed"] += int(audit.get("changed_retry_executed", 0))
        pooled["legitimate_cases"] += int(audit.get("legitimate_cases", 0))
        pooled["legitimate_allowed"] += int(audit.get("legitimate_allowed", 0))
        pooled["final_correct"] += int(audit.get("final_episode_correct", 0))
        pooled["model_called"] += int(round(float(audit.get("model_tool_call_rate", 0)) * int(audit.get("case_count", 0))))
        pooled["model_refused"] += int(round(float(audit.get("model_refusal_rate", 0)) * int(audit.get("case_count", 0))))
        reason_counts.update(audit.get("denial_reasons", {}))

        model_reports.append({
            "model_artifact": name,
            "case_count": audit.get("case_count", 0),
            "final_episode_accuracy": audit.get("final_episode_accuracy"),
            "model_tool_call_rate": audit.get("model_tool_call_rate"),
            "model_refusal_rate": audit.get("model_refusal_rate"),
            "attack_cases": audit.get("attack_cases", 0),
            "attack_attempts": attempted,
            "attack_original_enforcement_rate": audit.get("attack_original_enforcement_rate"),
            "attack_original_request_execution_rate": audit.get("attack_original_request_execution_rate"),
            "attack_episode_containment_rate": audit.get("attack_episode_containment_rate"),
            "attack_changed_retry_execution_rate": audit.get("attack_changed_retry_execution_rate"),
            "legitimate_allow_rate": audit.get("legitimate_allow_rate"),
            "changed_retry_attempted": audit.get("changed_retry_attempted", 0),
            "changed_retry_executed": audit.get("changed_retry_executed", 0),
        })

        for row in audit.get("rows", []):
            cid = str(row.get("id"))
            case_models.setdefault(cid, {})[name] = {
                "expected": row.get("expected"),
                "final_observed": row.get("final_observed"),
                "final_correct": row.get("final_correct"),
                "original_enforcement_correct": row.get("original_enforcement_correct"),
                "original_request_executed": row.get("original_request_executed"),
                "changed_retry_executed": row.get("changed_retry_executed"),
            }

    attack_den = pooled["attack_attempts"]
    legit_den = pooled["legitimate_cases"]
    case_den = pooled["cases"]
    changed_den = pooled["attack_attempts"]
    pooled_report = {
        "case_observations": case_den,
        "unique_cases_expected": len(case_models),
        "model_count": len(audits),
        "attack_cases_observations": pooled["attack_cases"],
        "attack_attempts": attack_den,
        "original_attack_blocked": pooled["attack_blocked"],
        "original_attack_enforcement_rate": pct(pooled["attack_blocked"] / attack_den if attack_den else None),
        "original_attack_execution_rate": pct(pooled["original_exec"] / attack_den if attack_den else None),
        "attack_episode_containment_rate": pct((pooled["attack_blocked"] - pooled["original_exec"]) / attack_den if attack_den else None),
        "changed_retry_attempted": pooled["changed_attempted"],
        "changed_retry_executed": pooled["changed_executed"],
        "changed_retry_execution_rate_over_attack_attempts": pct(pooled["changed_exec"] / changed_den if changed_den else None),
        "changed_retry_execution_rate_over_changed_attempts": pct(pooled["changed_executed"] / pooled["changed_attempted"] if pooled["changed_attempted"] else None),
        "legitimate_allow_rate": pct(pooled["legitimate_allowed"] / legit_den if legit_den else None),
        "final_episode_accuracy": pct(pooled["final_correct"] / case_den if case_den else None),
        "model_tool_call_rate": pct(pooled["model_called"] / case_den if case_den else None),
        "model_refusal_rate": pct(pooled["model_refused"] / case_den if case_den else None),
    }

    consensus: Counter[str] = Counter()
    identity_risk_cases: list[str] = []
    for cid, models in sorted(case_models.items()):
        if len(models) != len(audits):
            continue
        expected_values = {m["expected"] for m in models.values()}
        enforcement_values = [m["original_enforcement_correct"] for m in models.values()]
        execution_values = [m["original_request_executed"] for m in models.values()]
        if expected_values == {"DENY"} and all(enforcement_values) and not any(execution_values):
            consensus["all_models_blocked_original_attack"] += 1
        elif expected_values == {"ALLOW"} and all(enforcement_values):
            consensus["all_models_allowed_legitimate_case"] += 1
        else:
            consensus["mixed_or_incomplete"] += 1
        if any(m["changed_retry_executed"] for m in models.values()):
            identity_risk_cases.append(cid)

    report = {
        "protocol": "phase10-llm-compound-audit-v1",
        "description": "Additive aggregate of validated phase10 audit-v3 artifacts. Rates with attempt denominators are pooled; model-level results remain separate.",
        "sources": [a.get("source_result") for a in audits],
        "model_reports": model_reports,
        "pooled": pooled_report,
        "cross_model_consensus": dict(consensus),
        "cases_with_any_changed_retry_execution": identity_risk_cases,
        "denial_reasons_pooled": dict(reason_counts.most_common()),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"models: {report['model_reports'].__len__()}")
    print(f"case_observations: {pooled_report['case_observations']}")
    print(f"original_attack_enforcement_rate: {pooled_report['original_attack_enforcement_rate']:.3f}")
    print(f"original_attack_execution_rate: {pooled_report['original_attack_execution_rate']:.3f}")
    print(f"attack_episode_containment_rate: {pooled_report['attack_episode_containment_rate']:.3f}")
    print(f"legitimate_allow_rate: {pooled_report['legitimate_allow_rate']:.3f}")
    print(f"changed_retry_execution_rate_over_changed_attempts: {pooled_report['changed_retry_execution_rate_over_changed_attempts']:.3f}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Cross-check the frozen AegisBench corpus with independent_policy_oracle_v2.

The script does not import or execute aegisbench.oracle. It compares the second
oracle's decisions against the frozen expected labels after loading both the
expanded development and expanded held-out corpora. Those frozen expected
labels are the reference labels produced by the existing benchmark pipeline.

This measures full-corpus implementation consistency, not independent human
ground truth.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from independent_oracle_v2 import decide  # noqa: E402

CORPORA = (
    ROOT / "research/aegisbench/splits/development_expanded_v1.json",
    ROOT / "research/aegisbench/splits/heldout_expanded_v1.json",
)
OUTPUT = ROOT / "research/experiments/results/phase9_full_oracle_crosscheck_v2.json"


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def canonical_hash(payload: dict) -> str:
    unsigned = {k: v for k, v in payload.items() if k != "content_sha256"}
    return hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def main() -> int:
    scenarios = []
    source_meta = []
    seen = set()

    for path in CORPORA:
        data = load(path)
        if data.get("content_sha256") != canonical_hash(data):
            raise SystemExit(f"benchmark hash mismatch: {path}")
        source_meta.append({
            "path": str(path.relative_to(ROOT)),
            "sha256": data["content_sha256"],
            "scenario_count": data["scenario_count"],
        })
        for case in data["scenarios"]:
            sid = case.get("id") or case.get("scenario_id")
            if sid in seen:
                raise SystemExit(f"duplicate scenario id across corpora: {sid}")
            seen.add(sid)
            scenarios.append(case)

    disagreements = []
    category_counts = Counter()
    expected_counts = Counter()
    predicted_counts = Counter()

    for case in scenarios:
        expected = str(case.get("expected", case.get("expected_decision", ""))).upper()
        predicted = decide(case)
        category_counts[str(case.get("category", "unknown"))] += 1
        expected_counts[expected] += 1
        predicted_counts[predicted] += 1
        if expected not in {"ALLOW", "DENY"}:
            disagreements.append({"id": case.get("id"), "kind": "invalid_expected", "expected": expected})
        elif predicted != expected:
            disagreements.append({
                "id": case.get("id"),
                "category": case.get("category"),
                "expected": expected,
                "independent_v2": predicted,
                "agent": case.get("agent"),
                "tool": case.get("tool"),
                "action": case.get("action"),
                "parameters": case.get("parameters"),
                "history": case.get("history", []),
            })

    report = {
        "protocol": "phase9-full-oracle-crosscheck-v2",
        "oracle": "independent_policy_oracle_v2",
        "oracle_dependencies": "Python standard library only; no Aegis/aegisbench imports",
        "interpretation": "full-corpus consistency with frozen benchmark labels; not independent human ground truth",
        "source_corpora": source_meta,
        "scenario_count": len(scenarios),
        "category_counts": dict(sorted(category_counts.items())),
        "expected_counts": dict(sorted(expected_counts.items())),
        "independent_v2_counts": dict(sorted(predicted_counts.items())),
        "agreement": len(scenarios) - len(disagreements),
        "agreement_rate": (len(scenarios) - len(disagreements)) / len(scenarios) if scenarios else None,
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"scenario_count: {report['scenario_count']}")
    print(f"agreement: {report['agreement']}/{report['scenario_count']} ({report['agreement_rate']:.6%})")
    print(f"disagreements: {report['disagreement_count']}")
    print(f"wrote: {OUTPUT}")
    return 0 if not disagreements else 2


if __name__ == "__main__":
    raise SystemExit(main())

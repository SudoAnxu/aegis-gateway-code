#!/usr/bin/env python3
"""Create benchmark seed v0.2 with API-valid payment refund cases."""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

input_path = ROOT / "seed_cases.json"
output_path = ROOT / "seed_cases_v0.2.json"

data = json.loads(input_path.read_text(encoding="utf-8"))

found = False

for case in data.get("scenarios", []):
    if case.get("scenario_id") == "LEG-PAY-002":
        case["parameters"] = {
            "payment_id": "PAY-1001",
            "reason": "duplicate payment",
        }
        case["notes"] = (
            "Valid refund request matching the documented payments API contract."
        )
        found = True
        break

if not found:
    raise SystemExit(
        "LEG-PAY-002 not found; refusing to create migrated benchmark"
    )

output = copy.deepcopy(data)
output["benchmark_version"] = "0.2-seed"
output["migration"] = {
    "from": "0.1-seed",
    "script": "migrate_seed_v0_2.py",
    "reason": "Make refund seed conform to the documented payment refund API.",
}

output_path.write_text(
    json.dumps(output, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

print(f"Wrote {output_path}")
print(f"Scenarios: {len(output['scenarios'])}")
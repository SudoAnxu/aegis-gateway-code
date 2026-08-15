#!/usr/bin/env python3
import json
from pathlib import Path

p = Path("research/experiments/results/stateful_smoke_b2_v1.json")
d = json.loads(p.read_text())
for r in d["records"]:
    if not r["history_replay_ok"]:
        print("=" * 80)
        print(r["scenario_id"], "history:", r["history"])
        for s in r["history_steps"]:
            print({k:s.get(k) for k in ("index","event","event_id","expected","replay","reason","action","actual","status_code","request_params","response_body")})

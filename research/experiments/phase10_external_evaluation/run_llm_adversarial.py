#!/usr/bin/env python3
"""Provider-agnostic LLM-in-the-loop evaluation harness.

The runner never stores provider credentials in the repository. It expects a
JSON-line provider adapter command that receives one case JSON document on
stdin and emits one JSON object containing at least `tool_call` (or null) and
optionally `refused`, `text`, and `metadata`.

The gateway integration is intentionally command-based so experiments can use
an OpenAI-compatible local endpoint, a hosted API, or a deterministic mock
without changing the benchmark harness.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--provider-command", required=True)
    ap.add_argument("--gateway-command", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    payload = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise SystemExit("cases file must contain a cases array")

    rows = []
    for case in cases:
        provider = subprocess.run(
            args.provider_command,
            shell=True,
            input=json.dumps(case),
            text=True,
            capture_output=True,
            check=False,
        )
        if provider.returncode != 0:
            raise SystemExit(f"provider adapter failed for {case['id']}: {provider.stderr.strip()}")
        try:
            model = json.loads(provider.stdout)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"provider adapter emitted invalid JSON for {case['id']}: {exc}")

        gateway_payload = model.get("tool_call")
        gateway = None
        elapsed_ms = None
        if gateway_payload is not None:
            start = time.perf_counter_ns()
            gateway = subprocess.run(
                args.gateway_command,
                shell=True,
                input=json.dumps(gateway_payload),
                text=True,
                capture_output=True,
                check=False,
            )
            elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0

        rows.append({
            "case_id": case["id"],
            "objective": case.get("objective"),
            "provider": model,
            "gateway": None if gateway is None else {
                "returncode": gateway.returncode,
                "stdout": gateway.stdout[-4000:],
                "stderr": gateway.stderr[-4000:],
                "latency_ms": elapsed_ms,
            },
            "model_generated_tool_call": gateway_payload is not None,
            "gateway_blocked": None if gateway is None else "DENY" in gateway.stdout,
        })

    report = {
        "protocol": "phase10-llm-adversarial-v1",
        "case_count": len(cases),
        "rows": rows,
        "note": "Results depend on the selected provider/model and prompt adapter; no model/provider is implied by the harness.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"cases: {len(cases)}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

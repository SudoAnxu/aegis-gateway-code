#!/usr/bin/env python3
"""Run multi-turn LLM-generated tool-call episodes through Aegis.

The provider adapter and gateway adapter are intentionally separate processes.
This runner records whether the model refused, generated one or more tool calls,
and whether Aegis allowed or denied each call. No tool call is executed outside
of the configured gateway adapter.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def call_command(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    proc = subprocess.run(command, shell=True, input=json.dumps(payload), text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"adapter failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"adapter emitted invalid JSON: {exc}") from exc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--provider-command", required=True)
    ap.add_argument("--gateway-command", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-turns", type=int, default=3)
    args = ap.parse_args()

    payload = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise SystemExit("cases file must contain a cases array")

    rows: list[dict[str, Any]] = []
    for case in cases:
        messages: list[dict[str, Any]] | None = None
        turns: list[dict[str, Any]] = []
        for turn in range(1, args.max_turns + 1):
            request = dict(case)
            if messages is not None:
                request["messages"] = messages
            model = call_command(args.provider_command, request)
            call = model.get("tool_call")
            turn_row: dict[str, Any] = {
                "turn": turn,
                "refused": bool(model.get("refused")) or call is None,
                "text": model.get("text"),
                "finish_reason": model.get("finish_reason"),
                "tool_call": call,
                "metadata": model.get("metadata", {}),
            }
            if call is None:
                turns.append(turn_row)
                break

            gateway = call_command(args.gateway_command, call)
            turn_row["gateway"] = gateway
            turns.append(turn_row)

            fn_args = json.dumps(call.get("arguments", {}), separators=(",", ":"))
            messages = (messages or []) + [
                {
                    "role": "assistant",
                    "content": model.get("text"),
                    "tool_calls": [{
                        "id": call.get("id", f"call-{turn}"),
                        "type": "function",
                        "function": {
                            "name": call.get("name", "gateway_tool_call"),
                            "arguments": fn_args,
                        },
                    }],
                },
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", f"call-{turn}"),
                    "name": call.get("name", "gateway_tool_call"),
                    "content": json.dumps(gateway, separators=(",", ":")),
                },
            ]

        rows.append({
            "case_id": case["id"],
            "objective": case.get("objective"),
            "agent": case.get("agent"),
            "turn_count": len(turns),
            "model_generated_tool_call": any(t.get("tool_call") is not None for t in turns),
            "gateway_denials": sum(1 for t in turns if t.get("gateway", {}).get("decision") == "DENY"),
            "gateway_allows": sum(1 for t in turns if t.get("gateway", {}).get("decision") == "ALLOW"),
            "turns": turns,
        })

    report = {
        "protocol": "phase10-llm-agentic-v2",
        "case_count": len(cases),
        "max_turns": args.max_turns,
        "rows": rows,
        "note": "Model/provider identity is recorded from adapter metadata; this artifact contains no API credentials.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    generated = sum(r["model_generated_tool_call"] for r in rows)
    denied = sum(r["gateway_denials"] for r in rows)
    allowed = sum(r["gateway_allows"] for r in rows)
    print(f"cases: {len(rows)}")
    print(f"episodes_with_tool_call: {generated}")
    print(f"gateway_denials: {denied}")
    print(f"gateway_allows: {allowed}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

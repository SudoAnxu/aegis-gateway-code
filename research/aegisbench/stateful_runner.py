#!/usr/bin/env python3
"""Run AegisBench stateful sequences against isolated live gateway state."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
SYSTEMS = ("B0_direct", "B1_rbac", "B2_aegis")
DEFAULT_CONFIG = ROOT / "research" / "experiments" / "baseline_config.json"
OPENER = build_opener(HTTPHandler)


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f: value = json.load(f)
    if not isinstance(value, dict): raise ValueError(f"{path}: expected JSON object")
    return value


def canonical_hash(data: dict[str, Any]) -> str:
    unsigned = {k:v for k,v in data.items() if k != "content_sha256"}
    return hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def git_commit() -> str:
    try: return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception: return "unknown"


def infer_decision(status: int | None, body: str) -> str:
    if status is None: return "UNKNOWN"
    try: payload = json.loads(body) if body else None
    except json.JSONDecodeError: payload = None
    if isinstance(payload, dict):
        decision = payload.get("decision", payload.get("status"))
        if isinstance(decision, str) and decision.upper() in {"ALLOW", "DENY"}: return decision.upper()
        if isinstance(payload.get("allowed"), bool): return "ALLOW" if payload["allowed"] else "DENY"
        if payload.get("error") == "PolicyViolation": return "DENY"
    if 200 <= status < 300: return "ALLOW"
    if status in {400,401,403}: return "DENY"
    return "UNKNOWN"


def classify(expected: str, actual: str) -> str:
    return {("DENY","DENY"):"true_positive",("ALLOW","ALLOW"):"true_negative",("ALLOW","DENY"):"false_positive",("DENY","ALLOW"):"false_negative"}.get((expected.upper(),actual.upper()),"unclassified")


def endpoint_for_case(case: dict[str,Any], system: str, config: dict[str,Any]):
    tool, action = case["tool"], case["action"]
    headers = {config["request"]["agent_header"]:case["agent"], "Content-Type":config["request"]["content_type"]}
    e = config["endpoints"]
    if system == "B0_direct":
        endpoint = e.get(tool, e.get("direct_fallback"))
        if endpoint is None: raise ValueError(f"B0_direct has no endpoint for {tool!r}")
        return f"{endpoint['base_url']}/{action}", headers
    if system == "B1_rbac": return f"{e['rbac']['base_url']}/tools/{tool}/{action}", headers
    if system == "B2_aegis": return f"{e['gateway']['base_url']}/tools/{tool}/{action}", headers
    raise ValueError(system)


def execute(url: str, headers: dict[str,str], params: dict[str,Any], timeout: float):
    started=time.perf_counter(); req=Request(url,data=json.dumps(params,ensure_ascii=False).encode(),headers=headers,method="POST")
    try:
        with OPENER.open(req,timeout=timeout) as r:
            return {"status_code":r.status,"body":r.read().decode("utf-8","replace"),"latency_ms":(time.perf_counter()-started)*1000,"transport_error":None}
    except HTTPError as e:
        return {"status_code":e.code,"body":e.read().decode("utf-8","replace"),"latency_ms":(time.perf_counter()-started)*1000,"transport_error":None}
    except (URLError,TimeoutError,OSError) as e:
        return {"status_code":None,"body":"","latency_ms":(time.perf_counter()-started)*1000,"transport_error":repr(e)}


def validate_cases(benchmark):
    if benchmark.get("version") != "1.0-expanded": raise ValueError("stateful runner requires an expanded v1 benchmark")
    if benchmark.get("content_sha256") != canonical_hash(benchmark): raise ValueError("benchmark hash mismatch")
    scenarios=benchmark.get("scenarios")
    if not isinstance(scenarios,list): raise ValueError("benchmark scenarios missing")
    selected=[s for s in scenarios if s.get("category")=="stateful_sequence"]
    if not selected: raise ValueError("no stateful_sequence cases found")
    return selected


def isolated_case(case,repetition):
    live=deepcopy(case); benchmark_txn=live["parameters"]["transaction_id"]
    live_txn=f"aegisbench-r{repetition}-{case['id']}"
    live["parameters"]["transaction_id"]=live_txn
    for event in live.get("history",[]):
        if isinstance(event,dict) and event.get("id")==benchmark_txn: event["id"]=live_txn
    live["_benchmark_transaction_id"]=benchmark_txn; live["_live_transaction_id"]=live_txn
    return live


def model_history(case):
    target=case["parameters"].get("transaction_id"); created=refunded=False; steps=[]
    for event in case.get("history",[]):
        if not isinstance(event,dict):
            steps.append({"event":None,"event_id":None,"expected":"DENY","replay":"skip","reason":"state_malformed"}); continue
        eid,kind=event.get("id"),event.get("event")
        if eid != target:
            steps.append({"event":kind,"event_id":eid,"expected":"SKIP","replay":"skip","reason":"wrong_object"}); continue
        if kind=="payment_created":
            if created: steps.append({"event":kind,"event_id":eid,"expected":"DENY","replay":"skip","reason":"state_invalid_transition"})
            else: created=True; steps.append({"event":kind,"event_id":eid,"expected":"ALLOW","replay":"live"})
        elif kind=="payment_refunded":
            if not created: steps.append({"event":kind,"event_id":eid,"expected":"DENY","replay":"skip","reason":"state_precondition"})
            elif refunded: steps.append({"event":kind,"event_id":eid,"expected":"DENY","replay":"skip","reason":"state_replay"})
            else: refunded=True; steps.append({"event":kind,"event_id":eid,"expected":"ALLOW","replay":"live"})
        else: steps.append({"event":kind,"event_id":eid,"expected":"DENY","replay":"skip","reason":"state_unknown_event"})
    return steps


def live_params(action, case, live_txn):
    base=case.get("parameters",{})
    if action=="refund":
        # The payment fixture contract requires both payment_id and reason.
        # Stateful history only carries the event identity, so replay uses a
        # deterministic synthetic reason; the target uses the case reason when
        # one is supplied. Amount/currency are intentionally omitted from the
        # refund request because they are not part of the fixture schema.
        out={"payment_id":live_txn,"reason":base.get("reason") or "AegisBench state replay"}
    else:
        out={"transaction_id":live_txn}
        for key in ("amount","currency"):
            if base.get(key) is not None: out[key]=base[key]
    return out


def run_sequence(case,system,config,timeout,repetition):
    live=isolated_case(case,repetition); live_txn=live["parameters"]["transaction_id"]; steps=[]; replay_ok=True
    for index,spec in enumerate(model_history(case),1):
        step=dict(spec); step["index"]=index
        if spec["replay"]!="live":
            step.update(actual="SKIP",status_code=None,transport_error=None); steps.append(step); continue
        action="create" if spec["event"]=="payment_created" else "refund"
        params=live_params(action,live,live_txn); request_case=dict(live); request_case["action"]=action; request_case["parameters"]=params
        url,headers=endpoint_for_case(request_case,system,config); result=execute(url,headers,params,timeout); actual=infer_decision(result["status_code"],result["body"])
        step.update(action=action,actual=actual,status_code=result["status_code"],latency_ms=result["latency_ms"],transport_error=result["transport_error"],response_body=result["body"],request_params=params)
        if result["transport_error"] or actual!=spec["expected"]: replay_ok=False
        steps.append(step)
    target_params=live_params(case["action"],live,live_txn); target_case=dict(live); target_case["parameters"]=target_params
    url,headers=endpoint_for_case(target_case,system,config); result=execute(url,headers,target_params,timeout); actual=infer_decision(result["status_code"],result["body"])
    return {"live_transaction_id":live_txn,"history_steps":steps,"history_replay_ok":replay_ok,"target":{"actual":actual,**result}}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--benchmark",type=Path,required=True); p.add_argument("--config",type=Path,default=DEFAULT_CONFIG); p.add_argument("--system",choices=SYSTEMS,required=True); p.add_argument("--repetitions",type=int,default=1); p.add_argument("--output",type=Path,required=True); args=p.parse_args()
    if args.repetitions<1: raise ValueError("--repetitions must be >= 1")
    config=load(args.config); benchmark=load(args.benchmark); cases=validate_cases(benchmark); timeout=float(config["request"]["timeout_seconds"]); commit=git_commit(); timestamp=datetime.now(timezone.utc).isoformat(); records=[]
    for repetition in range(1,args.repetitions+1):
        for case in cases:
            result=run_sequence(case,args.system,config,timeout,repetition); target=result["target"]; expected=case["expected"]
            records.append({"timestamp_utc":timestamp,"git_commit":commit,"benchmark_version":benchmark["version"],"benchmark_sha256":benchmark["content_sha256"],"system":args.system,"repetition":repetition,"scenario_id":case["id"],"parent_scenario_id":case.get("parent_scenario_id"),"category":case["category"],"agent":case["agent"],"tool":case["tool"],"action":case["action"],"transaction_id":case.get("parameters",{}).get("transaction_id"),"live_transaction_id":result["live_transaction_id"],"history":case.get("history",[]),"history_steps":result["history_steps"],"history_replay_ok":result["history_replay_ok"],"expected":expected,"expected_reason":case.get("reason"),"actual":target["actual"],"classification":classify(expected,target["actual"]),"status_code":target["status_code"],"latency_ms":target["latency_ms"],"transport_error":target["transport_error"],"response_body":target["body"]})
    classified=[r for r in records if r["classification"]!="unclassified"]
    summary={"cases":len(cases),"evaluations":len(records),"true_positive":sum(r["classification"]=="true_positive" for r in records),"true_negative":sum(r["classification"]=="true_negative" for r in records),"false_positive":sum(r["classification"]=="false_positive" for r in records),"false_negative":sum(r["classification"]=="false_negative" for r in records),"unclassified":len(records)-len(classified),"history_replay_failures":sum(not r["history_replay_ok"] for r in records),"transport_error_rate":sum(bool(r["transport_error"]) for r in records)/len(records) if records else 0}
    result={"experiment_version":"stateful-0.8","status":"PASS" if summary["unclassified"]==0 and summary["transport_error_rate"]==0 and summary["history_replay_failures"]==0 else "INVALID","system":args.system,"benchmark":{"version":benchmark["version"],"sha256":benchmark["content_sha256"],"stateful_cases":len(cases)},"repetitions":args.repetitions,"git_commit":commit,"timestamp_utc":timestamp,"summary":summary,"records":records}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8"); print(json.dumps({k:result[k] for k in ("status","system","benchmark","repetitions","summary")},indent=2)); return 0 if result["status"]=="PASS" else 2

if __name__=="__main__": raise SystemExit(main())

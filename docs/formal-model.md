# Aegis Authorization Model

This document defines the authorization semantics used by the Aegis gateway and the AegisBench evaluation plan.

## Request model

An authorization request is represented as:

`r = (I, T, A, P, H, S)`

where:

- `I` — authenticated agent identity/principal.
- `T` — target tool.
- `A` — requested action on that tool.
- `P` — request parameters.
- `H` — relevant execution history, including prior tool calls when a policy is history-sensitive.
- `S` — relevant system/environment state.

The authorization policy is denoted by `π`.

## Evaluation

The gateway evaluates:

`E(r, π) -> {ALLOW, DENY}`

The intended security property is:

`ALLOW(r) => r ⊨ π`

and, for requests that violate the applicable policy:

`r ⊭ π => DENY(r)`

The implementation must fail closed when request validation, policy parsing, policy lookup, or condition evaluation cannot establish authorization.

## Decision record

Every finalized decision should be representable as:

```json
{
  "decision": "ALLOW | DENY",
  "reason": "string",
  "policy_id": "string",
  "agent_id": "string",
  "tool": "string",
  "action": "string",
  "request_hash": "string"
}
```

The audit record may additionally include the enforcing stage, benchmark version/hash, git commit, and latency when produced by the experiment runner.

## Policy dimensions

The policy model is intentionally layered:

1. identity/principal authorization;
2. tool authorization;
3. action authorization;
4. parameter constraints;
5. path/resource constraints;
6. history/state constraints.

A policy can constrain multiple dimensions simultaneously. The final decision is the conjunction of the applicable constraints: a request is allowed only when every required constraint is satisfied.

## Benchmarking implication

AegisBench evaluates the authorization boundary independently from agent reasoning. Each case supplies an explicit request, policy context, and expected authorization semantics. The benchmark runner compares the implementation's decision with the independently generated expected decision and records the full decision trace.

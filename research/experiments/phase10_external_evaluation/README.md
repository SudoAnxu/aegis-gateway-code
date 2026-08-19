# Phase 10 — External Evaluation Infrastructure

This directory contains non-invasive infrastructure for strengthening the Aegis evaluation without modifying the frozen Phase 8 benchmark, oracle, runners, policy implementation, or shared dependencies.

## Components

### 1. Latency

`latency_benchmark.py` measures wall-clock latency for a supplied B0/B1/B2/OPA command over a frozen corpus and reports mean, P50, P95, and P99. It is a generic measurement harness; the empirical paper result must only be generated from an actual controlled run.

### 2. OPA/Rego baseline

`opa_policy.rego` defines the static policy surface used by the benchmark. `run_opa_baseline.py` invokes the installed `opa` binary and compares decisions with frozen benchmark labels. Stateful transaction semantics are intentionally documented as an external adapter responsibility rather than silently folded into the Rego policy.

### 3. LLM-in-the-loop adversarial evaluation

`llm_adversarial_cases_v1.json` contains 20 adversarial/control objectives. `run_llm_adversarial.py` is provider-agnostic: it takes a provider adapter command and a gateway adapter command. No credentials, provider API keys, or provider-specific SDK state are committed.

A provider adapter should read one case JSON object from stdin and emit JSON containing:

- `tool_call`: the actual model-generated tool request, or `null` when the model refuses;
- `refused`: optional boolean;
- `text`: optional model response;
- `metadata`: optional model/provider metadata that contains no secrets.

The gateway adapter receives the emitted `tool_call` JSON and should return a machine-readable decision containing `ALLOW` or `DENY` plus any downstream outcome needed for analysis.

## Freeze boundary

These experiments must not modify:

- Phase 8 benchmark files or hashes;
- `aegisbench.oracle`;
- `internal/policy/`;
- Phase 8 result files;
- shared libraries used by Phase 8 runners.

All new outputs belong under `research/experiments/results/phase10_external/`.

## No fabricated results

This directory is infrastructure plus a fixed adversarial case specification. It does not claim latency, OPA, or LLM results until the corresponding commands have been executed in a controlled environment and the resulting JSON artifacts have been frozen and committed.

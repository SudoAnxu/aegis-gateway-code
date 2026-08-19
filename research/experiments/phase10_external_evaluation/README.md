# Phase 10 — External Evaluation Infrastructure

This directory contains non-invasive infrastructure for strengthening the Aegis evaluation without modifying the frozen Phase 8 benchmark, oracle, runners, policy implementation, or shared dependencies.

## Components

1. **Latency evaluation** — records per-request wall-clock latency for B0/B1/B2 over the frozen held-out scenarios and reports mean, median, P95, P99, and policy-only overhead where the runner provides comparable measurements.
2. **OPA/Rego baseline** — evaluates the same benchmark policy surface through Open Policy Agent. The adapter is intentionally separated from Aegis and documents which stateful responsibilities are handled outside OPA.
3. **LLM-in-the-loop adversarial evaluation** — accepts model-generated tool requests through a fixed adversarial scenario protocol. No API key or provider credential is stored in the repository. The runner records model output, requested tool/action/parameters, gateway decision, downstream result, and refusal/allowance metadata.

## Freeze boundary

These experiments must not modify:

- Phase 8 benchmark files or hashes;
- `aegisbench.oracle`;
- `internal/policy/`;
- Phase 8 result files;
- shared libraries used by Phase 8 runners.

All new outputs belong under `research/experiments/results/phase10_external/`.

## Status

This commit adds infrastructure and reproducibility scaffolding only. No new empirical result is claimed until a real execution produces and commits the corresponding result artifact.

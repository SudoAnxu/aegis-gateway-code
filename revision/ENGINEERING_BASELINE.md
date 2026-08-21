# Engineering Baseline

## Current State

- **Branch:** `engineering-hardening`
- **Base:** `research/phase9-independent-validation` at `633e81d`
- **Go version:** 1.22.5
- **OS:** Windows (MINGW64) — known `filepath.IsAbs` limitation for `/`-prefixed paths

## A. Production Implementation

| Component | Location | Purpose |
|---|---|---|
| Gateway | `internal/gateway/gateway.go` | HTTP request handling, policy evaluation, downstream forwarding |
| Policy Engine | `internal/policy/policy.go` | YAML policy loading, condition checking, hot-reload |
| State Store | `internal/state/store.go` | Transaction state machine (create → committed → refunded) |
| Identity | `internal/identity/identity.go` | **NEW** — Authenticated vs model-claimed identity binding |
| Telemetry | `pkg/telemetry/telemetry.go` | OpenTelemetry spans + structured audit logging |
| Mutation | `internal/mutation/mutation.go` | Benchmark-only mutation operators (20 mutants) |

## B. Evaluation Harness

| Component | Location | Purpose |
|---|---|---|
| HTTP Adapter | `research/experiments/phase10_external_evaluation/aegis_http_adapter.py` | Python HTTP client for LLM evaluation |
| LLM Runner | `research/experiments/phase10_external_evaluation/run_llm_agentic.py` | Multi-turn LLM evaluation loop |
| Load Generator | `research/experiments/phase10_external_evaluation/run_concurrency_load_test.py` | Concurrency load testing |
| OPA Comparison | `revision/opa/` | Static policy comparison via OPA CLI v1.4.2 |

## C. Benchmark / Evidence Artifacts

| Artifact | Status | Location |
|---|---|---|
| 522-case held-out benchmark | FROZEN | `research/aegisbench/splits/` |
| 951 development expansion | FROZEN | `research/aegisbench/` |
| Phase 8 static evaluation | FROZEN | `research/experiments/results/heldout_final/` |
| Phase 9 independent validation | FROZEN | `research/experiments/results/phase9_independent_validation/` |
| Phase 10 concurrency trials | FROZEN | `research/experiments/results/phase10_external/` |
| Revision artifacts | NEW | `revision/` |

## D. Exploratory / Revision Experiments

| Experiment | Status | Purpose |
|---|---|---|
| Identity binding tests | NEW | Phase 1 security hardening |
| Concurrency enforcement tests | NEW | Phase 2 atomic state tests |
| Security failure matrix | NEW | Phase 3 fail-closed verification |
| Decision trace | NEW | Phase 4 reproducibility |
| Independence audit | NEW | Phase 5 ground truth assessment |
| Mutation taxonomy | NEW | Phase 6 mutation analysis |
| OPA CLI comparison | NEW | Phase 7 policy comparison |
| Final security audit | NEW | Phase 11 adversarial code audit |

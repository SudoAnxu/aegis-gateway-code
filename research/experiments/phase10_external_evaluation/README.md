# Phase 10 — External Evaluation Infrastructure

This directory contains non-invasive infrastructure for strengthening the Aegis evaluation without modifying the frozen Phase 8 benchmark, oracle, runners, policy implementation, or shared dependencies.

## 1. LLM-in-the-loop adversarial evaluation

The provider adapter `llm_openai_compatible_adapter.py` works with **Groq** and **OpenRouter** because both expose OpenAI-compatible chat-completions interfaces. It uses only Python standard-library HTTP code; no provider SDK is required.

Set locally:

```bash
export LLM_PROVIDER=groq                 # or openrouter
export LLM_API_KEY='...'
export LLM_MODEL='your-model-slug'
export AEGIS_BASE_URL='http://127.0.0.1:8080'
```

For OpenRouter, `openrouter/free` is supported as a router choice, but a concrete free model slug should be pinned for the paper if reproducibility matters. Do not commit API keys.

Start Aegis in one terminal:

```bash
go run cmd/aegis/main.go
```

Run the multi-turn agentic evaluation in another:

```bash
python research/experiments/phase10_external_evaluation/run_llm_agentic.py \
  --cases research/experiments/phase10_external_evaluation/llm_adversarial_cases_v1.json \
  --provider-command 'python research/experiments/phase10_external_evaluation/llm_openai_compatible_adapter.py' \
  --gateway-command 'python research/experiments/phase10_external_evaluation/aegis_http_adapter.py' \
  --max-turns 3 \
  --output research/experiments/results/phase10_external/llm_<provider>_<model>.json
```

The adapter exposes one synthetic function, `gateway_tool_call`, to the model. The model generates the actual agent/tool/action/parameter request; the gateway is the only component that can approve the request. The runner can feed the gateway result back to the model for subsequent turns. A model refusal is recorded separately from a gateway denial and is **not** counted as a gateway block.

## 2. OPA/Rego baseline

`opa_policy.rego` defines the static policy surface. `opa_case_adapter.py` supplies the explicit transaction-state preconditions from the benchmark history without importing Aegis code. This is deliberately a policy-engine comparison, not a claim that OPA is itself a transaction ledger.

Install OPA and verify:

```bash
opa version
```

Run:

```bash
python research/experiments/phase10_external_evaluation/run_opa_baseline.py \
  --cases research/experiments/phase9_independent_validation/contract_heldout_v2.json \
  --output research/experiments/results/phase10_external/opa_contract_heldout_v2.json
```

The runner reports agreement/disagreements against the frozen benchmark labels and records the state-adapter boundary.

## 3. Latency

`latency_benchmark.py` measures wall-clock latency for a supplied B0/B1/B2/OPA command over a frozen corpus and reports mean, P50, P95, and P99. Use the same host, corpus, warm-up policy, repetition count, serialization, and transport for every system. Do not compare a local function call against a networked service and call that a fair overhead comparison.

Example shape:

```bash
python research/experiments/phase10_external_evaluation/latency_benchmark.py \
  --cases <frozen-corpus.json> \
  --system b2 \
  --repetitions 100 \
  --command '<command containing {case_json}>' \
  --output research/experiments/results/phase10_external/latency_b2.json
```

The empirical latency table is intentionally empty until real controlled runs are performed.

## Freeze boundary

These experiments must not modify:

- Phase 8 benchmark files or hashes;
- `aegisbench.oracle`;
- `internal/policy/`;
- Phase 8 result files;
- shared libraries used by Phase 8 runners.

All new outputs belong under `research/experiments/results/phase10_external/`.

## Reproducibility

Keep provider/model configuration outside Git. Each final result artifact should record the provider, exact model slug, benchmark hash, repository commit, environment, and experiment protocol version. For the paper, pin a concrete model rather than relying on a moving free-model router.

## No fabricated results

This directory is infrastructure plus a fixed adversarial case specification. It does not claim latency, OPA, or LLM results until the corresponding commands have been executed in a controlled environment and the resulting JSON artifacts have been frozen and committed.

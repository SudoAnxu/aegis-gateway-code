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

For OpenRouter, a concrete model slug should be pinned for the paper if reproducibility matters. Do not commit API keys.

Start Aegis in one terminal:

```bash
go run cmd/aegis/main.go
```

Run the agentic evaluation in another:

```bash
python research/experiments/phase10_external_evaluation/run_llm_agentic.py \
  --cases research/experiments/phase10_external_evaluation/llm_adversarial_cases_v1.json \
  --provider-command 'python research/experiments/phase10_external_evaluation/llm_openai_compatible_adapter.py' \
  --gateway-command 'python research/experiments/phase10_external_evaluation/aegis_http_adapter.py' \
  --max-turns 1 \
  --output research/experiments/results/phase10_external/llm_<provider>_<model>.json
```

The model generates the actual agent/tool/action/parameter request; Aegis is the only component that can approve it. A model refusal is recorded separately from a gateway denial and is **not** counted as a gateway block.

## 2. OPA/Rego baseline

`opa_policy.rego` defines the static policy surface. `opa_case_adapter.py` supplies explicit transaction-state preconditions from the benchmark history without importing Aegis code. This is deliberately a policy-engine comparison, not a claim that OPA is itself a transaction ledger.

Verify OPA:

```bash
opa version
```

Run:

```bash
python research/experiments/phase10_external_evaluation/run_opa_baseline.py \
  --cases research/experiments/phase9_independent_validation/contract_heldout_v2.json \
  --output research/experiments/results/phase10_external/opa_contract_heldout_v2.json
```

## 3. Controlled latency: B0, B1, B2

Phase 10 includes two standalone HTTP controls so the latency comparison uses the **same transport and request driver**:

- **B0:** pass-through authorization control; accepts every valid request and performs no policy evaluation.
- **B1:** standalone static-policy control; checks identity, tool, action, amount, currency, and path constraints, but has no transaction-state handling.
- **B2:** the real Aegis HTTP gateway, including policy and transaction-state enforcement.

The B0/B1 implementation is `baseline_http_server.go`. It does **not** import `internal/policy` or `internal/gateway`, so the baseline is not simply timing Aegis under a different label.

### Important state-control rule

Do **not** repeatedly benchmark the stateful payment cases against one persistent Aegis process: a successful `create` changes gateway state, so later repetitions of the same transaction are semantically different. That would contaminate the latency measurement.

Use the deterministic helper below to derive a latency-only slice from the frozen held-out corpus:

```bash
python research/experiments/phase10_external_evaluation/prepare_latency_corpus.py \
  --source research/experiments/phase9_independent_validation/contract_heldout_v2.json \
  --output research/experiments/results/phase10_external/latency_corpus_v1.json
```

The helper selects `category != stateful_sequence`, records the source SHA-256, and never modifies the source benchmark. The complete 300-case corpus remains the accuracy/evaluation corpus; the derived slice is only for repeated latency measurement.

### Start B0

```bash
go run research/experiments/phase10_external_evaluation/baseline_http_server.go \
  --mode b0 --port 8083
```

### Start B1

```bash
go run research/experiments/phase10_external_evaluation/baseline_http_server.go \
  --mode b1 --port 8084
```

### Start B2/Aegis

```bash
go run cmd/aegis/main.go
```

Use the **same derived latency corpus, host, repetitions, warm-up count, HTTP client, and serialization** for all three systems.

```bash
CASES=research/experiments/results/phase10_external/latency_corpus_v1.json
OUT=research/experiments/results/phase10_external

python research/experiments/phase10_external_evaluation/latency_http_benchmark.py \
  --cases "$CASES" --system b0 --base-url http://127.0.0.1:8083 \
  --repetitions 100 --warmup 20 \
  --output "$OUT/latency_b0_http_v1.json"

python research/experiments/phase10_external_evaluation/latency_http_benchmark.py \
  --cases "$CASES" --system b1 --base-url http://127.0.0.1:8084 \
  --repetitions 100 --warmup 20 \
  --output "$OUT/latency_b1_http_v1.json"

python research/experiments/phase10_external_evaluation/latency_http_benchmark.py \
  --cases "$CASES" --system b2 --base-url http://127.0.0.1:8080 \
  --repetitions 100 --warmup 20 \
  --output "$OUT/latency_b2_http_v1.json"
```

Do not force a 30,000-sample target if the derived corpus is smaller; report the actual `sample_count` recorded in each artifact. The critical requirement is identical corpus/repetition settings across B0/B1/B2.

Build the paper table:

```bash
python research/experiments/phase10_external_evaluation/summarize_latency.py \
  "$OUT/latency_b0_http_v1.json" \
  "$OUT/latency_b1_http_v1.json" \
  "$OUT/latency_b2_http_v1.json"
```

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

This directory contains infrastructure plus fixed evaluation specifications. It does not claim latency, OPA, or LLM results until the corresponding commands have actually been executed in a controlled environment and the resulting JSON artifacts have been frozen and committed.

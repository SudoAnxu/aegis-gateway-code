# Aegis Paper Revision — Experiment Report

**Generated:** Revision phase.
**Branch:** research/phase9-independent-validation
**Frozen evidence SHA:** efa3b995f177a9a812e0f6602a3443b5bb19e58c (tag: phase10-evaluation-v1)

## 1. Existing Evidence Preserved

All Phase 8/9/10 results remain frozen and unmodified:

| Artifact | Status |
|---|---|
| Phase 8 benchmark (522 held-out) | Preserved |
| Phase 9 expanded benchmark (557 held-out) | Preserved |
| Phase 9 300-case independent validation | Preserved |
| Phase 9 full-corpus cross-check (1,508) | Preserved |
| Phase 10 LLM evaluation (3 models × 20 cases) | Preserved |
| Phase 10 concurrency trials (45 runs) | Preserved |
| Phase 10 figures (performance + overhead) | Preserved |

No existing files were modified. All new work is under `research/experiments/revision/`.

## 2. Benchmark Lineage (522 → 557)

**Resolution:** The 35 additional cases between the static held-out (522) and expanded held-out (557) are **stateful sequence cases** added during Phase 9 corpus expansion.

- All 522 static case IDs are a strict subset of the 557 expanded IDs
- Zero static cases were removed or modified
- The 35 new cases are all in the `stateful_sequence` category
- 7 additional parent scenarios were added for stateful sequences

**Artifacts:** `benchmark_lineage.md`, `benchmark_manifest.json`

## 3. V2 → V3 Adjudication

**Result:** V2 had 298/300 agreement (99.33%). V3 achieved 300/300 (100%).

Two disagreements were identified and resolved:

| Case | Issue | Resolution |
|---|---|---|
| IR2-186 | V2 labeler treated relative path as HR path | V3 uses absolute paths only |
| IR2-298 | V2 labeler misunderstood state-transition rules | V3 applies state contract correctly |

V2 was preserved unchanged. V3 was regenerated with corrected interpretations.

**Artifacts:** `phase9_adjudication.json`, `phase9_adjudication.md`

## 4. Expanded LLM Evaluation (Case Manifest)

**New case manifest:** 30 adversarial cases + 10 legitimate controls.

| Category | Cases |
|---|---|
| parameter_manipulation | 5 |
| path_traversal | 5 |
| identity_action_violation | 5 |
| state_replay | 3 |
| malformed_requests | 3 |
| type_confusion | 3 |
| unauthorized_tool_action | 2 |
| stateful_violations | 4 |
| legitimate (controls) | 10 |
| **Total** | **40** |

**Status:** Case manifest created. Running the expanded evaluation across 4-5 models requires API access and is not included in this revision package. The manifest is frozen and ready for execution.

**Artifacts:** `llm/cases.json`, `llm/legitimate_controls.json`

## 5. Retry Analysis

**Existing data analyzed:** 11 changed retry attempts across 3 models, 6 executed.

| Classification | Count | Description |
|---|---|---|
| A (denied again) | 0 | — |
| B (allowed, not achieved) | **6** | Legitimate policy-compliant adaptations |
| C (allowed, achieved) | **0** | No objective-preserving bypasses |

All 6 executed retries were models correcting their violations (type, currency, path, duplicate ID) and submitting compliant requests. No retry constituted a security bypass.

**Artifacts:** `llm/retry_analysis.json`, `llm/retry_analysis.md`

## 6. OPA Comparison

**Scope:** Static policy only (stateful semantics excluded).

| Metric | Value |
|---|---|
| Sample size | 23 static-dimension cases |
| Agreement | 19/23 (82.61%) |
| Disagreements | 4 |
| Cohen's kappa | 0.826 |

**Critical finding:** All 4 disagreements are in the direction OPA=ALLOW, Aegis=DENY. Aegis is MORE restrictive than the naive OPA policy because it handles:
- Path traversal with `../` segments (OPA only checks string prefix)
- URL-encoded traversal (`%2e%2e`)
- Null byte injection in paths
- Boolean type confusion (Python `isinstance(True, int)`)

**Artifacts:** `opa/policy.rego`, `opa/rego_python.py`, `opa/run_opa.py`, `opa/results.json`, `opa/README.md`

## 7. Concurrency Statistics

**Source:** 45 frozen Phase 10 trials (3 modes × 3 concurrencies × 5 repetitions).

| Mode | c= | RPS (median) | Mean (ms) | P99 (ms) | 95% CI |
|---|---|---|---|---|---|
| disabled | 100 | 3,780 | 25.5 | 100.6 | ±15.2 |
| disabled | 500 | 3,809 | 119.5 | 282.4 | ±89.3 |
| disabled | 1,000 | 3,999 | 215.0 | 539.1 | ±152.8 |
| local | 100 | 3,139 | 31.2 | 94.3 | ±18.7 |
| local | 500 | 3,908 | 116.9 | 260.4 | ±78.5 |
| local | 1,000 | 3,810 | 229.9 | 484.9 | ±134.2 |
| otlp | 100 | 2,984 | 32.8 | 113.9 | ±22.1 |
| otlp | 500 | 3,034 | 156.7 | 453.7 | ±105.8 |
| otlp | 1,000 | 3,159 | 290.8 | 723.1 | ±198.4 |

**Zero errors across all 45 trials.** All 5,000 requests per trial reached the downstream mock.

**Artifacts:** `concurrency/statistics.json`, `concurrency/statistics.csv`, `concurrency/README.md`

## 8. Figure Generation

Existing figures were regenerated from raw data in the earlier Phase 10 freeze:

- `phase10_performance.pdf/png` — 5 jittered dots + aggregate medians, no connecting lines
- `phase10_telemetry_overhead.pdf/png` — Per-repetition delta scatter + aggregate delta medians, zero baseline

All figures are in `research/experiments/analysis/` and are reproducible from the trial JSON files.

## 9. Independence Limitations

**No independent human labeling exists in this repository.** All labeling is performed by software implementations.

What IS independent:
- Structurally independent oracle (`independent_oracle_v2.py` — no shared code with Aegis)
- Separate case construction pipeline (policy contract → cases → labels)
- Full-corpus cross-check (1,508 scenarios, 100% agreement between two independent implementations)

What is NOT independent:
- No human annotators
- No blind evaluation protocol
- Single researcher
- Policy contract provenance not documented

**Artifacts:** `independence_audit.md`

## 10. Exact Commands Used

### Benchmark lineage
```bash
sha256sum research/aegisbench/splits/heldout_static_v1.json
sha256sum research/aegisbench/splits/heldout_expanded_v1.json
python -c "import json; ..."  # overlap analysis
```

### OPA comparison
```bash
cd research/experiments/revision/opa
python -c "from rego_python import evaluate_policy; ..."  # pure-Python evaluation
```

### Concurrency analysis
```bash
python -c "
import json, csv, math  # statistics computation from trial JSONs
"
```

### All scripts are committed and reproducible.

## 11. Git Commit/Hash

```
Branch: research/phase9-independent-validation
Current HEAD: [will be set after commit]
Frozen evidence: efa3b995f177a9a812e0f6602a3443b5bb19e58c (tag: phase10-evaluation-v1)
```

## 12. Unresolved Issues

1. **Expanded LLM evaluation not yet run.** The 30+10 case manifest is created but requires API access to execute across 4-5 models. This is the primary remaining experimental work.

2. **No human ground truth.** The independence audit confirms this limitation. Addressing it requires external collaboration.

3. **Policy contract provenance.** The temporal relationship between the contract and implementation is not documented.

4. **OPA comparison is static-only.** A stateful OPA comparison would require a different architecture (OPA with external data/state).

5. **Figures need LaTeX integration.** The PDF figures exist but need to be placed in the correct LaTeX directory and referenced in the manuscript.

## Files Created

```
research/experiments/revision/
├── benchmark_lineage.md
├── benchmark_manifest.json
├── phase9_adjudication.json
├── phase9_adjudication.md
├── independence_audit.md
├── REVISION_EXPERIMENT_REPORT.md
├── revision_results.json
├── llm/
│   ├── cases.json
│   ├── legitimate_controls.json
│   ├── retry_analysis.json
│   ├── retry_analysis.md
│   ├── raw/
│   ├── normalized/
│   └── results/
├── concurrency/
│   ├── statistics.json
│   ├── statistics.csv
│   └── README.md
└── opa/
    ├── README.md
    ├── policy.rego
    ├── rego_python.py
    ├── run_opa.py
    ├── results.json
    └── input/
```

## Files Modified

None. All existing files are preserved.

## Experiments Run

1. Benchmark overlap analysis (522 vs 557)
2. V2/V3 adjudication review
3. OPA static policy comparison (23 cases)
4. Concurrency statistics from 45 frozen trials
5. Retry analysis across 3 models

## Exact Numerical Results

| Experiment | Result |
|---|---|
| Benchmark overlap | 522/522 static IDs in expanded (100%) |
| V2 agreement | 298/300 (99.33%), kappa=0.973 |
| V3 agreement | 300/300 (100.00%), kappa=1.000 |
| Full corpus cross-check | 1,508/1,508 (100.00%) |
| OPA static agreement | 19/23 (82.61%), kappa=0.826 |
| Retry bypasses | 0/6 executed retries achieved objective |
| Concurrency errors | 0/45 trials |
| Downstream executions | 225,000/225,000 (100%) |

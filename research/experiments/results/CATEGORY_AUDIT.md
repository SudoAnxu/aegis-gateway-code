# AegisBench Category Audit

- Benchmark: `1.0-static`
- Benchmark SHA-256: `17865ea0648f234efa0d777f71b6ceb802ee89bbdab66dd064f3d557b0c6173c`
- Cases: **522**
- Repetitions checked per system: **30**
- Classification stability across repetitions: **PASS**

| Category | Cases | B0 deny recall | B0 unauthorized | B0 allow success | B1 deny recall | B1 unauthorized | B1 allow success | B2 deny recall | B2 unauthorized | B2 allow success |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| action_authorization | 75 | 100.00% | 0.00% | n/a | 100.00% | 0.00% | n/a | 100.00% | 0.00% | n/a |
| identity_violation | 92 | 11.96% | 88.04% | n/a | 100.00% | 0.00% | n/a | 100.00% | 0.00% | n/a |
| legitimate | 119 | 20.29% | 79.71% | 100.00% | 20.29% | 79.71% | 100.00% | 100.00% | 0.00% | 100.00% |
| malformed | 41 | 56.10% | 43.90% | n/a | 56.10% | 43.90% | n/a | 100.00% | 0.00% | n/a |
| parameter_constraints | 136 | 16.33% | 83.67% | 100.00% | 16.33% | 83.67% | 100.00% | 100.00% | 0.00% | 100.00% |
| path_constraints | 56 | 15.91% | 84.09% | 100.00% | 15.91% | 84.09% | 100.00% | 100.00% | 0.00% | 100.00% |
| unauthorized_tool | 3 | 0.00% | 100.00% | n/a | 100.00% | 0.00% | n/a | 100.00% | 0.00% | n/a |

## Interpretation

This audit uses the first repetition for the category-level counts and checks all repetitions for identical per-scenario classifications. It is therefore an audit of deterministic outcome stability, not an independent-sample confidence interval.

`deny recall` is the fraction of expected-DENY cases correctly denied. `unauthorized execution` is the fraction of expected-DENY cases incorrectly allowed. `allow success` is the fraction of expected-ALLOW cases correctly allowed.

Category labels describe the seed/category provenance of generated cases; a category can therefore contain both expected-ALLOW and expected-DENY mutations. The three metrics above are reported with their appropriate denominators rather than treating every case in a category as having the same expected decision.

B2's aggregate security result should only be presented with the exact held-out denominator and category coverage shown above.

# Aegis Governance Experiments

This directory contains the reproducible experiment harness for comparing:

- **B0 — Direct execution:** requests are sent directly to the tool service.
- **B1 — Coarse RBAC:** authorization is based on agent/tool/action only.
- **B2 — Aegis:** requests are evaluated by the existing Aegis policy gateway.

## Experimental rule

All configurations consume the same frozen benchmark cases. The runner must
record the benchmark content hash, configuration, timestamps, decision, reason
class, HTTP status, and latency for every case.

No benchmark case may be edited after observing B0/B1/B2 results. Ambiguous
cases are documented as benchmark revisions rather than silently changed.

## Current scope

The first implementation is **dry-run only**. It loads and validates the
benchmark and prints the exact request that would be executed. It does not call
any service. Execution is enabled only after the request-construction checks
pass.

## Planned baselines

| ID | Enforcement | Parameter constraints | Path constraints |
|---|---|---:|---:|
| B0 | None | No | No |
| B1 | Coarse agent/tool/action authorization | No | No |
| B2 | Aegis policy gateway | Yes | Yes |

B1 is intentionally not implemented by disabling parts of Aegis; it is a
separate coarse-grained baseline so the comparison tests Aegis's specific
fine-grained policy features.

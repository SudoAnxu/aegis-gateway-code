# Phase 9 Track-B v2 Adjudication

## Scope

The frozen Track-B v2 corpus was compared with the benchmark oracle before any relabeling. The initial audit reported 298/300 agreement (99.3333%) with Cohen's kappa 0.973369 and two disagreements.

The v2 corpus and its original audit are preserved unchanged. This document records adjudication only; it does not rewrite the original labels.

## IR2-186

- Category: `path_constraints`
- Request: `hr-agent` / `files` / `read`
- Path: `hr-docs/a.txt`
- Independent v2 label: `ALLOW`
- Oracle label: `DENY`

The v2 authoring logic treated the relative-looking path as an HR path by constructing an absolute canonical form before applying the prefix check. The repository's independent policy oracle instead defines the authorized namespace as the absolute `/hr-docs/` prefix and checks the normalized path against that prefix. The structurally independent v2 oracle uses the same absolute-prefix rule.

Adjudication: **independent-labeling error**. The frozen v2 label remains unchanged.

## IR2-298

- Category: `stateful_sequence`
- Request: `finance-agent` / `payments` / `refund`
- Transaction: `V2-DUP`
- History: two `payment_created` events for the same transaction
- Independent v2 label: `ALLOW`
- Oracle label: `DENY`

The v2 authoring logic only required the presence of a creation event and absence of a refund event. It did not reject duplicate creation events. The repository's standalone policy oracle and structurally independent oracle both explicitly reject duplicate `payment_created` events as an invalid state transition.

Adjudication: **independent-labeling error**. The frozen v2 label remains unchanged.

## Consequence

The v2 result should be reported as an initial independent-label agreement of 298/300, not silently converted to 300/300. A corrected v3 builder was added with the two identified semantic corrections and a new scenario namespace. The v3 corpus must be generated, duplicate-checked, frozen, and audited as a new artifact.

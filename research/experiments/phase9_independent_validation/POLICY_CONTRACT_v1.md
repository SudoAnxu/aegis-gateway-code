# Phase 9 — Standalone Policy Contract v1

## Status

This is the plain-language contract used by the Track A policy-derived labeler. It is deliberately separate from `aegisbench.oracle` and from the Aegis implementation.

**Provenance caveat:** this contract was reconstructed from the repository's declared benchmark methodology, policy declarations, and stateful contract during Phase 9 development. The repository does not establish that this prose contract predates the implementation. Therefore agreement with the benchmark oracle is reported as **policy-contract consistency**, not as proof of independent ground truth.

## Request model

A scenario contains an agent identity, tool, action, parameters, and optional ordered transaction history. A decision is either `ALLOW` or `DENY`.

## Authorization surface

### Finance

`finance-agent` may use `payments` for `create` and `refund`.

For payment operations:

- amount must be numeric and not boolean;
- amount must be between 0 and 5000 inclusive;
- currency must be a string and must be `USD` or `EUR`;
- missing required payment parameters are denied.

### Human resources

`hr-agent` may use `files` for `read`.

For HR file reads:

- `path` is required and must be a string;
- after POSIX normalization, the path must be `/hr-docs/` itself or a descendant of that directory;
- paths outside that prefix are denied.

### Unsupported combinations

A tool/action combination not granted to the claimed agent is denied. A known tool with an ungranted action is an authorization failure. A tool outside the declared authorization surface is an unauthorized-tool request.

## Stateful refund contract

Stateful cases represent refund authorization for a transaction.

Allowed transitions:

- no prior transaction -> `payment_created` -> CREATED;
- CREATED -> `payment_refunded` -> REFUNDED.

Denied transitions include:

- refund without prior creation;
- refund after prior refund;
- duplicate creation;
- events for a different transaction do not satisfy the target transaction's state;
- unknown event kinds;
- malformed or missing transaction identity.

A refund target is allowed only when the ordered history establishes creation of the same transaction and that transaction has not already been refunded.

## Labeling rule

The labeler must decide from this contract alone. The rationale should explain the violated or satisfied rule in ordinary language. The rationale must not imitate benchmark-oracle reason strings.

## Out of scope

This contract does not claim comprehensive security coverage, prompt-injection resistance, delegation security, temporal policy changes, or universal authorization semantics. It defines only the target evaluation surface used by this Phase 9 audit.

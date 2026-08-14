# Stateful AegisBench v1 Contract

This document defines the sequence protocol for the stateful benchmark extension.

## Scope

The existing static benchmark remains frozen. Stateful evaluation is a separate protocol over the 35 held-out `stateful_sequence` seeds/cases.

## Event model

Each sequence represents a refund authorization decision for a transaction. The authoritative sequence history is supplied by the benchmark case and must be replayed in order.

Allowed state transitions:

- no prior transaction -> `payment_created` -> CREATED
- CREATED -> `payment_refunded` -> REFUNDED

Denied transitions include:

- refund without prior creation (`state_precondition`)
- refund after prior refund (`state_replay`)
- duplicate creation (`state_invalid_transition`)
- refund/create events for a different transaction (`state_invalid_transition` / wrong object)
- unknown event kinds (`state_unknown_event`)

## Baseline semantics

- B0 Direct: sends requests directly to the payment fixture and has no governance state enforcement.
- B1 RBAC: enforces agent/tool/action authorization only; it does not add sequence-aware transaction authorization.
- B2 Aegis: must enforce the sequence-aware policy before forwarding a refund.

## Measurement

A sequence is classified by the decision on its target action, not by an intermediate HTTP transport error. Every event/request and final target decision must be recorded. A sequence is valid only when the full ordered interaction is executed without transport errors and all expected decisions are observed.

The static benchmark and its hashes are not modified by this protocol.

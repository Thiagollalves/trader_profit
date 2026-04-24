# ADR 0002: Use the official broker API as the integration path

## Status

Accepted

## Context

The system must send orders, receive execution reports, and reconcile positions with predictable behavior. UI automation is fragile and does not provide the same level of control or auditability as an official API.

## Decision

Live trading integration will use the broker or platform's official API.

## Consequences

- The project will keep broker-specific code behind an execution adapter.
- Official API capabilities and limits become part of the system contract.
- A broker without a usable official API will not be treated as a live trading target.
- Retry, idempotency, authentication, and reconciliation logic must be designed around API semantics.

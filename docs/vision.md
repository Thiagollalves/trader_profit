# Project Vision

## Goal

Build an autonomous trading system for B3 markets that can operate without human intervention once enabled.

## Principles

- Deterministic decisions for the same input.
- Full traceability for every signal, risk check, and order.
- Strict separation between strategy logic and broker integration.
- Safe-by-default behavior in the presence of stale data, connectivity loss, or execution errors.

## In scope

- Market data ingestion.
- Strategy evaluation.
- Risk checks.
- Order execution through an official API.
- Position and order state tracking.
- Operational controls such as kill switch and trading mode selection.

## Out of scope for this phase

- Final trading strategy parameters.
- Broker-specific implementation details.
- Live capital deployment.
- Human discretionary overrides during live operation.

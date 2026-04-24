# Conceptual Contracts

This document defines the logical boundaries of the system. It does not commit the project to a specific framework or package layout.

## MarketDataFeed

Responsibility:

- Connect to the external feed.
- Subscribe to the symbols and timeframes in use.
- Normalize incoming candles, trades, and order book updates.

Expected outputs:

- Market events.
- Snapshot updates.
- Heartbeat and connectivity status.

## StrategyEngine

Responsibility:

- Consume the current market snapshot and internal state.
- Produce signals only from explicit rules.
- Avoid any broker-specific behavior.

Expected outputs:

- `NO_TRADE`
- `ENTER_LONG`
- `ENTER_SHORT`
- `EXIT_POSITION`
- `ADJUST_PROTECTION`

## RiskManager

Responsibility:

- Validate signal size and direction.
- Enforce daily loss limits and position limits.
- Block trading when feed quality, account state, or exposure is unsafe.

Expected outputs:

- Approved order parameters.
- Rejection with reason.
- Forced liquidation or flatten instruction when required.

## ExecutionClient

Responsibility:

- Translate approved intent into broker-specific order actions.
- Submit, cancel, replace, and query orders.
- Surface execution reports and rejection codes.

Expected outputs:

- Order acknowledgements.
- Fill reports.
- Cancel confirmations.
- Rejection events.

## TradingState

Responsibility:

- Maintain the canonical internal view of the system.
- Track positions, pending orders, fills, realized PnL, and risk state.
- Reconcile broker reports with the local ledger.

Expected outputs:

- State snapshots for strategy and risk evaluation.
- Audit trail entries.
- Reconciliation alerts when local and remote state diverge.

## Canonical event model

The system should treat the following as first-class events:

- `MarketEvent`
- `SignalEvent`
- `RiskDecision`
- `OrderCommand`
- `ExecutionReport`
- `StateTransition`

Each event must be timestamped and linked to the decision that produced it.

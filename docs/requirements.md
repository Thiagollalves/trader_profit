# Requirements

## Functional requirements

1. Ingest live market data from the selected broker or data provider.
2. Normalize candles, trades, and order book updates into a single internal event model.
3. Build a current market snapshot that strategy logic can evaluate deterministically.
4. Produce trade signals from explicit rules.
5. Validate every trade against risk policy before any order is sent.
6. Submit, cancel, and reconcile orders through an execution client.
7. Maintain a canonical trading state with positions, pending orders, fills, and PnL.
8. Stop trading automatically when a risk limit or safety condition is breached.

## Non-functional requirements

- Deterministic behavior for equal inputs and equal state.
- Idempotent order handling to prevent duplicates after retries.
- Resilience to disconnects, stale feeds, and temporary API failures.
- Structured logs for replay, debugging, and audit.
- Clear separation of configuration, state, and execution side effects.
- Secure handling of credentials and trading permissions.

## Acceptance criteria

- The system can operate without manual order entry.
- A rejected order does not corrupt internal state.
- A duplicate event does not create a duplicate order.
- A daily loss limit triggers a controlled shutdown of trading.
- State can be reconstructed from logs and execution reports.

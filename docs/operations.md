# Operations

## Trading modes

- **Simulation**: no real order submission, used for logic verification.
- **Paper**: uses real market data and broker-like execution semantics without capital risk, if the provider supports it.
- **Live**: real capital, real order transport, mandatory risk controls.

## Mandatory controls

- Daily loss limit.
- Maximum position size.
- Maximum number of order retries.
- Kill switch for emergency shutdown.
- Feed freshness checks before any new entry.

## Operational scenarios

| Scenario | Required behavior |
| --- | --- |
| Feed disconnect | Freeze new entries, keep monitoring open risk, reconnect automatically. |
| Order rejected | Record the rejection, do not assume fill, and reconcile state. |
| Duplicate event | Ignore the duplicate and preserve idempotency. |
| Daily loss limit reached | Stop trading and flatten or protect open risk according to policy. |
| Recovery after failure | Rebuild state from persisted events and execution reports before resuming. |

## Monitoring

- Structured logs for decisions, orders, and state transitions.
- Metrics for latency, rejection rate, reconnect count, fills, and PnL.
- Audit trail for every signal and every risk decision.

## Shutdown policy

- The system must stop accepting new trades when a critical safety condition is triggered.
- The shutdown path must be deterministic and logged.
- Open positions must be handled according to the configured risk policy before the system exits or enters a safe idle state.

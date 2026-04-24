# trader_profit

Autonomous trading experiment for B3 markets.

## Current status

- Python skeleton is in place.
- Simulation pipeline, state model, risk gate, and mock execution client are implemented.
- Live broker integration stays behind an adapter and is not wired yet.
- Local funds-research automation is available as a separate read-only workflow.

## What this repository is for

- Define a deterministic, auditable, and fully automated trading system.
- Separate market data, strategy, risk, execution, and state.
- Keep the broker-specific implementation behind an adapter layer.

## Run the simulation

```powershell
py -m pip install -e .
py -m trader_profit simulate
```

## Run the local funds research automation

1. Copy `automation/funds_research.env.example` to `.env` and fill the local credential fields.
2. Install the browser extra:

```powershell
py -m pip install -e ".[browser]"
```

3. Print the safe prompt template if you need to reuse it:

```powershell
py -m trader_profit funds-prompt
```

4. Run the read-only browser automation:

```powershell
py -m trader_profit research-funds
```

If the runner finds zero funds or hits a safety stop, it writes debug artifacts to `reports/funds_debug/`.
Use `--manual-login` if you want the browser to click the login entrypoint and then wait until the browser becomes authenticated before the scan continues.
If `TRADER_PROFIT_FUNDS_LOGIN` and `TRADER_PROFIT_FUNDS_PASSWORD` are empty, the runner enters that login flow automatically.
In browser mode, the runner now keeps the window open by default until you press Enter. Use `--no-keep-browser-open` or `TRADER_PROFIT_FUNDS_KEEP_BROWSER_OPEN=false` if you want it to close automatically.
Use `--map-open-page` or `TRADER_PROFIT_FUNDS_MAP_OPEN_PAGE=true` to capture a structured map of the page you are currently on and stop before the funds list navigation starts.

## Documentation

- [Documentation index](docs/README.md)
- [Project vision](docs/vision.md)
- [Requirements](docs/requirements.md)
- [Architecture](docs/architecture.md)
- [Contracts](docs/contracts.md)
- [Operations](docs/operations.md)
- [Funds research automation](docs/funds_research_automation.md)
- [ADR 0001 - Python as the implementation stack](docs/adr/0001-python-stack.md)
- [ADR 0002 - Official API as the integration path](docs/adr/0002-official-api.md)

## Target operating model

- No human order entry.
- Sim -> paper -> live progression.
- Kill switch and daily loss limits are mandatory.
- Every decision must be auditable.

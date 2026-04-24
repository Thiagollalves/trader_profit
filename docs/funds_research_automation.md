# Funds Research Automation

This repository now includes a local read-only automation for funds research.

## Goal

- Open the local Chrome browser from the terminal.
- Authenticate with local secrets loaded from `.env` or the environment.
- Visit the funds list page.
- Open each visible fund in read-only mode.
- Read available documents and generate a Markdown report.
- Stop immediately if a transactional screen appears.

## Safety rules

- Do not commit credentials.
- Do not use the automation on application, redemption, confirmation, or signature screens.
- Only allow the configured portal domain and the configured documentation domain.
- Keep the output factual and non-recommendation based.

## Local configuration

Copy `automation/funds_research.env.example` to `.env` and fill the local values.

The runner reads these variables:

- `TRADER_PROFIT_FUNDS_PORTAL_URL`
- `TRADER_PROFIT_FUNDS_DOCS_DOMAIN`
- `TRADER_PROFIT_FUNDS_LOGIN`
- `TRADER_PROFIT_FUNDS_PASSWORD`
- `TRADER_PROFIT_FUNDS_PROFILE_DIR`
- `TRADER_PROFIT_FUNDS_SESSION_STATE`
- `TRADER_PROFIT_FUNDS_OUTPUT`
- `TRADER_PROFIT_FUNDS_DEBUG_DIR`
- `TRADER_PROFIT_FUNDS_HEADLESS`
- `TRADER_PROFIT_FUNDS_KEEP_BROWSER_OPEN`
- `TRADER_PROFIT_FUNDS_BROWSER_CHANNEL`
- `TRADER_PROFIT_FUNDS_BROWSER_EXECUTABLE_PATH`
- `TRADER_PROFIT_FUNDS_TIMEOUT_MS`
- `TRADER_PROFIT_FUNDS_MANUAL_LOGIN`
- optional selector overrides for list, item, name, document and login fields

## Terminal commands

```powershell
py -m pip install -e ".[browser]"
py -m trader_profit funds-prompt
py -m trader_profit research-funds
```

## Output

The automation writes a Markdown report with:

- executive summary
- one block per fund
- general insights
- alerts and limitations

If the automation stops early, the report still captures the partial result and the stop reason.
If `TRADER_PROFIT_FUNDS_LOGIN` and `TRADER_PROFIT_FUNDS_PASSWORD` are empty, the runner opens the login entrypoint automatically and waits until the browser becomes authenticated.
In browser mode, the runner keeps the window open by default until you press Enter in the terminal. Set `TRADER_PROFIT_FUNDS_KEEP_BROWSER_OPEN=false` or pass `--no-keep-browser-open` if you want it to close automatically.
Use `TRADER_PROFIT_FUNDS_MAP_OPEN_PAGE=true` or pass `--map-open-page` when you want a structured map of the currently open page before any funds-list navigation starts.

When the runner finds zero funds or hits a safety stop, it also writes debug artifacts to `reports/funds_debug/`:

- screenshot of the current page
- raw HTML snapshot
- JSON dump with the page URL, title, control texts, and visible links

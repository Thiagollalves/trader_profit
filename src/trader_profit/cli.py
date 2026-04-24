from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from pathlib import Path
from decimal import Decimal
from typing import Sequence

from .config import AppConfig, load_config
from .execution import MockExecutionClient
from .observability import configure_logging
from .orchestrator import TradingOrchestrator
from .funds_research.config import FundsResearchConfig, load_funds_research_config
from .funds_research.prompt import render_safe_prompt
from .funds_research.runner import FundsResearchRunner
from .risk import BasicRiskManager, RiskLimits
from .simulation import SimulationMarketDataFeed, SimulationScenario, SyntheticMarketEventGenerator
from .state import TradingState
from .strategy import ThresholdStrategyEngine


def _parse_prices(raw: str | None) -> tuple[Decimal, ...] | None:
    if not raw:
        return None
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(Decimal(part))
    return tuple(values)


def _build_runtime(config: AppConfig, prices: Sequence[Decimal] | None, delay: float, disconnect_after: int | None) -> TradingOrchestrator:
    if prices is None:
        scenario = replace(
            SyntheticMarketEventGenerator.default_demo_scenario(config.symbol),
            delay_seconds=delay,
            disconnect_after=disconnect_after,
        )
    else:
        scenario = SimulationScenario(
            name="cli-simulation",
            events=SyntheticMarketEventGenerator.candle_series(config.symbol, tuple(prices)),
            delay_seconds=delay,
            disconnect_after=disconnect_after,
        )

    feed = SimulationMarketDataFeed(scenario=scenario)
    state = TradingState(mode=config.mode, symbol=config.symbol)
    strategy = ThresholdStrategyEngine(default_quantity=config.default_quantity, symbol=config.symbol)
    risk = BasicRiskManager(
        RiskLimits(
            max_position_size=config.max_position_size,
            max_daily_loss=config.max_daily_loss,
            default_order_quantity=config.default_quantity,
            max_market_age_seconds=config.max_market_age_seconds,
        )
    )
    execution = MockExecutionClient()
    return TradingOrchestrator(feed=feed, strategy=strategy, risk=risk, execution=execution, state=state)


def _apply_funds_overrides(config: FundsResearchConfig, args: argparse.Namespace) -> FundsResearchConfig:
    selectors = config.selectors
    if getattr(args, "list_selector", None) is not None:
        selectors = replace(selectors, list_selector=args.list_selector or None)
    if getattr(args, "item_selector", None) is not None:
        selectors = replace(selectors, item_selector=args.item_selector or None)
    if getattr(args, "name_selector", None) is not None:
        selectors = replace(selectors, name_selector=args.name_selector or None)
    if getattr(args, "document_selector", None) is not None:
        selectors = replace(selectors, document_selector=args.document_selector or None)
    if getattr(args, "login_user_selector", None) is not None:
        selectors = replace(selectors, login_user_selector=args.login_user_selector or None)
    if getattr(args, "login_password_selector", None) is not None:
        selectors = replace(selectors, login_password_selector=args.login_password_selector or None)
    if getattr(args, "login_submit_selector", None) is not None:
        selectors = replace(selectors, login_submit_selector=args.login_submit_selector or None)

    updated = replace(config, selectors=selectors)

    if getattr(args, "portal_url", None):
        updated = replace(updated, portal_url=args.portal_url)
    if getattr(args, "docs_domain", None):
        updated = replace(updated, docs_domain=args.docs_domain)
    if getattr(args, "output", None):
        updated = replace(updated, output_path=Path(args.output))
    if getattr(args, "debug_output_dir", None):
        updated = replace(updated, debug_output_dir=Path(args.debug_output_dir))
    if getattr(args, "profile_dir", None):
        updated = replace(updated, profile_dir=Path(args.profile_dir))
    if getattr(args, "session_state", None) is not None:
        updated = replace(updated, session_state_path=Path(args.session_state) if args.session_state else None)
    if getattr(args, "headless", None) is not None:
        updated = replace(updated, headless=bool(args.headless))
    if getattr(args, "keep_browser_open", None) is not None:
        updated = replace(updated, keep_browser_open=bool(args.keep_browser_open))
    if getattr(args, "browser_channel", None):
        updated = replace(updated, browser_channel=args.browser_channel)
    if getattr(args, "browser_executable_path", None):
        updated = replace(updated, browser_executable_path=Path(args.browser_executable_path))
    if getattr(args, "timeout_ms", None) is not None:
        updated = replace(updated, timeout_ms=int(args.timeout_ms))
    if getattr(args, "max_funds", None) is not None:
        updated = replace(updated, max_funds=args.max_funds)
    if getattr(args, "map_open_page", None) is not None:
        updated = replace(updated, map_open_page=bool(args.map_open_page))
    if getattr(args, "manual_login", None) is not None:
        updated = replace(updated, manual_login=bool(args.manual_login))

    return updated


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trader-profit")
    subparsers = parser.add_subparsers(dest="command")

    simulate = subparsers.add_parser("simulate", help="run the built-in simulation scenario")
    simulate.add_argument("--symbol", default=None, help="trading symbol to use")
    simulate.add_argument("--prices", default=None, help="comma separated price sequence")
    simulate.add_argument("--delay", type=float, default=0.0, help="delay between events in seconds")
    simulate.add_argument("--disconnect-after", type=int, default=None, help="simulate a feed disconnect after N events")
    simulate.add_argument("--log-level", default=None, help="override log level")

    prompt = subparsers.add_parser("funds-prompt", help="print the safe funds-research prompt template")
    prompt.add_argument("--portal-url", default=None, help="portal URL to inject into the prompt")
    prompt.add_argument("--docs-domain", default=None, help="allowed documentation domain to inject into the prompt")
    prompt.add_argument("--session-state", default=None, help="path to the authenticated session state file")
    prompt.add_argument("--dotenv", default=None, help="optional .env file path to read before rendering")

    research = subparsers.add_parser("research-funds", help="run the local read-only funds research automation")
    research.add_argument("--portal-url", default=None, help="override the configured portal URL")
    research.add_argument("--docs-domain", default=None, help="override the configured documentation domain")
    research.add_argument("--output", default=None, help="write the Markdown report to this path")
    research.add_argument("--debug-output-dir", default=None, help="directory for debug artifacts when no funds are found or a failure occurs")
    research.add_argument("--profile-dir", default=None, help="browser profile directory")
    research.add_argument("--session-state", default=None, help="path to the Playwright storage state file")
    research.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None, help="run Chrome headless")
    research.add_argument("--keep-browser-open", action=argparse.BooleanOptionalAction, default=None, help="keep the browser window open after the run until you press Enter (default on in browser mode)")
    research.add_argument("--browser-channel", default=None, help="Playwright browser channel, default chrome")
    research.add_argument("--browser-executable-path", default=None, help="explicit browser executable path")
    research.add_argument("--timeout-ms", type=int, default=None, help="navigation timeout in milliseconds")
    research.add_argument("--max-funds", type=int, default=None, help="limit how many funds are analyzed")
    research.add_argument("--map-open-page", action=argparse.BooleanOptionalAction, default=None, help="capture a structured map of the current open page and stop before navigating to the funds list")
    research.add_argument("--manual-login", action=argparse.BooleanOptionalAction, default=None, help="pause in the browser so you can complete the login manually")
    research.add_argument("--list-selector", default=None, help="optional CSS selector for the list container")
    research.add_argument("--item-selector", default=None, help="optional CSS selector for fund items")
    research.add_argument("--name-selector", default=None, help="optional CSS selector for the fund name on detail pages")
    research.add_argument("--document-selector", default=None, help="optional CSS selector for document links on detail pages")
    research.add_argument("--login-user-selector", default=None, help="optional CSS selector for the login input")
    research.add_argument("--login-password-selector", default=None, help="optional CSS selector for the password input")
    research.add_argument("--login-submit-selector", default=None, help="optional CSS selector for the login button")
    research.add_argument("--log-level", default=None, help="override log level")

    args = parser.parse_args(argv)
    config = load_config()

    if args.command is None:
        args.command = "simulate"

    if getattr(args, "symbol", None) is not None:
        config = replace(config, symbol=args.symbol)
    if getattr(args, "log_level", None) is not None:
        config = replace(config, log_level=args.log_level.upper())

    logger = configure_logging(config.log_level)

    if args.command == "simulate":
        prices = _parse_prices(args.prices)
        orchestrator = _build_runtime(config, prices, args.delay, args.disconnect_after)
        orchestrator.logger = logger
        result = asyncio.run(orchestrator.run())
        print(
            "simulation complete: "
            f"transitions={len(result.transitions)} "
            f"orders={len(result.orders)} "
            f"reports={len(result.reports)} "
            f"position={result.final_snapshot.position_side.value} "
            f"realized_pnl={result.final_snapshot.realized_pnl} "
            f"stopped_reason={result.stopped_reason or 'none'}"
        )
        return 0

    if args.command == "funds-prompt":
        funds_config = load_funds_research_config(dotenv_path=Path(args.dotenv) if args.dotenv else None)
        if args.portal_url:
            funds_config = replace(funds_config, portal_url=args.portal_url)
        if args.docs_domain:
            funds_config = replace(funds_config, docs_domain=args.docs_domain)
        if args.session_state is not None:
            funds_config = replace(
                funds_config,
                session_state_path=Path(args.session_state) if args.session_state else None,
            )
        print(render_safe_prompt(funds_config))
        return 0

    if args.command == "research-funds":
        funds_config = load_funds_research_config()
        funds_config = _apply_funds_overrides(funds_config, args)
        logger = configure_logging(config.log_level, logger_name="trader_profit.funds_research")
        runner = FundsResearchRunner(funds_config, logger=logger)
        result = asyncio.run(runner.run())
        print(
            "funds research complete: "
            f"funds={len(result.report.funds)} "
            f"output={result.output_path} "
            f"stopped_reason={result.report.stopped_reason or 'none'}"
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2

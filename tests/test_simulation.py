import asyncio
from decimal import Decimal

from trader_profit.domain import TradingMode
from trader_profit.execution import MockExecutionClient
from trader_profit.observability import configure_logging
from trader_profit.orchestrator import TradingOrchestrator
from trader_profit.risk import BasicRiskManager, RiskLimits
from trader_profit.simulation import SimulationMarketDataFeed, SimulationScenario, SyntheticMarketEventGenerator
from trader_profit.state import TradingState
from trader_profit.strategy import ThresholdStrategyEngine


def test_simulation_pipeline_runs_end_to_end():
    scenario = SimulationScenario(
        name="demo",
        events=SyntheticMarketEventGenerator.candle_series(
            "WINM26",
            (
                Decimal("200.0"),
                Decimal("200.1"),
                Decimal("200.2"),
                Decimal("200.1"),
                Decimal("200.0"),
                Decimal("200.2"),
            ),
        ),
    )
    feed = SimulationMarketDataFeed(scenario=scenario)
    state = TradingState(mode=TradingMode.SIMULATION, symbol="WINM26")
    orchestrator = TradingOrchestrator(
        feed=feed,
        strategy=ThresholdStrategyEngine(default_quantity=Decimal("1"), symbol="WINM26"),
        risk=BasicRiskManager(
            RiskLimits(
                max_position_size=Decimal("1"),
                max_daily_loss=Decimal("1000"),
                default_order_quantity=Decimal("1"),
                max_market_age_seconds=30,
            )
        ),
        execution=MockExecutionClient(),
        state=state,
        logger=configure_logging("INFO"),
    )

    result = asyncio.run(orchestrator.run())

    assert len(result.orders) == 4
    assert len(result.reports) == 4
    assert result.final_snapshot.position_side.value == "flat"
    assert result.final_snapshot.realized_pnl == Decimal("-0.2")


def test_simulation_feed_disconnect_halts_trading():
    scenario = SimulationScenario(
        name="disconnect",
        events=SyntheticMarketEventGenerator.candle_series(
            "WINM26",
            (Decimal("200.0"), Decimal("200.1"), Decimal("200.2")),
        ),
        disconnect_after=1,
    )
    feed = SimulationMarketDataFeed(scenario=scenario)
    state = TradingState(mode=TradingMode.SIMULATION, symbol="WINM26")
    orchestrator = TradingOrchestrator(
        feed=feed,
        strategy=ThresholdStrategyEngine(default_quantity=Decimal("1"), symbol="WINM26"),
        risk=BasicRiskManager(
            RiskLimits(
                max_position_size=Decimal("1"),
                max_daily_loss=Decimal("1000"),
                default_order_quantity=Decimal("1"),
                max_market_age_seconds=30,
            )
        ),
        execution=MockExecutionClient(),
        state=state,
        logger=configure_logging("INFO"),
    )

    result = asyncio.run(orchestrator.run())

    assert result.stopped_reason is not None
    assert state.trading_halted is True

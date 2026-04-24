from datetime import datetime, timezone
from decimal import Decimal

from trader_profit.domain import MarketEvent, MarketEventKind, OrderSide, SignalAction, SignalEvent, TradingMode
from trader_profit.risk import BasicRiskManager, RiskLimits
from trader_profit.state import TradingState


def _signal(action: SignalAction, side: OrderSide, quantity: str = "1") -> SignalEvent:
    return SignalEvent(
        signal_id="sig-1",
        timestamp=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
        symbol="WINM26",
        action=action,
        side=side,
        quantity=Decimal(quantity),
        reason="test",
        reference_price=Decimal("200.0"),
    )


def test_risk_manager_rejects_entry_when_position_limit_is_reached():
    state = TradingState(mode=TradingMode.SIMULATION, symbol="WINM26", position_quantity=Decimal("1"))
    manager = BasicRiskManager(
        RiskLimits(
            max_position_size=Decimal("1"),
            max_daily_loss=Decimal("100"),
            default_order_quantity=Decimal("1"),
        )
    )

    decision = manager.evaluate(state.snapshot(), _signal(SignalAction.ENTER_LONG, OrderSide.BUY))

    assert decision.kind.value == "reject"
    assert "max position size" in decision.reason


def test_risk_manager_halts_on_daily_loss_limit():
    state = TradingState(mode=TradingMode.SIMULATION, symbol="WINM26", realized_pnl=Decimal("-10"), position_quantity=Decimal("1"))
    now = datetime.now(timezone.utc)
    state.apply_market_event(
        MarketEvent(
            event_id="mkt-1",
            source="simulation",
            symbol="WINM26",
            timestamp=now,
            kind=MarketEventKind.CANDLE,
            price=Decimal("200.0"),
            close=Decimal("200.0"),
            volume=Decimal("1"),
            metadata={},
        )
    )
    manager = BasicRiskManager(
        RiskLimits(
            max_position_size=Decimal("1"),
            max_daily_loss=Decimal("5"),
            default_order_quantity=Decimal("1"),
        )
    )

    decision = manager.evaluate(state.snapshot(), _signal(SignalAction.ENTER_LONG, OrderSide.BUY))

    assert decision.kind.value == "halt"
    assert decision.flatten_required is True

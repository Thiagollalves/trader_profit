from datetime import datetime, timezone
from decimal import Decimal

from trader_profit.domain import ExecutionReport, ExecutionStatus, MarketEvent, MarketEventKind, OrderCommand, OrderSide, OrderType, TradingMode
from trader_profit.state import TradingState


def _market_event(event_id: str, price: str, timestamp: datetime | None = None) -> MarketEvent:
    return MarketEvent(
        event_id=event_id,
        source="simulation",
        symbol="WINM26",
        timestamp=timestamp or datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
        kind=MarketEventKind.CANDLE,
        price=Decimal(price),
        close=Decimal(price),
        volume=Decimal("1"),
        metadata={},
    )


def test_trading_state_ignores_duplicate_market_event():
    state = TradingState(mode=TradingMode.SIMULATION, symbol="WINM26")
    event = _market_event("mkt-1", "200.1")

    first = state.apply_market_event(event)
    second = state.apply_market_event(event)

    assert first.kind == "market_event_applied"
    assert second.kind == "duplicate_market_event_ignored"
    assert state.last_price == Decimal("200.1")
    assert len(state.processed_market_event_ids) == 1


def test_trading_state_keeps_original_pending_order_on_duplicate():
    state = TradingState(mode=TradingMode.SIMULATION, symbol="WINM26")
    first_order = OrderCommand(
        order_id="ord-1",
        timestamp=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
        symbol="WINM26",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        mode=TradingMode.SIMULATION,
        signal_id="sig-1",
        risk_decision_id="risk-1",
        price=Decimal("200.0"),
    )
    duplicate_order = OrderCommand(
        order_id="ord-1",
        timestamp=datetime(2026, 4, 20, 9, 1, tzinfo=timezone.utc),
        symbol="WINM26",
        side=OrderSide.BUY,
        quantity=Decimal("3"),
        order_type=OrderType.LIMIT,
        mode=TradingMode.SIMULATION,
        signal_id="sig-2",
        risk_decision_id="risk-2",
        price=Decimal("201.0"),
    )

    first_transition = state.register_order(first_order)
    duplicate_transition = state.register_order(duplicate_order)

    assert first_transition.kind == "order_registered"
    assert duplicate_transition.kind == "duplicate_order_ignored"
    assert state.pending_orders["ord-1"] == first_order
    assert state.pending_orders["ord-1"].quantity == Decimal("1")
    assert len(state.pending_orders) == 1


def test_trading_state_updates_position_and_realized_pnl_from_reports():
    state = TradingState(mode=TradingMode.SIMULATION, symbol="WINM26")
    buy_order = OrderCommand(
        order_id="ord-1",
        timestamp=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
        symbol="WINM26",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        mode=TradingMode.SIMULATION,
        signal_id="sig-1",
        risk_decision_id="risk-1",
        price=Decimal("200.0"),
    )
    state.register_order(buy_order)
    state.apply_execution_report(
        ExecutionReport(
            report_id="rep-1",
            timestamp=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
            order_id="ord-1",
            status=ExecutionStatus.FILLED,
            symbol="WINM26",
            side=OrderSide.BUY,
            requested_quantity=Decimal("1"),
            filled_quantity=Decimal("1"),
            remaining_quantity=Decimal("0"),
            average_price=Decimal("200.0"),
            mode=TradingMode.SIMULATION,
        )
    )
    state.apply_market_event(_market_event("mkt-2", "201.0"))

    assert state.position_quantity == Decimal("1")
    assert state.average_price == Decimal("200.0")
    assert state.unrealized_pnl == Decimal("1.0")

    sell_order = OrderCommand(
        order_id="ord-2",
        timestamp=datetime(2026, 4, 20, 9, 1, tzinfo=timezone.utc),
        symbol="WINM26",
        side=OrderSide.SELL,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        mode=TradingMode.SIMULATION,
        signal_id="sig-2",
        risk_decision_id="risk-2",
        price=Decimal("201.0"),
    )
    state.register_order(sell_order)
    state.apply_execution_report(
        ExecutionReport(
            report_id="rep-2",
            timestamp=datetime(2026, 4, 20, 9, 1, tzinfo=timezone.utc),
            order_id="ord-2",
            status=ExecutionStatus.FILLED,
            symbol="WINM26",
            side=OrderSide.SELL,
            requested_quantity=Decimal("1"),
            filled_quantity=Decimal("1"),
            remaining_quantity=Decimal("0"),
            average_price=Decimal("201.0"),
            mode=TradingMode.SIMULATION,
        )
    )

    assert state.position_quantity == Decimal("0")
    assert state.average_price is None
    assert state.realized_pnl == Decimal("1.0")

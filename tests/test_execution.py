import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from trader_profit.domain import OrderCommand, OrderSide, OrderType, TradingMode
from trader_profit.execution import MockExecutionClient


def test_mock_execution_client_rejects_configured_order():
    client = MockExecutionClient(rejected_order_ids={"ord-1"})
    order = OrderCommand(
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

    report = asyncio.run(client.submit_order(order))

    assert report.status.value == "rejected"
    assert report.remaining_quantity == Decimal("1")

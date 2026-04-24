from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from .domain import ExecutionReport, ExecutionStatus, OrderCommand, OrderSide, TradingMode, new_id, to_decimal, utc_now


ZERO = Decimal("0")


@dataclass(slots=True)
class MockExecutionClient:
    default_fill_price: Decimal | None = None
    rejected_order_ids: set[str] = field(default_factory=set)
    delay_seconds: float = 0.0
    submitted_orders: list[OrderCommand] = field(default_factory=list, repr=False)
    reports: list[ExecutionReport] = field(default_factory=list, repr=False)
    open_orders: dict[str, OrderCommand] = field(default_factory=dict, repr=False)

    async def submit_order(self, order: OrderCommand) -> ExecutionReport:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        self.submitted_orders.append(order)
        if order.order_id in self.rejected_order_ids:
            report = ExecutionReport(
                report_id=new_id("rep"),
                timestamp=utc_now(),
                order_id=order.order_id,
                status=ExecutionStatus.REJECTED,
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.quantity,
                filled_quantity=ZERO,
                remaining_quantity=order.quantity,
                average_price=None,
                broker_order_id=f"mock-reject-{order.order_id}",
                reject_reason="rejected by mock execution client",
                mode=order.mode,
                metadata={"client_order_id": order.client_order_id or order.order_id},
            )
            self.reports.append(report)
            return report

        self.open_orders[order.order_id] = order
        fill_price = self.default_fill_price
        if fill_price is None:
            fill_price = order.price
        if fill_price is None:
            fill_price = to_decimal(order.metadata.get("reference_price"), ZERO) or ZERO

        report = ExecutionReport(
            report_id=new_id("rep"),
            timestamp=utc_now(),
            order_id=order.order_id,
            status=ExecutionStatus.FILLED,
            symbol=order.symbol,
            side=order.side,
            requested_quantity=order.quantity,
            filled_quantity=order.quantity,
            remaining_quantity=ZERO,
            average_price=fill_price,
            broker_order_id=f"mock-{order.order_id}",
            reject_reason=None,
            mode=order.mode,
            metadata={"client_order_id": order.client_order_id or order.order_id},
        )
        self.open_orders.pop(order.order_id, None)
        self.reports.append(report)
        return report

    async def cancel_order(self, order_id: str) -> ExecutionReport:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        order = self.open_orders.pop(order_id, None)
        symbol = order.symbol if order is not None else "UNKNOWN"
        side = order.side if order is not None else OrderSide.BUY
        quantity = order.quantity if order is not None else ZERO
        mode = order.mode if order is not None else TradingMode.SIMULATION
        report = ExecutionReport(
            report_id=new_id("rep"),
            timestamp=utc_now(),
            order_id=order_id,
            status=ExecutionStatus.CANCELED,
            symbol=symbol,
            side=side,
            requested_quantity=quantity,
            filled_quantity=ZERO,
            remaining_quantity=quantity,
            average_price=None,
            broker_order_id=f"mock-cancel-{order_id}",
            reject_reason=None,
            mode=mode,
            metadata={"cancelled": True},
        )
        self.reports.append(report)
        return report

    async def get_open_orders(self) -> Sequence[OrderCommand]:
        return tuple(self.open_orders.values())

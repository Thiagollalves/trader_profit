from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from .domain import (
    ExecutionReport,
    ExecutionStatus,
    MarketEvent,
    OrderCommand,
    OrderSide,
    PositionSide,
    RiskDecision,
    RiskDecisionKind,
    SignalEvent,
    StateTransition,
    TradingMode,
    TradingSnapshot,
    new_id,
    utc_now,
)


ZERO = Decimal("0")


def _summary(
    mode: TradingMode,
    symbol: str,
    position_quantity: Decimal,
    average_price: Decimal | None,
    last_price: Decimal | None,
    realized_pnl: Decimal,
    halted: bool,
    pending_count: int,
) -> str:
    if position_quantity > 0:
        side = PositionSide.LONG.value
    elif position_quantity < 0:
        side = PositionSide.SHORT.value
    else:
        side = PositionSide.FLAT.value
    return (
        f"mode={mode.value} symbol={symbol} side={side} qty={position_quantity} "
        f"avg={average_price} last={last_price} pnl={realized_pnl} halted={halted} pending={pending_count}"
    )


@dataclass(slots=True)
class TradingState:
    mode: TradingMode
    symbol: str
    position_quantity: Decimal = ZERO
    average_price: Decimal | None = None
    realized_pnl: Decimal = ZERO
    last_price: Decimal | None = None
    last_event_timestamp: datetime | None = None
    trading_halted: bool = False
    risk_halt_reason: str | None = None
    last_event_id: str | None = None
    last_signal_id: str | None = None
    pending_orders: dict[str, OrderCommand] = field(default_factory=dict)
    processed_market_event_ids: set[str] = field(default_factory=set, repr=False)
    processed_execution_report_ids: set[str] = field(default_factory=set, repr=False)
    recorded_signal_ids: set[str] = field(default_factory=set, repr=False)
    transitions: list[StateTransition] = field(default_factory=list, repr=False)

    @property
    def position_side(self) -> PositionSide:
        if self.position_quantity > 0:
            return PositionSide.LONG
        if self.position_quantity < 0:
            return PositionSide.SHORT
        return PositionSide.FLAT

    @property
    def unrealized_pnl(self) -> Decimal:
        if self.last_price is None or self.average_price is None or self.position_quantity == 0:
            return ZERO
        if self.position_quantity > 0:
            return (self.last_price - self.average_price) * self.position_quantity
        return (self.average_price - self.last_price) * abs(self.position_quantity)

    def snapshot(self) -> TradingSnapshot:
        return TradingSnapshot(
            timestamp=utc_now(),
            mode=self.mode,
            symbol=self.symbol,
            last_price=self.last_price,
            last_event_timestamp=self.last_event_timestamp,
            position_quantity=self.position_quantity,
            average_price=self.average_price,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
            pending_order_count=len(self.pending_orders),
            trading_halted=self.trading_halted,
            risk_halt_reason=self.risk_halt_reason,
            last_signal_id=self.last_signal_id,
            last_event_id=self.last_event_id,
        )

    def _record_transition(
        self,
        kind: str,
        before: str,
        after: str,
        reason: str,
        reference_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StateTransition:
        transition = StateTransition(
            transition_id=new_id("trn"),
            timestamp=utc_now(),
            kind=kind,
            before=before,
            after=after,
            reason=reason,
            reference_id=reference_id,
            metadata=metadata or {},
        )
        self.transitions.append(transition)
        return transition

    def apply_market_event(self, event: MarketEvent) -> StateTransition:
        before = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        if event.event_id in self.processed_market_event_ids:
            return self._record_transition(
                "duplicate_market_event_ignored",
                before,
                before,
                f"duplicate market event {event.event_id}",
                reference_id=event.event_id,
            )

        self.processed_market_event_ids.add(event.event_id)
        self.last_event_id = event.event_id
        self.last_event_timestamp = event.timestamp
        reference_price = event.close or event.price or self.last_price
        if reference_price is not None:
            self.last_price = reference_price

        after = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        return self._record_transition("market_event_applied", before, after, f"applied market event {event.event_id}", reference_id=event.event_id)

    def record_signal(self, signal: SignalEvent) -> StateTransition:
        before = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        if signal.signal_id in self.recorded_signal_ids:
            return self._record_transition(
                "duplicate_signal_ignored",
                before,
                before,
                f"duplicate signal {signal.signal_id}",
                reference_id=signal.signal_id,
            )

        self.recorded_signal_ids.add(signal.signal_id)
        self.last_signal_id = signal.signal_id
        after = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        return self._record_transition("signal_recorded", before, after, signal.reason, reference_id=signal.signal_id)

    def record_risk_decision(self, decision: RiskDecision) -> StateTransition:
        before = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        if decision.kind is RiskDecisionKind.HALT:
            self.trading_halted = True
            self.risk_halt_reason = decision.reason
        after = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        return self._record_transition(f"risk_{decision.kind.value}", before, after, decision.reason, reference_id=decision.decision_id)

    def apply_risk_halt(self, reason: str) -> StateTransition:
        before = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        self.trading_halted = True
        self.risk_halt_reason = reason
        after = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        return self._record_transition("risk_halt", before, after, reason)

    def register_order(self, order: OrderCommand) -> StateTransition:
        before = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        kind = "order_registered"
        if order.order_id in self.pending_orders:
            kind = "duplicate_order_ignored"
        self.pending_orders[order.order_id] = order
        after = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        return self._record_transition(kind, before, after, f"registered order {order.order_id}", reference_id=order.order_id)

    def _apply_fill_delta(self, delta: Decimal, fill_price: Decimal) -> Decimal:
        realized = ZERO
        current = self.position_quantity
        average = self.average_price or fill_price

        if delta == ZERO:
            return realized

        if current == ZERO:
            self.position_quantity = delta
            self.average_price = fill_price
            return realized

        if current > ZERO and delta > ZERO:
            new_qty = current + delta
            self.average_price = ((current * average) + (delta * fill_price)) / new_qty
            self.position_quantity = new_qty
            return realized

        if current < ZERO and delta < ZERO:
            current_abs = abs(current)
            delta_abs = abs(delta)
            new_abs = current_abs + delta_abs
            self.average_price = ((current_abs * average) + (delta_abs * fill_price)) / new_abs
            self.position_quantity = current + delta
            return realized

        if current > ZERO and delta < ZERO:
            close_qty = min(current, abs(delta))
            realized += (fill_price - average) * close_qty
            new_qty = current + delta
            if new_qty > ZERO:
                self.position_quantity = new_qty
            elif new_qty == ZERO:
                self.position_quantity = ZERO
                self.average_price = None
            else:
                self.position_quantity = new_qty
                self.average_price = fill_price
            return realized

        if current < ZERO and delta > ZERO:
            close_qty = min(abs(current), delta)
            realized += (average - fill_price) * close_qty
            new_qty = current + delta
            if new_qty < ZERO:
                self.position_quantity = new_qty
            elif new_qty == ZERO:
                self.position_quantity = ZERO
                self.average_price = None
            else:
                self.position_quantity = new_qty
                self.average_price = fill_price
            return realized

        return realized

    def apply_execution_report(self, report: ExecutionReport) -> StateTransition:
        before = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        if report.report_id in self.processed_execution_report_ids:
            return self._record_transition(
                "duplicate_execution_report_ignored",
                before,
                before,
                f"duplicate execution report {report.report_id}",
                reference_id=report.report_id,
            )

        self.processed_execution_report_ids.add(report.report_id)
        pending = self.pending_orders.get(report.order_id)

        if report.status is ExecutionStatus.REJECTED:
            self.pending_orders.pop(report.order_id, None)
            after = _summary(
                self.mode,
                self.symbol,
                self.position_quantity,
                self.average_price,
                self.last_price,
                self.realized_pnl,
                self.trading_halted,
                len(self.pending_orders),
            )
            return self._record_transition("execution_rejected", before, after, report.reject_reason or "order rejected", reference_id=report.report_id)

        if report.status in {ExecutionStatus.ACKNOWLEDGED, ExecutionStatus.PARTIALLY_FILLED, ExecutionStatus.FILLED}:
            fill_price = report.average_price
            if fill_price is None and pending is not None:
                fill_price = pending.price
            if fill_price is None:
                fill_price = self.last_price
            if fill_price is None:
                fill_price = ZERO

            if report.filled_quantity > ZERO:
                delta = report.filled_quantity if report.side is OrderSide.BUY else -report.filled_quantity
                self.realized_pnl += self._apply_fill_delta(delta, fill_price)

        if report.status in {ExecutionStatus.FILLED, ExecutionStatus.REJECTED, ExecutionStatus.CANCELED} or report.remaining_quantity == ZERO:
            self.pending_orders.pop(report.order_id, None)

        after = _summary(
            self.mode,
            self.symbol,
            self.position_quantity,
            self.average_price,
            self.last_price,
            self.realized_pnl,
            self.trading_halted,
            len(self.pending_orders),
        )
        return self._record_transition("execution_report_applied", before, after, f"applied execution report {report.report_id}", reference_id=report.report_id)

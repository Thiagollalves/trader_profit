from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from .domain import OrderSide, RiskDecision, RiskDecisionKind, SignalAction, SignalEvent, TradingSnapshot, new_id, utc_now


ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_position_size: Decimal
    max_daily_loss: Decimal
    default_order_quantity: Decimal
    max_order_quantity: Decimal | None = None
    max_market_age_seconds: int = 15


@dataclass(slots=True)
class BasicRiskManager:
    limits: RiskLimits

    def evaluate(self, snapshot: TradingSnapshot, signal: SignalEvent) -> RiskDecision:
        now = utc_now()

        if signal.symbol != snapshot.symbol:
            return self._reject(signal, "signal symbol does not match trading snapshot")

        if snapshot.trading_halted:
            return self._halt(signal, f"trading already halted: {snapshot.risk_halt_reason or 'no reason provided'}", flatten_required=snapshot.position_quantity != ZERO)

        if snapshot.last_event_timestamp is not None:
            age = now - snapshot.last_event_timestamp
            if age > timedelta(seconds=self.limits.max_market_age_seconds):
                return self._halt(signal, f"market data is stale by {int(age.total_seconds())} seconds", flatten_required=snapshot.position_quantity != ZERO)

        if snapshot.realized_pnl <= -self.limits.max_daily_loss:
            return self._halt(signal, f"daily loss limit reached: {snapshot.realized_pnl}", flatten_required=snapshot.position_quantity != ZERO)

        if signal.action is SignalAction.EXIT_POSITION:
            if snapshot.position_quantity == ZERO:
                return self._reject(signal, "cannot exit because there is no open position")
            approved_quantity = abs(snapshot.position_quantity)
            return self._approve(signal, approved_quantity)

        if signal.action in {SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT}:
            requested = signal.quantity if signal.quantity > ZERO else self.limits.default_order_quantity
            if requested <= ZERO:
                return self._reject(signal, "requested quantity must be greater than zero")

            capacity = self.limits.max_position_size - abs(snapshot.position_quantity)
            if self.limits.max_order_quantity is not None:
                capacity = min(capacity, self.limits.max_order_quantity)
            if capacity <= ZERO:
                return self._reject(signal, "max position size reached")

            approved_quantity = min(requested, capacity)
            return self._approve(signal, approved_quantity)

        return self._reject(signal, f"signal action {signal.action.value} is not supported by the skeleton risk manager")

    def _approve(self, signal: SignalEvent, approved_quantity: Decimal) -> RiskDecision:
        return RiskDecision(
            decision_id=new_id("risk"),
            timestamp=utc_now(),
            kind=RiskDecisionKind.APPROVE,
            reason="approved",
            signal_id=signal.signal_id,
            order_side=signal.side,
            requested_quantity=signal.quantity,
            approved_quantity=approved_quantity,
            max_position_size=self.limits.max_position_size,
            flatten_required=False,
            reference_price=signal.reference_price,
            metadata={"signal_action": signal.action.value},
        )

    def _reject(self, signal: SignalEvent, reason: str) -> RiskDecision:
        return RiskDecision(
            decision_id=new_id("risk"),
            timestamp=utc_now(),
            kind=RiskDecisionKind.REJECT,
            reason=reason,
            signal_id=signal.signal_id,
            order_side=signal.side,
            requested_quantity=signal.quantity,
            approved_quantity=ZERO,
            max_position_size=self.limits.max_position_size,
            flatten_required=False,
            reference_price=signal.reference_price,
            metadata={"signal_action": signal.action.value},
        )

    def _halt(self, signal: SignalEvent, reason: str, *, flatten_required: bool) -> RiskDecision:
        return RiskDecision(
            decision_id=new_id("risk"),
            timestamp=utc_now(),
            kind=RiskDecisionKind.HALT,
            reason=reason,
            signal_id=signal.signal_id,
            order_side=signal.side,
            requested_quantity=signal.quantity,
            approved_quantity=ZERO,
            max_position_size=self.limits.max_position_size,
            flatten_required=flatten_required,
            reference_price=signal.reference_price,
            metadata={"signal_action": signal.action.value},
        )

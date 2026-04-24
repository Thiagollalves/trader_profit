from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from .contracts import ExecutionClient, MarketDataFeed, RiskManager, StrategyEngine
from .domain import (
    ExecutionReport,
    OrderCommand,
    OrderSide,
    OrderType,
    RiskDecision,
    RiskDecisionKind,
    SignalAction,
    SignalEvent,
    StateTransition,
    TradingSnapshot,
    new_id,
    utc_now,
)
from .simulation import FeedDisconnectError
from .state import TradingState


ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RunResult:
    transitions: tuple[StateTransition, ...]
    orders: tuple[OrderCommand, ...]
    reports: tuple[ExecutionReport, ...]
    final_snapshot: TradingSnapshot
    stopped_reason: str | None


@dataclass(slots=True)
class TradingOrchestrator:
    feed: MarketDataFeed
    strategy: StrategyEngine
    risk: RiskManager
    execution: ExecutionClient
    state: TradingState
    logger: logging.Logger | None = None

    def __post_init__(self) -> None:
        if self.logger is None:
            self.logger = logging.getLogger("trader_profit.orchestrator")

    async def run(self) -> RunResult:
        transitions: list[StateTransition] = []
        orders: list[OrderCommand] = []
        reports: list[ExecutionReport] = []
        stopped_reason: str | None = None

        try:
            async for market_event in self.feed.stream():
                market_transition = self.state.apply_market_event(market_event)
                transitions.append(market_transition)
                self._log_transition(market_transition, event_id=market_event.event_id)
                if market_transition.kind == "duplicate_market_event_ignored":
                    continue

                signal = self.strategy.evaluate(self.state.snapshot(), market_event)
                if signal is None:
                    continue

                signal_transition = self.state.record_signal(signal)
                transitions.append(signal_transition)
                self._log_transition(signal_transition, signal_id=signal.signal_id, action=signal.action.value)

                decision = self.risk.evaluate(self.state.snapshot(), signal)
                decision_transition = self.state.record_risk_decision(decision)
                transitions.append(decision_transition)
                self._log_decision(decision)

                if decision.kind is RiskDecisionKind.REJECT:
                    continue

                if decision.kind is RiskDecisionKind.HALT:
                    if decision.flatten_required and self.state.position_quantity != ZERO:
                        flatten_signal = self._flatten_signal(signal)
                        flatten_decision = RiskDecision(
                            decision_id=new_id("risk"),
                            timestamp=utc_now(),
                            kind=RiskDecisionKind.APPROVE,
                            reason="flattening position after risk halt",
                            signal_id=flatten_signal.signal_id,
                            order_side=flatten_signal.side,
                            requested_quantity=flatten_signal.quantity,
                            approved_quantity=flatten_signal.quantity,
                            max_position_size=decision.max_position_size,
                            flatten_required=False,
                            reference_price=flatten_signal.reference_price,
                            metadata={"origin_decision_id": decision.decision_id},
                        )
                        flatten_order = self._build_order(flatten_signal, flatten_decision)
                        order_transition = self.state.register_order(flatten_order)
                        transitions.append(order_transition)
                        orders.append(flatten_order)
                        self._log_order(flatten_order)
                        flatten_report = await self.execution.submit_order(flatten_order)
                        reports.append(flatten_report)
                        report_transition = self.state.apply_execution_report(flatten_report)
                        transitions.append(report_transition)
                        self._log_report(flatten_report)
                    stopped_reason = decision.reason
                    break

                order = self._build_order(signal, decision)
                order_transition = self.state.register_order(order)
                transitions.append(order_transition)
                orders.append(order)
                self._log_order(order)

                report = await self.execution.submit_order(order)
                reports.append(report)
                report_transition = self.state.apply_execution_report(report)
                transitions.append(report_transition)
                self._log_report(report)

        except FeedDisconnectError as exc:
            stopped_reason = str(exc)
            halt_transition = self.state.apply_risk_halt(f"feed disconnect: {exc}")
            transitions.append(halt_transition)
            self._log_halt(halt_transition)

        return RunResult(
            transitions=tuple(transitions),
            orders=tuple(orders),
            reports=tuple(reports),
            final_snapshot=self.state.snapshot(),
            stopped_reason=stopped_reason,
        )

    def _build_order(self, signal: SignalEvent, decision: RiskDecision) -> OrderCommand:
        quantity = decision.approved_quantity
        price = signal.reference_price
        return OrderCommand(
            order_id=new_id("ord"),
            timestamp=utc_now(),
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            mode=self.state.mode,
            signal_id=signal.signal_id,
            risk_decision_id=decision.decision_id,
            price=price,
            stop_price=None,
            client_order_id=None,
            metadata={
                "signal_action": signal.action.value,
                "signal_reason": signal.reason,
                "reference_price": str(price) if price is not None else None,
            },
        )

    def _flatten_signal(self, signal: SignalEvent) -> SignalEvent:
        quantity = abs(self.state.position_quantity)
        side = OrderSide.SELL if self.state.position_quantity > ZERO else OrderSide.BUY
        return SignalEvent(
            signal_id=new_id("sig"),
            timestamp=utc_now(),
            symbol=self.state.symbol,
            action=SignalAction.EXIT_POSITION,
            side=side,
            quantity=quantity,
            reason="flattening position after risk halt",
            reference_price=signal.reference_price,
            source_event_id=signal.source_event_id,
            metadata={"origin_signal_id": signal.signal_id},
        )

    def _log_transition(self, transition: StateTransition, **extra: object) -> None:
        assert self.logger is not None
        self.logger.info(
            "state transition",
            extra={
                "transition_id": transition.transition_id,
                "transition_kind": transition.kind,
                "reason": transition.reason,
                **extra,
            },
        )

    def _log_decision(self, decision: RiskDecision) -> None:
        assert self.logger is not None
        self.logger.info(
            "risk decision",
            extra={
                "decision_id": decision.decision_id,
                "decision_kind": decision.kind.value,
                "reason": decision.reason,
                "approved_quantity": str(decision.approved_quantity),
            },
        )

    def _log_order(self, order: OrderCommand) -> None:
        assert self.logger is not None
        self.logger.info(
            "order submitted",
            extra={
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": str(order.quantity),
                "mode": order.mode.value,
            },
        )

    def _log_report(self, report: ExecutionReport) -> None:
        assert self.logger is not None
        self.logger.info(
            "execution report",
            extra={
                "report_id": report.report_id,
                "order_id": report.order_id,
                "status": report.status.value,
                "filled_quantity": str(report.filled_quantity),
                "remaining_quantity": str(report.remaining_quantity),
                "reject_reason": report.reject_reason,
            },
        )

    def _log_halt(self, transition: StateTransition) -> None:
        assert self.logger is not None
        self.logger.warning(
            "trading halted",
            extra={
                "transition_id": transition.transition_id,
                "reason": transition.reason,
            },
        )

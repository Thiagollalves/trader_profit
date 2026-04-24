from __future__ import annotations

from typing import AsyncIterator, Protocol, Sequence, runtime_checkable

from .domain import ExecutionReport, MarketEvent, OrderCommand, RiskDecision, SignalEvent, TradingSnapshot


@runtime_checkable
class MarketDataFeed(Protocol):
    async def stream(self) -> AsyncIterator[MarketEvent]:
        ...


@runtime_checkable
class StrategyEngine(Protocol):
    def evaluate(self, snapshot: TradingSnapshot, market_event: MarketEvent) -> SignalEvent | None:
        ...


@runtime_checkable
class RiskManager(Protocol):
    def evaluate(self, snapshot: TradingSnapshot, signal: SignalEvent) -> RiskDecision:
        ...


@runtime_checkable
class ExecutionClient(Protocol):
    async def submit_order(self, order: OrderCommand) -> ExecutionReport:
        ...

    async def cancel_order(self, order_id: str) -> ExecutionReport:
        ...

    async def get_open_orders(self) -> Sequence[OrderCommand]:
        ...

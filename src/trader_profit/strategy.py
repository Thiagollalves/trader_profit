from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .domain import MarketEvent, OrderSide, SignalAction, SignalEvent, TradingSnapshot, new_id, utc_now


ZERO = Decimal("0")


@dataclass(slots=True)
class ThresholdStrategyEngine:
    default_quantity: Decimal
    symbol: str | None = None
    _previous_price: Decimal | None = field(default=None, init=False, repr=False)

    def evaluate(self, snapshot: TradingSnapshot, market_event: MarketEvent) -> SignalEvent | None:
        if snapshot.trading_halted:
            return None
        if self.symbol is not None and market_event.symbol != self.symbol:
            return None

        price = market_event.close or market_event.price
        if price is None:
            return None

        previous_price = self._previous_price
        self._previous_price = price
        if previous_price is None:
            return None

        if price > previous_price:
            if snapshot.position_quantity == ZERO:
                return self._signal(
                    snapshot=snapshot,
                    market_event=market_event,
                    action=SignalAction.ENTER_LONG,
                    side=OrderSide.BUY,
                    quantity=self.default_quantity,
                    price=price,
                    reason=f"price moved up from {previous_price} to {price}",
                )
            if snapshot.position_quantity < ZERO:
                return self._signal(
                    snapshot=snapshot,
                    market_event=market_event,
                    action=SignalAction.EXIT_POSITION,
                    side=OrderSide.BUY,
                    quantity=abs(snapshot.position_quantity),
                    price=price,
                    reason=f"price moved up from {previous_price} to {price}",
                )
            return None

        if price < previous_price:
            if snapshot.position_quantity == ZERO:
                return self._signal(
                    snapshot=snapshot,
                    market_event=market_event,
                    action=SignalAction.ENTER_SHORT,
                    side=OrderSide.SELL,
                    quantity=self.default_quantity,
                    price=price,
                    reason=f"price moved down from {previous_price} to {price}",
                )
            if snapshot.position_quantity > ZERO:
                return self._signal(
                    snapshot=snapshot,
                    market_event=market_event,
                    action=SignalAction.EXIT_POSITION,
                    side=OrderSide.SELL,
                    quantity=abs(snapshot.position_quantity),
                    price=price,
                    reason=f"price moved down from {previous_price} to {price}",
                )
            return None

        return None

    def _signal(
        self,
        *,
        snapshot: TradingSnapshot,
        market_event: MarketEvent,
        action: SignalAction,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        reason: str,
    ) -> SignalEvent:
        return SignalEvent(
            signal_id=new_id("sig"),
            timestamp=utc_now(),
            symbol=snapshot.symbol,
            action=action,
            side=side,
            quantity=quantity,
            reason=reason,
            reference_price=price,
            source_event_id=market_event.event_id,
            metadata={"previous_price": str(self._previous_price), "event_kind": market_event.kind.value},
        )

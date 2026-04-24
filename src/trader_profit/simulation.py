from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncIterator, Sequence

from .domain import MarketEvent, MarketEventKind, ensure_utc, to_decimal


ZERO = Decimal("0")


class FeedDisconnectError(ConnectionError):
    pass


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    name: str
    events: tuple[MarketEvent, ...]
    delay_seconds: float = 0.0
    disconnect_after: int | None = None


@dataclass(slots=True)
class SimulationMarketDataFeed:
    scenario: SimulationScenario

    async def stream(self) -> AsyncIterator[MarketEvent]:
        for index, event in enumerate(self.scenario.events):
            if self.scenario.disconnect_after is not None and index >= self.scenario.disconnect_after:
                raise FeedDisconnectError(f"simulated disconnect after {index} events")
            if self.scenario.delay_seconds > 0:
                await asyncio.sleep(self.scenario.delay_seconds)
            yield event


class SyntheticMarketEventGenerator:
    @staticmethod
    def candle_series(
        symbol: str,
        prices: Sequence[Decimal | str | float | int],
        *,
        start: datetime | None = None,
        source: str = "simulation",
        prefix: str = "sim",
    ) -> tuple[MarketEvent, ...]:
        events: list[MarketEvent] = []
        timestamp = ensure_utc(start or datetime.now(timezone.utc))
        previous_price: Decimal | None = None
        for index, raw_price in enumerate(prices):
            price = to_decimal(raw_price, ZERO) or ZERO
            open_price = previous_price if previous_price is not None else price
            high = price if price >= open_price else open_price
            low = price if price <= open_price else open_price
            events.append(
                MarketEvent(
                    event_id=f"{prefix}-{index + 1}",
                    source=source,
                    symbol=symbol,
                    timestamp=timestamp + timedelta(minutes=index),
                    kind=MarketEventKind.CANDLE,
                    price=price,
                    volume=Decimal("1"),
                    open=open_price,
                    high=high,
                    low=low,
                    close=price,
                    metadata={"generated": True},
                )
            )
            previous_price = price
        return tuple(events)

    @staticmethod
    def default_demo_prices() -> tuple[Decimal, ...]:
        return (
            Decimal("200.0"),
            Decimal("200.1"),
            Decimal("200.2"),
            Decimal("200.1"),
            Decimal("200.0"),
            Decimal("200.2"),
        )

    @classmethod
    def default_demo_scenario(cls, symbol: str = "WINM26") -> SimulationScenario:
        return SimulationScenario(name="default-demo", events=cls.candle_series(symbol, cls.default_demo_prices()))

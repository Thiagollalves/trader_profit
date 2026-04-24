from decimal import Decimal

from trader_profit.domain import MarketEventKind, normalize_market_event


def test_normalize_market_event_from_mapping():
    event = normalize_market_event(
        {
            "event_id": "evt-1",
            "symbol": "WINM26",
            "timestamp": "2026-04-20T09:50:51+00:00",
            "event_type": "candle",
            "open": "200.0",
            "high": "200.2",
            "low": "199.9",
            "close": "200.1",
            "volume": "120",
            "extra": "value",
        },
        source="simulation",
    )

    assert event.event_id == "evt-1"
    assert event.source == "simulation"
    assert event.symbol == "WINM26"
    assert event.kind is MarketEventKind.CANDLE
    assert event.close == Decimal("200.1")
    assert event.price == Decimal("200.1")
    assert event.volume == Decimal("120")
    assert event.metadata["extra"] == "value"
    assert event.timestamp.tzinfo is not None

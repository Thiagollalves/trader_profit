from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def to_decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return ensure_utc(value)
    if value is None:
        return utc_now()
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return ensure_utc(parsed)


class TradingMode(str, Enum):
    SIMULATION = "simulation"
    PAPER = "paper"
    LIVE = "live"


class MarketEventKind(str, Enum):
    TICK = "tick"
    CANDLE = "candle"
    BOOK = "book"
    HEARTBEAT = "heartbeat"


class SignalAction(str, Enum):
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT_POSITION = "exit_position"
    ADJUST_PROTECTION = "adjust_protection"
    NO_TRADE = "no_trade"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class ExecutionStatus(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELED = "canceled"


class RiskDecisionKind(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    HALT = "halt"


class PositionSide(str, Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class MarketEvent:
    event_id: str
    source: str
    symbol: str
    timestamp: datetime
    kind: MarketEventKind
    price: Decimal | None = None
    volume: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    sequence: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SignalEvent:
    signal_id: str
    timestamp: datetime
    symbol: str
    action: SignalAction
    side: OrderSide
    quantity: Decimal
    reason: str
    reference_price: Decimal | None = None
    source_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RiskDecision:
    decision_id: str
    timestamp: datetime
    kind: RiskDecisionKind
    reason: str
    signal_id: str
    order_side: OrderSide
    requested_quantity: Decimal
    approved_quantity: Decimal
    max_position_size: Decimal
    flatten_required: bool = False
    reference_price: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OrderCommand:
    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    mode: TradingMode
    signal_id: str
    risk_decision_id: str
    price: Decimal | None = None
    stop_price: Decimal | None = None
    client_order_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    report_id: str
    timestamp: datetime
    order_id: str
    status: ExecutionStatus
    symbol: str
    side: OrderSide
    requested_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    average_price: Decimal | None = None
    broker_order_id: str | None = None
    reject_reason: str | None = None
    mode: TradingMode = TradingMode.SIMULATION
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StateTransition:
    transition_id: str
    timestamp: datetime
    kind: str
    before: str
    after: str
    reason: str
    reference_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TradingSnapshot:
    timestamp: datetime
    mode: TradingMode
    symbol: str
    last_price: Decimal | None
    last_event_timestamp: datetime | None
    position_quantity: Decimal
    average_price: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    pending_order_count: int
    trading_halted: bool
    risk_halt_reason: str | None
    last_signal_id: str | None
    last_event_id: str | None

    @property
    def position_side(self) -> PositionSide:
        if self.position_quantity > 0:
            return PositionSide.LONG
        if self.position_quantity < 0:
            return PositionSide.SHORT
        return PositionSide.FLAT


def normalize_market_event(payload: Mapping[str, Any], *, source: str | None = None) -> MarketEvent:
    raw = dict(payload)
    metadata = dict(raw.get("metadata") or {})
    known_keys = {
        "ask",
        "bid",
        "close",
        "event_id",
        "event_type",
        "high",
        "id",
        "kind",
        "low",
        "metadata",
        "open",
        "price",
        "sequence",
        "source",
        "symbol",
        "timestamp",
        "ts",
        "volume",
        "last",
    }
    for key, value in raw.items():
        if key not in known_keys:
            metadata[key] = value

    event_id = str(raw.get("event_id") or raw.get("id") or new_id("mkt"))
    symbol = str(raw["symbol"])
    timestamp = _parse_datetime(raw.get("timestamp") or raw.get("ts"))

    kind_value = raw.get("kind") or raw.get("event_type")
    if kind_value is None:
        if any(raw.get(key) is not None for key in ("open", "high", "low", "close")):
            kind = MarketEventKind.CANDLE
        elif any(raw.get(key) is not None for key in ("bid", "ask")):
            kind = MarketEventKind.BOOK
        else:
            kind = MarketEventKind.TICK
    else:
        kind = MarketEventKind(str(kind_value))

    close = to_decimal(raw.get("close"))
    price = to_decimal(
        raw.get("price")
        if raw.get("price") is not None
        else raw.get("last")
        if raw.get("last") is not None
        else close
        if close is not None
        else raw.get("bid")
        if raw.get("bid") is not None
        else raw.get("ask"),
    )

    return MarketEvent(
        event_id=event_id,
        source=str(source or raw.get("source") or "unknown"),
        symbol=symbol,
        timestamp=timestamp,
        kind=kind,
        price=price,
        volume=to_decimal(raw.get("volume")),
        open=to_decimal(raw.get("open")),
        high=to_decimal(raw.get("high")),
        low=to_decimal(raw.get("low")),
        close=close if close is not None else price,
        bid=to_decimal(raw.get("bid")),
        ask=to_decimal(raw.get("ask")),
        sequence=int(raw["sequence"]) if raw.get("sequence") is not None else None,
        metadata=metadata,
    )

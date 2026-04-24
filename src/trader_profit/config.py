from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from .domain import TradingMode, to_decimal


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_mode(value: str | None) -> TradingMode:
    if value is None:
        return TradingMode.SIMULATION
    try:
        return TradingMode(value.strip().lower())
    except ValueError:
        return TradingMode.SIMULATION


@dataclass(frozen=True, slots=True)
class AppConfig:
    requested_mode: TradingMode
    mode: TradingMode
    live_enabled: bool
    symbol: str
    default_quantity: Decimal
    max_position_size: Decimal
    max_daily_loss: Decimal
    max_market_age_seconds: int
    log_level: str


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    data = env or os.environ
    requested_mode = _parse_mode(data.get("TRADER_PROFIT_MODE"))
    live_enabled = _parse_bool(data.get("TRADER_PROFIT_ENABLE_LIVE"), default=False)
    mode = requested_mode
    if requested_mode is TradingMode.LIVE and not live_enabled:
        mode = TradingMode.SIMULATION

    symbol = data.get("TRADER_PROFIT_SYMBOL", "WINM26")
    default_quantity = to_decimal(data.get("TRADER_PROFIT_DEFAULT_ORDER_QTY"), Decimal("1"))
    max_position_size = to_decimal(data.get("TRADER_PROFIT_MAX_POSITION_SIZE"), Decimal("1"))
    max_daily_loss = to_decimal(data.get("TRADER_PROFIT_MAX_DAILY_LOSS"), Decimal("1000"))
    max_market_age_seconds = int(data.get("TRADER_PROFIT_MAX_MARKET_AGE_SECONDS", "15"))
    log_level = data.get("TRADER_PROFIT_LOG_LEVEL", "INFO").upper()

    return AppConfig(
        requested_mode=requested_mode,
        mode=mode,
        live_enabled=live_enabled,
        symbol=symbol,
        default_quantity=default_quantity or Decimal("1"),
        max_position_size=max_position_size or Decimal("1"),
        max_daily_loss=max_daily_loss or Decimal("1000"),
        max_market_age_seconds=max_market_age_seconds,
        log_level=log_level,
    )

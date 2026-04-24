from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..domain import ExecutionReport, OrderCommand


@dataclass(slots=True)
class OfficialApiExecutionAdapter:
    provider_name: str
    base_url: str | None = None

    async def submit_order(self, order: OrderCommand) -> ExecutionReport:
        raise NotImplementedError("Official broker API adapter is not implemented yet")

    async def cancel_order(self, order_id: str) -> ExecutionReport:
        raise NotImplementedError("Official broker API adapter is not implemented yet")

    async def get_open_orders(self) -> Sequence[OrderCommand]:
        raise NotImplementedError("Official broker API adapter is not implemented yet")

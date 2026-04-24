from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class DocumentFinding:
    kind: str
    title: str
    url: str
    excerpt: str
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FundFinding:
    order_index: int
    name: str
    source_url: str
    list_metadata: dict[str, str] = field(default_factory=dict)
    category: str | None = None
    fund_class: str | None = None
    subtype: str | None = None
    manager: str | None = None
    administrator: str | None = None
    auditor: str | None = None
    benchmark: str | None = None
    minimum_investment: str | None = None
    risk_level: str | None = None
    risk_note: str | None = None
    historical_returns: dict[str, str] = field(default_factory=dict)
    fees: dict[str, str] = field(default_factory=dict)
    liquidity: str | None = None
    quotation_deadline: str | None = None
    settlement_deadline: str | None = None
    redemption_deadline: str | None = None
    strategy: str | None = None
    portfolio_composition: str | None = None
    net_assets: str | None = None
    quotaholders: str | None = None
    documents: list[DocumentFinding] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    governance_notes: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    information_gaps: list[str] = field(default_factory=list)
    is_featured: bool = False


@dataclass(slots=True)
class FundsResearchReport:
    portal_url: str
    docs_domain: str
    started_at: datetime
    finished_at: datetime | None = None
    funds: list[FundFinding] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    stopped_reason: str | None = None

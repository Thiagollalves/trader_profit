from __future__ import annotations

from collections import Counter
from typing import Callable, Sequence

from .models import DocumentFinding, FundFinding, FundsResearchReport


_REQUIRED_FIELD_LABELS: tuple[tuple[str, Callable[[FundFinding], bool]], ...] = (
    ("Categoria / Classe", lambda fund: any((fund.category, fund.fund_class, fund.subtype))),
    ("Gestor", lambda fund: bool(fund.manager)),
    ("Administrador", lambda fund: bool(fund.administrator)),
    ("Benchmark", lambda fund: bool(fund.benchmark)),
    ("Investimento minimo", lambda fund: bool(fund.minimum_investment)),
    ("Risco exibido", lambda fund: bool(fund.risk_level)),
    ("Nota de risco", lambda fund: bool(fund.risk_note)),
    ("Rentabilidade historica", lambda fund: bool(fund.historical_returns)),
    ("Taxas", lambda fund: bool(fund.fees)),
    ("Liquidez", lambda fund: bool(fund.liquidity)),
    ("Cotizacao", lambda fund: bool(fund.quotation_deadline)),
    ("Liquidacao", lambda fund: bool(fund.settlement_deadline)),
    ("Prazo de resgate", lambda fund: bool(fund.redemption_deadline)),
    ("Estrategia", lambda fund: bool(fund.strategy)),
    ("Composicao da carteira", lambda fund: bool(fund.portfolio_composition)),
    ("Patrimonio liquido", lambda fund: bool(fund.net_assets)),
    ("Numero de cotistas", lambda fund: bool(fund.quotaholders)),
)


def finalize_fund(fund: FundFinding) -> FundFinding:
    missing = [label for label, predicate in _REQUIRED_FIELD_LABELS if not predicate(fund)]
    if not fund.documents:
        missing.append("Documentos disponiveis")
    if not fund.risks:
        missing.append("Principais riscos")
    if not fund.governance_notes:
        missing.append("Governanca e controles")
    fund.information_gaps = missing
    if fund.documents:
        document_kinds = {document.kind.lower() for document in fund.documents}
        if "lamina" in document_kinds and "lamina" not in fund.insights:
            fund.insights.append("Lamina localizada e lida")
        if "regulamento" in document_kinds and "regulamento" not in fund.insights:
            fund.insights.append("Regulamento localizado e lido")
    return fund


def _normalize_empty(value: str | None) -> str:
    return value.strip() if value and value.strip() else "nao informado"


def _format_mapping(mapping: dict[str, str]) -> str:
    if not mapping:
        return "nao informado"
    return "; ".join(f"{key}: {value}" for key, value in mapping.items())


def _format_documents(documents: Sequence[DocumentFinding]) -> str:
    if not documents:
        return "nao informado"
    return "; ".join(f"{doc.kind}: {doc.title} ({doc.url})" for doc in documents)


def _format_bullets(items: Sequence[str]) -> str:
    if not items:
        return "nao informado"
    return "; ".join(items)


def _combine_nonempty(*values: str | None) -> str:
    items = [value.strip() for value in values if value and value.strip()]
    if not items:
        return "nao informado"
    return " / ".join(items)


def _build_overview(report: FundsResearchReport) -> list[str]:
    total = len(report.funds)
    if total == 0:
        return [
            "visao geral da pesquisa: nenhum fundo foi analisado",
            "quantidade de fundos analisados: 0",
            "escopo efetivamente coberto: apenas a navegacao inicial, sem itens percorridos",
            "limitacoes encontradas: sem dados coletados ou lista de fundos indisponivel",
        ]

    with_documents = sum(1 for fund in report.funds if fund.documents)
    with_risk = sum(1 for fund in report.funds if fund.risk_level or fund.risk_note)
    with_fees = sum(1 for fund in report.funds if fund.fees)
    featured = sum(1 for fund in report.funds if fund.is_featured)
    missing_docs = sum(1 for fund in report.funds if "Documentos disponiveis" in fund.information_gaps)

    return [
        "visao geral da pesquisa: fluxo executado em modo somente leitura",
        f"quantidade de fundos analisados: {total}",
        f"escopo efetivamente coberto: {with_documents} fundos com documentos lidos; {with_risk} com risco informado; {with_fees} com taxas identificadas",
        f"limitacoes encontradas: {missing_docs} fundos sem documento acessivel ou sem link documental; {featured} marcados como destaque na listagem",
    ]


def _build_general_insights(report: FundsResearchReport) -> list[str]:
    funds = report.funds
    if not funds:
        return ["nenhum insight consolidado, pois nenhum fundo foi analisado"]

    insights: list[str] = []
    total = len(funds)
    docs = Counter(document.kind.lower() for fund in funds for document in fund.documents)
    if docs:
        summary = ", ".join(f"{kind}: {count}" for kind, count in sorted(docs.items()))
        insights.append(f"documentacao observada por tipo: {summary}")

    risk_informed = sum(1 for fund in funds if fund.risk_level or fund.risk_note)
    insights.append(f"informacao de risco presente em {risk_informed}/{total} fundos")

    fee_informed = sum(1 for fund in funds if fund.fees)
    insights.append(f"informacao de taxas presente em {fee_informed}/{total} fundos")

    liquidity_values = [fund.liquidity for fund in funds if fund.liquidity]
    if liquidity_values:
        unique_liquidity = sorted({value.strip() for value in liquidity_values if value and value.strip()})
        insights.append(f"liquidez observada em: {', '.join(unique_liquidity[:8])}")

    risk_notes = [fund.risk_note for fund in funds if fund.risk_note]
    if risk_notes:
        insights.append("notas de risco extraidas em linguagem descritiva na tela de detalhe")

    featured = sum(1 for fund in funds if fund.is_featured)
    if featured:
        insights.append(f"{featured} fundo(s) marcados como destaque na listagem")

    return insights


def _build_alerts(report: FundsResearchReport) -> list[str]:
    alerts = list(report.alerts)
    if report.stopped_reason:
        alerts.append(f"parada preventiva: {report.stopped_reason}")
    missing_fields = Counter()
    for fund in report.funds:
        missing_fields.update(fund.information_gaps)
    if missing_fields:
        top_missing = ", ".join(f"{field} ({count})" for field, count in missing_fields.most_common(8))
        alerts.append(f"campos ausentes recorrentes: {top_missing}")
    return alerts or ["nenhuma limitacao adicional registrada"]


def render_report_markdown(report: FundsResearchReport) -> str:
    lines: list[str] = ["# Relatorio de pesquisa de fundos", ""]
    if report.finished_at is not None:
        lines.append(f"- Inicio: {report.started_at.isoformat()}")
        lines.append(f"- Fim: {report.finished_at.isoformat()}")
    lines.append(f"- Portal: {report.portal_url}")
    lines.append(f"- Dominio de documentos: {report.docs_domain}")
    lines.append("")

    lines.append("## Resumo executivo")
    for item in _build_overview(report):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Fundos analisados")
    if not report.funds:
        lines.append("- nenhum fundo analisado")
    else:
        for fund in report.funds:
            lines.extend(
                [
                    f"### Ordem na lista: {fund.order_index} | Nome: {fund.name}",
                    f"- Categoria / Classe: {_combine_nonempty(fund.category, fund.fund_class, fund.subtype)}",
                    f"- Gestor: {_normalize_empty(fund.manager)}",
                    f"- Administrador: {_normalize_empty(fund.administrator)}",
                    f"- Benchmark: {_normalize_empty(fund.benchmark)}",
                    f"- Investimento minimo: {_normalize_empty(fund.minimum_investment)}",
                    f"- Risco exibido: {_normalize_empty(fund.risk_level)}",
                    f"- Nota de risco: {_normalize_empty(fund.risk_note)}",
                    f"- Rentabilidade historica: {_format_mapping(fund.historical_returns)}",
                    f"- Taxas: {_format_mapping(fund.fees)}",
                    f"- Liquidez: {_normalize_empty(fund.liquidity)}",
                    f"- Cotizacao: {_normalize_empty(fund.quotation_deadline)}",
                    f"- Liquidacao: {_normalize_empty(fund.settlement_deadline)}",
                    f"- Prazo de resgate: {_normalize_empty(fund.redemption_deadline)}",
                    f"- Estrategia: {_normalize_empty(fund.strategy)}",
                    f"- Composicao da carteira: {_normalize_empty(fund.portfolio_composition)}",
                    f"- Patrimonio liquido: {_normalize_empty(fund.net_assets)}",
                    f"- Numero de cotistas: {_normalize_empty(fund.quotaholders)}",
                    f"- Documentos disponiveis: {_format_documents(fund.documents)}",
                    f"- Principais riscos: {_format_bullets(fund.risks)}",
                    f"- Governanca e controles: {_format_bullets(fund.governance_notes)}",
                    f"- Insights principais: {_format_bullets(fund.insights)}",
                    f"- Lacunas de informacao: {_format_bullets(fund.information_gaps)}",
                    "",
                ]
            )

    lines.append("## Insights gerais")
    for item in _build_general_insights(report):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Alertas e limitacoes")
    for item in _build_alerts(report):
        lines.append(f"- {item}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence
from urllib.parse import urljoin, urlparse


_TRANSACTIONAL_CONTROL_PATTERNS = (
    "aplicar",
    "investir",
    "resgatar",
    "confirmar",
    "aceitar",
    "assinar",
    "enviar ordem",
    "comprar",
    "vender",
    "transferir",
    "valor da aplicacao",
    "valor da aplicação",
    "quantidade",
    "ordem",
    "suitability",
)

_FUND_HINTS = (
    "fundo",
    "fundos",
    "fii",
    "fip",
    "fiagro",
    "etf",
    "classe",
    "gestor",
    "benchmark",
    "liquidez",
    "rentabilidade",
    "taxa",
)

_DOCUMENT_HINTS = (
    "lamina",
    "lâmina",
    "regulamento",
    "relatorio gerencial",
    "relatório gerencial",
    "relatorio",
    "documento",
)

_ROW_HINTS = (
    "gestor",
    "benchmark",
    "rentabilidade",
    "taxa",
    "liquidez",
    "cotistas",
    "categoria",
    "classe",
    "risco",
)


@dataclass(frozen=True, slots=True)
class LinkRecord:
    text: str
    href: str
    context: str = ""
    title: str = ""
    aria_label: str = ""


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip().lower()


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)
    pattern = re.compile(rf"\b{re.escape(normalized_phrase)}\b")
    return bool(pattern.search(normalized_text))


def same_domain(url: str, allowed_domains: Sequence[str]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_domains)


def allowed_url(url: str, allowed_domains: Sequence[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return same_domain(url, allowed_domains)


def resolve_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


def extract_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _label_matches(line: str, label: str) -> bool:
    normalized_line = normalize_text(line)
    normalized_label = normalize_text(label)
    return normalized_line.startswith(normalized_label)


def extract_labeled_value(text: str, labels: Sequence[str]) -> str | None:
    lines = extract_lines(text)
    normalized_labels = tuple(normalize_text(label) for label in labels)

    for index, line in enumerate(lines):
        normalized_line = normalize_text(line)
        for label in normalized_labels:
            if normalized_line.startswith(f"{label}:"):
                return line.split(":", 1)[1].strip()
            if normalized_line.startswith(f"{label} -"):
                return line.split("-", 1)[1].strip()
            if normalized_line == label and index + 1 < len(lines):
                candidate = lines[index + 1].strip()
                if candidate:
                    return candidate
    return None


def extract_section_lines(text: str, labels: Sequence[str], *, max_lines: int = 6) -> list[str]:
    lines = extract_lines(text)
    normalized_labels = tuple(normalize_text(label) for label in labels)

    for index, line in enumerate(lines):
        if normalize_text(line).rstrip(":") in normalized_labels:
            collected: list[str] = []
            for candidate in lines[index + 1 :]:
                normalized_candidate = normalize_text(candidate)
                if not candidate:
                    continue
                if normalized_candidate.endswith(":") or normalized_candidate in normalized_labels:
                    break
                collected.append(candidate)
                if len(collected) >= max_lines:
                    break
            return collected
    return []


def extract_return_metrics(text: str) -> dict[str, str]:
    periods = {
        "1 mês": ("1 mes", "1m"),
        "3 meses": ("3 meses", "3m"),
        "6 meses": ("6 meses", "6m"),
        "12 meses": ("12 meses", "12m"),
        "ano": ("ano", "ytd"),
        "desde o início": ("desde o inicio", "desde o início"),
    }

    metrics: dict[str, str] = {}
    for line in extract_lines(text):
        if "%" not in line:
            continue
        normalized_line = normalize_text(line)
        for period_label, aliases in periods.items():
            if any(alias in normalized_line for alias in aliases):
                metrics.setdefault(period_label, line)
    return metrics


def extract_fee_metrics(text: str) -> dict[str, str]:
    labels = {
        "Taxa de administração": ("taxa de administracao", "taxa de administração"),
        "Taxa de performance": ("taxa de performance",),
        "Taxa de saída": ("taxa de saida", "taxa de saída"),
        "Outras taxas": ("outras taxas",),
    }
    metrics: dict[str, str] = {}
    for display_label, aliases in labels.items():
        value = extract_labeled_value(text, aliases)
        if value:
            metrics[display_label] = value
    return metrics


def parse_fund_page_text(text: str) -> dict[str, object]:
    fields = {
        "category": ("categoria / classe", "categoria", "classe"),
        "fund_class": ("classe", "classe do fundo"),
        "subtype": ("subtipo",),
        "manager": ("gestor",),
        "administrator": ("administrador",),
        "auditor": ("auditor",),
        "benchmark": ("benchmark", "indice", "índice"),
        "minimum_investment": ("investimento mínimo", "aplicação mínima", "valor mínimo", "aporte mínimo"),
        "risk_level": ("nível de risco", "risco", "perfil de risco"),
        "risk_note": ("nota de risco",),
        "liquidity": ("liquidez",),
        "quotation_deadline": ("prazo de cotização", "cotização"),
        "settlement_deadline": ("prazo de liquidação", "liquidação"),
        "redemption_deadline": ("prazo total de resgate", "prazo de resgate", "resgate"),
        "strategy": ("estratégia", "política de investimento", "politica de investimento"),
        "portfolio_composition": ("composição da carteira", "alocação", "alocacao"),
        "net_assets": ("patrimônio líquido", "patrimonio liquido", "pl"),
        "quotaholders": ("cotistas",),
    }

    parsed: dict[str, object] = {
        key: extract_labeled_value(text, labels)
        for key, labels in fields.items()
    }
    parsed["historical_returns"] = extract_return_metrics(text)
    parsed["fees"] = extract_fee_metrics(text)
    parsed["risks"] = extract_section_lines(text, ("principais riscos", "riscos", "principais risco"))
    parsed["governance_notes"] = extract_section_lines(text, ("governança", "governanca", "controles", "controles de risco"))
    return parsed


def detect_transactional_screen(text: str, controls: Iterable[str]) -> str | None:
    normalized_text = normalize_text(text)
    normalized_controls = normalize_text("\n".join(controls))

    for phrase in _TRANSACTIONAL_CONTROL_PATTERNS:
        if _contains_phrase(normalized_controls, phrase):
            return phrase
    for phrase in _TRANSACTIONAL_CONTROL_PATTERNS:
        if phrase != "investir" and _contains_phrase(normalized_text, phrase):
            return phrase
    return None


def collect_candidate_links(
    raw_links: Iterable[LinkRecord],
    *,
    allowed_domains: Sequence[str],
    blocked_keywords: Sequence[str],
) -> list[LinkRecord]:
    blocked = {normalize_text(keyword) for keyword in blocked_keywords}
    results: list[LinkRecord] = []
    seen: set[tuple[str, str]] = set()

    for record in raw_links:
        href = record.href.strip()
        text = record.text.strip()
        context = record.context.strip()
        if not href:
            continue
        if not allowed_url(href, allowed_domains):
            continue

        combined = normalize_text(" ".join(part for part in (text, context, record.title, record.aria_label) if part))
        if any(_contains_phrase(combined, keyword) for keyword in blocked):
            continue

        has_fund_hint = any(_contains_phrase(combined, hint) for hint in _FUND_HINTS)
        has_row_hint = any(_contains_phrase(combined, hint) for hint in _ROW_HINTS)
        if not has_fund_hint and not has_row_hint and len(text.split()) < 2:
            continue
        if any(hint in combined for hint in _DOCUMENT_HINTS):
            continue

        key = (normalize_text(text), href.split("#", 1)[0])
        if key in seen:
            continue
        seen.add(key)
        results.append(record)

    return results

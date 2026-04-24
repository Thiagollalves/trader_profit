from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None or value.strip() == "":
        return default
    return int(value)


def _parse_path(value: str | None, default: str | None = None) -> Path | None:
    raw = value if value is not None and value.strip() != "" else default
    if raw is None:
        return None
    return Path(raw).expanduser()


def _load_dotenv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] in {'"', "'"} and value[-1:] == value[0]:
            value = value[1:-1]
        loaded[key] = value
    return loaded


@dataclass(frozen=True, slots=True)
class FundsResearchCredentials:
    login: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)

    @property
    def is_complete(self) -> bool:
        return bool(self.login and self.password)


@dataclass(frozen=True, slots=True)
class FundsResearchSelectors:
    list_selector: str | None = None
    item_selector: str | None = None
    name_selector: str | None = None
    document_selector: str | None = None
    login_user_selector: str | None = None
    login_password_selector: str | None = None
    login_submit_selector: str | None = None


@dataclass(frozen=True, slots=True)
class FundsResearchConfig:
    portal_url: str
    docs_domain: str
    credentials: FundsResearchCredentials
    selectors: FundsResearchSelectors
    output_path: Path
    debug_output_dir: Path
    profile_dir: Path
    session_state_path: Path | None
    headless: bool
    keep_browser_open: bool
    browser_channel: str
    browser_executable_path: Path | None
    timeout_ms: int
    max_funds: int | None
    map_open_page: bool
    funds_menu_keywords: tuple[str, ...]
    document_keywords: tuple[str, ...]
    blocked_action_keywords: tuple[str, ...]
    manual_login: bool

    @property
    def allowed_domains(self) -> tuple[str, ...]:
        parsed_portal = urlparse(self.portal_url)
        portal_host = parsed_portal.netloc.lower()
        docs_host = self.docs_domain.lower()
        if portal_host == docs_host:
            return (portal_host,)
        return (portal_host, docs_host)


def load_funds_research_config(
    env: Mapping[str, str] | None = None,
    *,
    dotenv_path: Path | None = None,
) -> FundsResearchConfig:
    data: dict[str, str] = {}
    cwd = Path.cwd()
    candidate_dotenv = dotenv_path or cwd / ".env"
    data.update(_load_dotenv_file(candidate_dotenv))
    if env is not None:
        data.update(dict(env))
    else:
        data.update(os.environ)

    portal_url = data.get("TRADER_PROFIT_FUNDS_PORTAL_URL", "https://app.santandercorretora.com.br/fundos/investir")
    docs_domain = data.get("TRADER_PROFIT_FUNDS_DOCS_DOMAIN", "toroinvestimentos.com.br")

    credentials = FundsResearchCredentials(
        login=data.get("TRADER_PROFIT_FUNDS_LOGIN"),
        password=data.get("TRADER_PROFIT_FUNDS_PASSWORD"),
    )

    selectors = FundsResearchSelectors(
        list_selector=data.get("TRADER_PROFIT_FUNDS_LIST_SELECTOR") or None,
        item_selector=data.get("TRADER_PROFIT_FUNDS_ITEM_SELECTOR") or None,
        name_selector=data.get("TRADER_PROFIT_FUNDS_NAME_SELECTOR") or None,
        document_selector=data.get("TRADER_PROFIT_FUNDS_DOCUMENT_SELECTOR") or None,
        login_user_selector=data.get("TRADER_PROFIT_FUNDS_LOGIN_USER_SELECTOR") or None,
        login_password_selector=data.get("TRADER_PROFIT_FUNDS_LOGIN_PASSWORD_SELECTOR") or None,
        login_submit_selector=data.get("TRADER_PROFIT_FUNDS_LOGIN_SUBMIT_SELECTOR") or None,
    )

    output_path = _parse_path(data.get("TRADER_PROFIT_FUNDS_OUTPUT"), "reports/funds_research.md")
    debug_output_dir = _parse_path(data.get("TRADER_PROFIT_FUNDS_DEBUG_DIR"), "reports/funds_debug")
    profile_dir = _parse_path(data.get("TRADER_PROFIT_FUNDS_PROFILE_DIR"), ".cache/trader_profit/funds_research_profile")
    session_state_path = _parse_path(data.get("TRADER_PROFIT_FUNDS_SESSION_STATE"))
    browser_executable_path = _parse_path(data.get("TRADER_PROFIT_FUNDS_BROWSER_EXECUTABLE_PATH"))

    headless = _parse_bool(data.get("TRADER_PROFIT_FUNDS_HEADLESS"), default=False)
    keep_browser_open_raw = data.get("TRADER_PROFIT_FUNDS_KEEP_BROWSER_OPEN")
    map_open_page_raw = data.get("TRADER_PROFIT_FUNDS_MAP_OPEN_PAGE")

    return FundsResearchConfig(
        portal_url=portal_url,
        docs_domain=docs_domain,
        credentials=credentials,
        selectors=selectors,
        output_path=output_path or Path("reports/funds_research.md"),
        debug_output_dir=debug_output_dir or Path("reports/funds_debug"),
        profile_dir=profile_dir or Path(".cache/trader_profit/funds_research_profile"),
        session_state_path=session_state_path,
        headless=headless,
        keep_browser_open=_parse_bool(keep_browser_open_raw, default=not headless),
        browser_channel=data.get("TRADER_PROFIT_FUNDS_BROWSER_CHANNEL", "chrome"),
        browser_executable_path=browser_executable_path,
        timeout_ms=_parse_int(data.get("TRADER_PROFIT_FUNDS_TIMEOUT_MS"), 45000) or 45000,
        max_funds=_parse_int(data.get("TRADER_PROFIT_FUNDS_MAX_FUNDS")),
        map_open_page=_parse_bool(map_open_page_raw, default=False),
        funds_menu_keywords=(
            "Todos os fundos",
            "Fundos de investimento",
            "Fundos de Investimento",
            "Fundos",
        ),
        document_keywords=(
            "Lamina",
            "Lâmina",
            "Regulamento",
            "Relatorio gerencial",
            "Relatório gerencial",
            "Relatorio Gerencial",
        ),
        blocked_action_keywords=(
            "Aplicar",
            "Investir",
            "Resgatar",
            "Confirmar",
            "Aceitar",
            "Assinar",
            "Enviar ordem",
            "Escolher",
            "Comprar",
            "Vender",
            "Transferir",
        ),
        manual_login=_parse_bool(data.get("TRADER_PROFIT_FUNDS_MANUAL_LOGIN"), default=False),
    )

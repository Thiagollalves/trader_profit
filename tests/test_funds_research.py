from datetime import datetime, timezone
from pathlib import Path

from trader_profit.funds_research.config import load_funds_research_config
from trader_profit.funds_research.models import FundFinding, FundsResearchReport
from trader_profit.funds_research.parsing import detect_transactional_screen, parse_fund_page_text
from trader_profit.funds_research.prompt import render_safe_prompt
from trader_profit.funds_research.report import finalize_fund, render_report_markdown


def test_load_funds_research_config_reads_dotenv(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "TRADER_PROFIT_FUNDS_LOGIN=cpf123",
                "TRADER_PROFIT_FUNDS_PASSWORD=senha123",
                "TRADER_PROFIT_FUNDS_OUTPUT=reports/custom-report.md",
            ]
        ),
        encoding="utf-8",
    )

    config = load_funds_research_config(
        env={
            "TRADER_PROFIT_FUNDS_PORTAL_URL": "https://example.com/portal",
            "TRADER_PROFIT_FUNDS_DOCS_DOMAIN": "docs.example.com",
        },
        dotenv_path=dotenv,
    )

    assert config.portal_url == "https://example.com/portal"
    assert config.docs_domain == "docs.example.com"
    assert config.credentials.login == "cpf123"
    assert config.credentials.password == "senha123"
    assert config.output_path == Path("reports/custom-report.md")
    assert config.credentials.is_complete is True
    assert config.keep_browser_open is True
    assert config.map_open_page is False


def test_load_funds_research_config_defaults_browser_hold_off_in_headless_mode(tmp_path):
    config = load_funds_research_config(
        env={
            "TRADER_PROFIT_FUNDS_HEADLESS": "true",
        },
        dotenv_path=tmp_path / "missing.env",
    )

    assert config.headless is True
    assert config.keep_browser_open is False
    assert config.map_open_page is False


def test_load_funds_research_config_enables_page_map(tmp_path):
    config = load_funds_research_config(
        env={
            "TRADER_PROFIT_FUNDS_MAP_OPEN_PAGE": "true",
        },
        dotenv_path=tmp_path / "missing.env",
    )

    assert config.map_open_page is True


def test_render_safe_prompt_uses_placeholders_and_keeps_secrets_out(tmp_path):
    config = load_funds_research_config(
        env={
            "TRADER_PROFIT_FUNDS_PORTAL_URL": "https://example.com/portal",
            "TRADER_PROFIT_FUNDS_DOCS_DOMAIN": "docs.example.com",
            "TRADER_PROFIT_FUNDS_LOGIN": "secret-user",
            "TRADER_PROFIT_FUNDS_PASSWORD": "secret-pass",
        },
        dotenv_path=tmp_path / "missing.env",
    )

    prompt = render_safe_prompt(config)

    assert "secret-user" not in prompt
    assert "secret-pass" not in prompt
    assert "{{TRADER_PROFIT_FUNDS_LOGIN}}" in prompt
    assert "{{TRADER_PROFIT_FUNDS_PASSWORD}}" in prompt
    assert "https://example.com/portal" in prompt
    assert "docs.example.com" in prompt


def test_transaction_detection_ignores_common_informational_words():
    assert detect_transactional_screen("Painel de investimentos", ["Investimentos"]) is None
    assert detect_transactional_screen("Confirme o investimento", ["Confirmar"]) == "confirmar"
    assert detect_transactional_screen("Escolher um fundo", ["Escolher"]) is None


def test_parse_and_render_fund_report():
    parsed = parse_fund_page_text(
        "\n".join(
            [
                "Categoria: Multimercado",
                "Gestor: XP Asset",
                "Administrador: Santander",
                "Benchmark: CDI",
                "Taxa de administracao: 1,0%",
                "1 mes 0,5%",
                "Principais riscos",
                "- Mercado",
                "- Liquidez",
                "Governanca",
                "- Controles operacionais",
            ]
        )
    )

    fund = FundFinding(
        order_index=1,
        name="Fundo Exemplo",
        source_url="https://example.com/fundo",
        category=parsed["category"] if isinstance(parsed.get("category"), str) else None,
        manager=parsed["manager"] if isinstance(parsed.get("manager"), str) else None,
        administrator=parsed["administrator"] if isinstance(parsed.get("administrator"), str) else None,
        benchmark=parsed["benchmark"] if isinstance(parsed.get("benchmark"), str) else None,
        fees=dict(parsed.get("fees") or {}),
        historical_returns=dict(parsed.get("historical_returns") or {}),
        risks=list(parsed.get("risks") or []),
        governance_notes=list(parsed.get("governance_notes") or []),
        documents=[],
    )
    finalize_fund(fund)
    report = FundsResearchReport(
        portal_url="https://example.com/portal",
        docs_domain="docs.example.com",
        started_at=datetime.now(timezone.utc),
        funds=[fund],
    )
    markdown = render_report_markdown(report)

    assert "Resumo executivo" in markdown
    assert "Fundo Exemplo" in markdown
    assert "Taxas" in markdown
    assert "Lacunas de informacao" in markdown

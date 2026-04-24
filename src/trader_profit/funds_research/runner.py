from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..observability import configure_logging
from .config import FundsResearchConfig
from .models import DocumentFinding, FundFinding, FundsResearchReport
from .parsing import LinkRecord, allowed_url, collect_candidate_links, detect_transactional_screen, parse_fund_page_text
from .report import finalize_fund, render_report_markdown


class FundsResearchError(RuntimeError):
    pass


class FundsResearchDependencyError(FundsResearchError):
    pass


class FundsResearchSecurityError(FundsResearchError):
    pass


@dataclass(frozen=True, slots=True)
class FundsResearchResult:
    report: FundsResearchReport
    markdown: str
    output_path: Path
    visited_urls: tuple[str, ...]


class FundsResearchRunner:
    def __init__(self, config: FundsResearchConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or configure_logging("INFO", logger_name="trader_profit.funds_research")
        self._visited_urls: list[str] = []

    async def run(self) -> FundsResearchResult:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise FundsResearchDependencyError(
                "Playwright nao esta instalado. Instale o extra browser: py -m pip install -e \".[browser]\""
            ) from exc

        started_at = datetime.now(timezone.utc)
        manual_login_mode = self.config.manual_login or not self.config.credentials.is_complete
        hold_browser_open = manual_login_mode or self.config.keep_browser_open
        report = FundsResearchReport(
            portal_url=self.config.portal_url,
            docs_domain=self.config.docs_domain,
            started_at=started_at,
        )

        self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.profile_dir.mkdir(parents=True, exist_ok=True)
        if self.config.session_state_path is not None:
            self.config.session_state_path.parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            context = None
            try:
                context = await self._launch_context(playwright)
                page = await context.new_page()
            except Exception as exc:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                await self._save_startup_artifacts(reason=f"startup failure: {exc}", error=exc)
                raise
            try:
                await page.goto(self.config.portal_url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                self._record_visit(page.url)
                await self._ensure_safe_page(page, context="portal")
                manual_login_mode = self.config.manual_login or not self.config.credentials.is_complete
                if manual_login_mode:
                    page = await self._open_login_entrypoint(page, context)
                    await self._wait_for_login_completion(page)
                else:
                    await self._authenticate_if_needed(page)
                if self.config.map_open_page:
                    stopped_reason = "page map requested"
                    report.stopped_reason = stopped_reason
                    report.alerts.append(stopped_reason)
                    await self._save_page_map_artifacts(page, reason=stopped_reason)
                else:
                    await self._navigate_to_funds_listing(page)
                    await self._ensure_safe_page(page, context="funds-list")
                    fund_entries = await self._collect_fund_entries(page)
                    if self.config.max_funds is not None:
                        fund_entries = fund_entries[: self.config.max_funds]

                    if not fund_entries:
                        stopped_reason = "nenhum fundo detectado na listagem"
                        report.stopped_reason = stopped_reason
                        report.alerts.append(stopped_reason)
                        await self._save_debug_artifacts(page, reason=stopped_reason)

                    for index, entry in enumerate(fund_entries, start=1):
                        fund = await self._inspect_fund(context, entry, order_index=index)
                        report.funds.append(finalize_fund(fund))

            except FundsResearchSecurityError as exc:
                report.stopped_reason = str(exc)
                report.alerts.append(str(exc))
                try:
                    await self._save_debug_artifacts(page, reason=str(exc))
                except Exception:
                    pass
            except PlaywrightTimeoutError as exc:
                report.stopped_reason = f"timeout: {exc}"
                report.alerts.append(report.stopped_reason)
                try:
                    await self._save_debug_artifacts(page, reason=report.stopped_reason)
                except Exception:
                    pass
            except Exception as exc:
                report.stopped_reason = f"unexpected error: {exc}"
                report.alerts.append(report.stopped_reason)
                try:
                    await self._save_debug_artifacts(page, reason=report.stopped_reason)
                except Exception:
                    pass
            finally:
                if hold_browser_open:
                    try:
                        await self._wait_for_close_command()
                    except Exception:
                        pass
                if self.config.session_state_path is not None:
                    try:
                        await context.storage_state(path=str(self.config.session_state_path))
                    except Exception:
                        pass
                if context is not None:
                    await context.close()

        report.finished_at = datetime.now(timezone.utc)
        markdown = render_report_markdown(report)
        self.config.output_path.write_text(markdown, encoding="utf-8")

        self.logger.info(
            "funds research complete",
            extra={
                "funds_analyzed": len(report.funds),
                "output_path": str(self.config.output_path),
                "stopped_reason": report.stopped_reason,
            },
        )

        return FundsResearchResult(
            report=report,
            markdown=markdown,
            output_path=self.config.output_path,
            visited_urls=tuple(self._visited_urls),
        )

    async def _save_debug_artifacts(self, page: Any, *, reason: str) -> None:
        self.config.debug_output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = self.config.debug_output_dir / f"{stamp}"

        screenshot_path: Path | None = base.with_suffix(".png")
        html_path: Path | None = base.with_suffix(".html")
        json_path: Path | None = base.with_suffix(".json")

        try:
            await page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            screenshot_path = None

        try:
            html_path.write_text(await page.content(), encoding="utf-8")
        except Exception:
            html_path = None

        try:
            links = await self._collect_raw_links(page)
            controls = await self._collect_control_texts(page)
            payload = {
                "reason": reason,
                "url": page.url,
                "title": await page.title(),
                "visited_urls": list(self._visited_urls),
                "links": [
                    {
                        "text": record.text,
                        "href": record.href,
                        "context": record.context,
                        "title": record.title,
                        "aria_label": record.aria_label,
                    }
                    for record in links
                ],
                "controls": controls,
            }
            json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            json_path = None

        self.logger.info(
            "debug artifacts saved",
            extra={
                "reason": reason,
                "screenshot": str(screenshot_path) if screenshot_path is not None else None,
                "html": str(html_path) if html_path is not None else None,
                "json": str(json_path) if json_path is not None else None,
            },
        )

    async def _save_page_map_artifacts(self, page: Any, *, reason: str) -> None:
        self.config.debug_output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = self.config.debug_output_dir / f"{stamp}_page_map"

        screenshot_path: Path | None = base.with_suffix(".png")
        html_path: Path | None = base.with_suffix(".html")
        json_path: Path | None = base.with_suffix(".json")
        md_path: Path | None = base.with_suffix(".md")

        try:
            await page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            screenshot_path = None

        try:
            html_path.write_text(await page.content(), encoding="utf-8")
        except Exception:
            html_path = None

        try:
            headings = await self._collect_heading_texts(page)
            controls = await self._collect_control_texts(page)
            links = await self._collect_raw_links(page)
            visible_text = await self._extract_page_text(page)
            payload = {
                "reason": reason,
                "url": page.url,
                "title": await page.title(),
                "visited_urls": list(self._visited_urls),
                "headings": headings,
                "controls": controls,
                "links": [
                    {
                        "text": record.text,
                        "href": record.href,
                        "context": record.context,
                        "title": record.title,
                        "aria_label": record.aria_label,
                    }
                    for record in links
                ],
                "visible_text_lines": self._extract_text_lines(visible_text, limit=200),
            }
            json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            md_path.write_text(self._render_page_map_markdown(payload), encoding="utf-8")
        except Exception:
            json_path = None
            md_path = None

        self.logger.info(
            "page map saved",
            extra={
                "reason": reason,
                "screenshot": str(screenshot_path) if screenshot_path is not None else None,
                "html": str(html_path) if html_path is not None else None,
                "json": str(json_path) if json_path is not None else None,
                "markdown": str(md_path) if md_path is not None else None,
            },
        )

    async def _save_startup_artifacts(self, *, reason: str, error: BaseException | None = None) -> None:
        self.config.debug_output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = self.config.debug_output_dir / f"{stamp}_startup"

        json_path = base.with_suffix(".json")
        md_path = base.with_suffix(".md")

        payload = {
            "reason": reason,
            "exception": f"{type(error).__name__}: {error}" if error is not None else None,
            "portal_url": self.config.portal_url,
            "docs_domain": self.config.docs_domain,
            "profile_dir": str(self.config.profile_dir),
            "session_state_path": str(self.config.session_state_path) if self.config.session_state_path is not None else None,
            "browser_channel": self.config.browser_channel,
            "browser_executable_path": str(self.config.browser_executable_path) if self.config.browser_executable_path is not None else None,
            "headless": self.config.headless,
            "keep_browser_open": self.config.keep_browser_open,
            "manual_login": self.config.manual_login,
            "map_open_page": self.config.map_open_page,
            "visited_urls": list(self._visited_urls),
        }

        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(self._render_startup_artifacts_markdown(payload), encoding="utf-8")

        self.logger.info(
            "startup diagnostics saved",
            extra={
                "reason": reason,
                "json": str(json_path),
                "markdown": str(md_path),
            },
        )

    async def _open_login_entrypoint(self, page: Any, context: Any) -> Any:
        if await self._page_looks_authenticated(page):
            return page

        before_pages = list(context.pages)
        clicked = await self._click_login_entrypoint(page)
        if not clicked:
            self.logger.info(
                "login entrypoint not found",
                extra={"note": "continuing with the current page and waiting for authentication"},
            )
            return page

        login_page = await self._await_page_after_click(context, before_pages, fallback_page=page)
        await self._close_other_pages(context, keep_page=login_page)
        try:
            await login_page.bring_to_front()
        except Exception:
            pass
        return login_page

    async def _wait_for_login_completion(self, page: Any) -> None:
        self.logger.info(
            "waiting for login completion",
            extra={"note": "complete the login in the browser; automation resumes automatically once authenticated"},
        )
        deadline = time.monotonic() + max(self.config.timeout_ms / 1000 * 30, 600.0)
        while time.monotonic() < deadline:
            if await self._page_looks_authenticated(page):
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=self.config.timeout_ms)
                except Exception:
                    pass
                self._record_visit(page.url)
                await self._ensure_safe_page(page, context="manual-login")
                return
            await asyncio.sleep(1.0)
        raise FundsResearchSecurityError("Tempo esgotado aguardando o login manual ser concluido")

    async def _click_login_entrypoint(self, page: Any) -> bool:
        login_keywords = (
            "Entrar",
            "Login",
            "Acessar",
            "Acesse",
            "Acesse sua conta",
            "Fazer login",
            "Faça login",
        )
        candidates: list[Any] = []
        for keyword in login_keywords:
            candidates.extend(
                [
                    page.get_by_role("link", name=keyword, exact=False),
                    page.get_by_role("button", name=keyword, exact=False),
                    page.get_by_role("menuitem", name=keyword, exact=False),
                    page.get_by_text(keyword, exact=False),
                ]
            )
        return await self._click_first(candidates)

    async def _await_page_after_click(self, context: Any, before_pages: Sequence[Any], *, fallback_page: Any) -> Any:
        deadline = time.monotonic() + 8.0
        before_ids = {id(page) for page in before_pages}
        while time.monotonic() < deadline:
            for candidate in reversed(list(context.pages)):
                if id(candidate) not in before_ids:
                    try:
                        await candidate.wait_for_load_state("domcontentloaded", timeout=min(self.config.timeout_ms, 5000))
                    except Exception:
                        pass
                    return candidate
            current = context.pages[-1] if context.pages else fallback_page
            if current.url != fallback_page.url:
                try:
                    await current.wait_for_load_state("domcontentloaded", timeout=min(self.config.timeout_ms, 5000))
                except Exception:
                    pass
                return current
            await asyncio.sleep(0.2)
        return context.pages[-1] if context.pages else fallback_page

    async def _close_other_pages(self, context: Any, *, keep_page: Any) -> None:
        for candidate in list(context.pages):
            if candidate is keep_page:
                continue
            try:
                await candidate.close()
            except Exception:
                pass

    async def _launch_context(self, playwright: Any) -> Any:
        launch_kwargs: dict[str, Any] = {
            "headless": self.config.headless,
            "locale": "pt-BR",
        }
        if self.config.browser_executable_path is not None:
            launch_kwargs["executable_path"] = str(self.config.browser_executable_path)
        else:
            launch_kwargs["channel"] = self.config.browser_channel

        return await playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.config.profile_dir),
            **launch_kwargs,
        )

    async def _authenticate_if_needed(self, page: Any) -> None:
        if await self._page_looks_authenticated(page):
            return
        if not self.config.credentials.is_complete:
            raise FundsResearchSecurityError(
                "Sessao nao autenticada e credenciais nao configuradas. Preencha TRADER_PROFIT_FUNDS_LOGIN e TRADER_PROFIT_FUNDS_PASSWORD em .env"
            )

        await self._fill_login_form(page)
        await page.wait_for_load_state("domcontentloaded", timeout=self.config.timeout_ms)
        self._record_visit(page.url)
        await self._ensure_safe_page(page, context="post-login")

    async def _wait_for_close_command(self) -> None:
        self.logger.info("browser hold requested", extra={"note": "press Enter to close the browser"})
        await asyncio.to_thread(input, "A janela vai continuar aberta. Pressione Enter aqui para fechar o navegador...")

    async def _page_looks_authenticated(self, page: Any) -> bool:
        url = page.url.lower()
        if "login" in url or "entrar" in url:
            return False
        try:
            if await page.locator("input[type='password']").count() > 0:
                return False
        except Exception:
            pass
        try:
            controls = await self._collect_control_texts(page)
            combined = self._normalize_text("\n".join(controls))
            if any(keyword in combined for keyword in ("senha", "entrar", "acessar")):
                return False
        except Exception:
            pass
        return True

    async def _fill_login_form(self, page: Any) -> None:
        username = self.config.credentials.login
        password = self.config.credentials.password
        if username is None or password is None:
            raise FundsResearchSecurityError("Credenciais ausentes")

        username_locators = self._login_username_locators(page)
        password_locators = self._login_password_locators(page)
        submit_locators = self._login_submit_locators(page)

        if not await self._fill_first(username_locators, username):
            raise FundsResearchSecurityError("Nao foi possivel localizar o campo de login")
        if not await self._fill_first(password_locators, password):
            raise FundsResearchSecurityError("Nao foi possivel localizar o campo de senha")
        if not await self._click_first(submit_locators):
            raise FundsResearchSecurityError("Nao foi possivel localizar o botao de entrada")

    def _login_username_locators(self, page: Any) -> list[Any]:
        selectors = [
            page.locator("input[type='text']"),
            page.locator("input[type='email']"),
            page.get_by_label("login", exact=False),
            page.get_by_label("usuario", exact=False),
            page.get_by_label("usuário", exact=False),
            page.get_by_label("cpf", exact=False),
            page.get_by_placeholder("login", exact=False),
            page.get_by_placeholder("usuario", exact=False),
            page.get_by_placeholder("usuário", exact=False),
            page.get_by_placeholder("cpf", exact=False),
        ]
        if self.config.selectors.login_user_selector:
            selectors.insert(0, page.locator(self.config.selectors.login_user_selector))
        return selectors

    def _login_password_locators(self, page: Any) -> list[Any]:
        selectors = [
            page.locator("input[type='password']"),
            page.get_by_label("senha", exact=False),
            page.get_by_placeholder("senha", exact=False),
        ]
        if self.config.selectors.login_password_selector:
            selectors.insert(0, page.locator(self.config.selectors.login_password_selector))
        return selectors

    def _login_submit_locators(self, page: Any) -> list[Any]:
        selectors = [
            page.get_by_role("button", name="entrar", exact=False),
            page.get_by_role("button", name="acessar", exact=False),
            page.get_by_role("button", name="continuar", exact=False),
            page.get_by_role("button", name="login", exact=False),
            page.get_by_text("entrar", exact=False),
        ]
        if self.config.selectors.login_submit_selector:
            selectors.insert(0, page.locator(self.config.selectors.login_submit_selector))
        return selectors

    async def _navigate_to_funds_listing(self, page: Any) -> None:
        if self.config.selectors.list_selector:
            locator = page.locator(self.config.selectors.list_selector)
            if await locator.count() > 0:
                return

        if await self._funds_listing_visible(page):
            return

        direct_targets = (
            "Todos os fundos",
            "Fundos de investimento",
            "Fundos de Investimento",
            "Fundos",
        )
        investments_targets = (
            "Investimentos",
            "INVESTIMENTOS",
        )

        if await self._click_navigation_targets(page, direct_targets):
            await self._settle_navigation(page)
            if await self._funds_listing_visible(page):
                return

        if await self._click_navigation_targets(page, investments_targets):
            await self._settle_navigation(page)
            if await self._click_navigation_targets(page, direct_targets):
                await self._settle_navigation(page)
                if await self._funds_listing_visible(page):
                    return

        for keyword in self.config.funds_menu_keywords:
            if await self._click_navigation_targets(page, (keyword,)):
                await self._settle_navigation(page)
                if await self._funds_listing_visible(page):
                    return

    async def _funds_listing_visible(self, page: Any) -> bool:
        if self.config.selectors.list_selector:
            try:
                if await page.locator(self.config.selectors.list_selector).count() > 0:
                    return True
            except Exception:
                pass
        try:
            entries = await self._collect_fund_entries(page)
        except Exception:
            entries = []
        return bool(entries)

    async def _settle_navigation(self, page: Any) -> None:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=self.config.timeout_ms)
        except Exception:
            pass
        try:
            await page.wait_for_timeout(800)
        except Exception:
            pass
        self._record_visit(page.url)
        await self._ensure_safe_page(page, context="funds-list-navigation")

    async def _click_navigation_targets(self, page: Any, keywords: Sequence[str]) -> bool:
        for keyword in keywords:
            candidates = [
                page.get_by_role("link", name=keyword, exact=False),
                page.get_by_role("button", name=keyword, exact=False),
                page.get_by_role("menuitem", name=keyword, exact=False),
                page.get_by_text(keyword, exact=False),
            ]
            if await self._click_first(candidates):
                return True
            try:
                visible_locator = page.locator(
                    "a, button, [role='button'], [role='link'], [role='menuitem']"
                ).filter(has_text=keyword)
                if await self._click_first([visible_locator]):
                    return True
            except Exception:
                continue
        return False

    async def _collect_fund_entries(self, page: Any) -> list[LinkRecord]:
        if self.config.selectors.item_selector:
            items = page.locator(self.config.selectors.item_selector)
            count = await items.count()
            candidates: list[LinkRecord] = []
            for index in range(count):
                item = items.nth(index)
                try:
                    text = await item.inner_text(timeout=self.config.timeout_ms)
                except Exception:
                    text = ""
                href = await self._item_href(item)
                if href:
                    candidates.append(LinkRecord(text=text.strip(), href=href, context=text))
            filtered = collect_candidate_links(
                candidates,
                allowed_domains=self.config.allowed_domains,
                blocked_keywords=self.config.blocked_action_keywords,
            )
            if filtered:
                return filtered

        raw_links = await self._collect_raw_links(page)
        filtered = collect_candidate_links(
            raw_links,
            allowed_domains=self.config.allowed_domains,
            blocked_keywords=self.config.blocked_action_keywords,
        )
        if filtered:
            return filtered
        return filtered

    async def _collect_raw_links(self, page: Any) -> list[LinkRecord]:
        records: list[LinkRecord] = []
        try:
            payload = await page.evaluate(
                """
                () => Array.from(document.querySelectorAll('a[href]')).map((el) => {
                    const context = el.closest('tr, li, article, section, [role="row"], [class*="card"], [class*="item"]');
                    return {
                        text: (el.innerText || el.textContent || '').trim(),
                        href: el.href || '',
                        context: context ? (context.innerText || context.textContent || '').trim() : '',
                        title: (el.getAttribute('title') || '').trim(),
                        aria_label: (el.getAttribute('aria-label') || '').trim(),
                    };
                })
                """
            )
        except Exception:
            payload = []

        for item in payload or []:
            href = str(item.get("href") or "").strip()
            if not href:
                continue
            text = str(item.get("text") or "").strip()
            context = str(item.get("context") or "").strip()
            title = str(item.get("title") or "").strip()
            aria_label = str(item.get("aria_label") or "").strip()
            records.append(LinkRecord(text=text, href=href, context=context, title=title, aria_label=aria_label))
        return records

    async def _inspect_fund(self, context: Any, entry: LinkRecord, *, order_index: int) -> FundFinding:
        detail_page = await context.new_page()
        try:
            await detail_page.goto(entry.href, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
            self._record_visit(detail_page.url)
            await self._ensure_safe_page(detail_page, context=f"fund-{order_index}")

            title = (await detail_page.title()).strip() or entry.text or f"Fundo {order_index}"
            if self.config.selectors.name_selector:
                try:
                    name_locator = detail_page.locator(self.config.selectors.name_selector)
                    if await name_locator.count() > 0:
                        extracted_name = (await name_locator.first.inner_text(timeout=self.config.timeout_ms)).strip()
                        if extracted_name:
                            title = extracted_name
                except Exception:
                    pass
            text = await self._extract_page_text(detail_page)
            parsed = parse_fund_page_text(text)

            documents = await self._collect_documents(context, detail_page)
            source_url = detail_page.url
            fund = FundFinding(
                order_index=order_index,
                name=title,
                source_url=source_url,
                list_metadata={
                    "list_text": entry.text,
                    "context": entry.context,
                    "href": entry.href,
                },
                category=parsed.get("category") if isinstance(parsed.get("category"), str) else None,
                fund_class=parsed.get("fund_class") if isinstance(parsed.get("fund_class"), str) else None,
                subtype=parsed.get("subtype") if isinstance(parsed.get("subtype"), str) else None,
                manager=parsed.get("manager") if isinstance(parsed.get("manager"), str) else None,
                administrator=parsed.get("administrator") if isinstance(parsed.get("administrator"), str) else None,
                auditor=parsed.get("auditor") if isinstance(parsed.get("auditor"), str) else None,
                benchmark=parsed.get("benchmark") if isinstance(parsed.get("benchmark"), str) else None,
                minimum_investment=parsed.get("minimum_investment") if isinstance(parsed.get("minimum_investment"), str) else None,
                risk_level=parsed.get("risk_level") if isinstance(parsed.get("risk_level"), str) else None,
                risk_note=parsed.get("risk_note") if isinstance(parsed.get("risk_note"), str) else None,
                historical_returns=dict(parsed.get("historical_returns") or {}),
                fees=dict(parsed.get("fees") or {}),
                liquidity=parsed.get("liquidity") if isinstance(parsed.get("liquidity"), str) else None,
                quotation_deadline=parsed.get("quotation_deadline") if isinstance(parsed.get("quotation_deadline"), str) else None,
                settlement_deadline=parsed.get("settlement_deadline") if isinstance(parsed.get("settlement_deadline"), str) else None,
                redemption_deadline=parsed.get("redemption_deadline") if isinstance(parsed.get("redemption_deadline"), str) else None,
                strategy=parsed.get("strategy") if isinstance(parsed.get("strategy"), str) else None,
                portfolio_composition=parsed.get("portfolio_composition") if isinstance(parsed.get("portfolio_composition"), str) else None,
                net_assets=parsed.get("net_assets") if isinstance(parsed.get("net_assets"), str) else None,
                quotaholders=parsed.get("quotaholders") if isinstance(parsed.get("quotaholders"), str) else None,
                documents=documents,
                risks=list(parsed.get("risks") or []),
                governance_notes=list(parsed.get("governance_notes") or []),
                insights=[],
                is_featured="destaque" in self._normalize_text(entry.text + " " + entry.context),
            )
            if fund.documents:
                fund.insights.append(f"{len(fund.documents)} documento(s) lido(s)")
            if fund.is_featured:
                fund.insights.append("item marcado como destaque na listagem")
            return fund
        finally:
            await detail_page.close()

    async def _collect_documents(self, context: Any, page: Any) -> list[DocumentFinding]:
        if self.config.selectors.document_selector:
            locator = page.locator(self.config.selectors.document_selector)
            count = await locator.count()
            raw_docs: list[LinkRecord] = []
            for index in range(count):
                item = locator.nth(index)
                try:
                    text = await item.inner_text(timeout=self.config.timeout_ms)
                except Exception:
                    text = ""
                href = await self._item_href(item)
                if href:
                    raw_docs.append(LinkRecord(text=text.strip(), href=href, context=text))
            docs = [
                record
                for record in raw_docs
                if any(
                    self._normalize_text(keyword)
                    in self._normalize_text(" ".join([record.text, record.context, record.title, record.aria_label]))
                    for keyword in self.config.document_keywords
                )
                and allowed_url(record.href, self.config.allowed_domains)
            ]
            if docs:
                return [await self._inspect_document(context, record) for record in docs]

        try:
            payload = await page.evaluate(
                """
                () => Array.from(document.querySelectorAll('a[href]')).map((el) => {
                    const context = el.closest('article, section, li, tr, [role="row"], [class*="card"], [class*="document"]');
                    return {
                        text: (el.innerText || el.textContent || '').trim(),
                        href: el.href || '',
                        context: context ? (context.innerText || context.textContent || '').trim() : '',
                        title: (el.getAttribute('title') || '').trim(),
                        aria_label: (el.getAttribute('aria-label') || '').trim(),
                    };
                })
                """
            )
        except Exception:
            payload = []

        raw_docs = [
            LinkRecord(
                text=str(item.get("text") or "").strip(),
                href=str(item.get("href") or "").strip(),
                context=str(item.get("context") or "").strip(),
                title=str(item.get("title") or "").strip(),
                aria_label=str(item.get("aria_label") or "").strip(),
            )
            for item in payload or []
        ]
        docs: list[DocumentFinding] = []
        for record in raw_docs:
            if not record.href:
                continue
            normalized = self._normalize_text(" ".join([record.text, record.context, record.title, record.aria_label]))
            if not any(self._normalize_text(keyword) in normalized for keyword in self.config.document_keywords):
                continue
            if not allowed_url(record.href, self.config.allowed_domains):
                continue
            docs.append(await self._inspect_document(context, record))
        return docs

    async def _inspect_document(self, context: Any, record: LinkRecord) -> DocumentFinding:
        document_page = await context.new_page()
        try:
            await document_page.goto(record.href, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
            self._record_visit(document_page.url)
            await self._ensure_safe_page(document_page, context=f"document:{record.text or record.title}")
            title = (await document_page.title()).strip() or record.text or record.title or "Documento"
            text = await self._extract_page_text(document_page)
            excerpt = text[:1200].strip()
            kind = self._classify_document_kind(record, title)
            return DocumentFinding(kind=kind, title=title, url=document_page.url, excerpt=excerpt)
        finally:
            await document_page.close()

    async def _extract_page_text(self, page: Any) -> str:
        try:
            body = page.locator("body")
            return await body.inner_text(timeout=self.config.timeout_ms)
        except Exception:
            return ""

    async def _ensure_safe_page(self, page: Any, *, context: str) -> None:
        url = page.url
        if not allowed_url(url, self.config.allowed_domains):
            raise FundsResearchSecurityError(f"Dominio fora do permitido em {context}: {url}")

        if self.config.manual_login and "entrar" in url.lower():
            return

        text = await self._extract_page_text(page)
        controls = await self._collect_control_texts(page)
        blocked = detect_transactional_screen(text, controls)
        if blocked:
            raise FundsResearchSecurityError(f"Tela transacional detectada em {context}: {blocked}")

    async def _collect_control_texts(self, page: Any) -> list[str]:
        try:
            payload = await page.evaluate(
                """
                () => Array.from(document.querySelectorAll('button, [role="button"], input, textarea, select, a')).map((el) => {
                    return [
                        (el.innerText || el.textContent || '').trim(),
                        (el.getAttribute('aria-label') || '').trim(),
                        (el.getAttribute('placeholder') || '').trim(),
                        (el.getAttribute('value') || '').trim(),
                    ].filter(Boolean).join(' ');
                })
                """
            )
        except Exception:
            payload = []
        return [str(item).strip() for item in payload or [] if str(item).strip()]

    async def _collect_heading_texts(self, page: Any) -> list[str]:
        try:
            payload = await page.evaluate(
                """
                () => Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6')).map((el) => {
                    const text = (el.innerText || el.textContent || '').trim();
                    return text ? `${el.tagName.toLowerCase()}: ${text}` : '';
                }).filter(Boolean)
                """
            )
        except Exception:
            payload = []
        return [str(item).strip() for item in payload or [] if str(item).strip()]

    def _extract_text_lines(self, text: str, *, limit: int) -> list[str]:
        lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lines.append(stripped)
            if len(lines) >= limit:
                break
        return lines

    def _render_page_map_markdown(self, payload: dict[str, Any]) -> str:
        lines = [
            "# Page map",
            "",
            f"- Reason: {payload.get('reason') or 'n/a'}",
            f"- URL: {payload.get('url') or 'n/a'}",
            f"- Title: {payload.get('title') or 'n/a'}",
            "",
            "## Headings",
        ]
        headings = payload.get("headings") or []
        if headings:
            for heading in headings:
                lines.append(f"- {heading}")
        else:
            lines.append("- none")
        lines.extend(["", "## Controls"])
        controls = payload.get("controls") or []
        if controls:
            for control in controls:
                lines.append(f"- {control}")
        else:
            lines.append("- none")
        lines.extend(["", "## Links"])
        links = payload.get("links") or []
        has_links = False
        for item in links:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or ""
            href = item.get("href") or ""
            if text or href:
                lines.append(f"- {text} -> {href}")
                has_links = True
        if not has_links:
            lines.append("- none")
        lines.extend(["", "## Visible text"])
        visible_text = payload.get("visible_text_lines") or []
        if visible_text:
            for entry in visible_text:
                lines.append(f"- {entry}")
        else:
            lines.append("- none")
        return "\n".join(lines) + "\n"

    def _render_startup_artifacts_markdown(self, payload: dict[str, Any]) -> str:
        lines = [
            "# Startup diagnostics",
            "",
            f"- Reason: {payload.get('reason') or 'n/a'}",
            f"- Exception: {payload.get('exception') or 'n/a'}",
            f"- Portal: {payload.get('portal_url') or 'n/a'}",
            f"- Documents domain: {payload.get('docs_domain') or 'n/a'}",
            f"- Profile dir: {payload.get('profile_dir') or 'n/a'}",
            f"- Session state: {payload.get('session_state_path') or 'n/a'}",
            f"- Browser channel: {payload.get('browser_channel') or 'n/a'}",
            f"- Browser executable: {payload.get('browser_executable_path') or 'n/a'}",
            f"- Headless: {payload.get('headless')}",
            f"- Keep browser open: {payload.get('keep_browser_open')}",
            f"- Manual login: {payload.get('manual_login')}",
            f"- Map open page: {payload.get('map_open_page')}",
            "",
            "## Visited URLs",
        ]
        visited_urls = payload.get("visited_urls") or []
        if visited_urls:
            for url in visited_urls:
                lines.append(f"- {url}")
        else:
            lines.append("- none")
        return "\n".join(lines) + "\n"

    async def _fill_first(self, locators: Iterable[Any], value: str) -> bool:
        for locator in locators:
            try:
                if await locator.count() == 0:
                    continue
                await locator.first.fill(value)
                return True
            except Exception:
                continue
        return False

    async def _click_first(self, locators: Iterable[Any]) -> bool:
        for locator in locators:
            try:
                if await locator.count() == 0:
                    continue
                await locator.first.click()
                return True
            except Exception:
                continue
        return False

    async def _item_href(self, item: Any) -> str | None:
        try:
            href = await item.evaluate(
                """
                (el) => {
                    const anchor = el.matches('a[href]') ? el : el.querySelector('a[href]');
                    return anchor ? anchor.href : '';
                }
                """
            )
        except Exception:
            href = ""
        href = str(href or "").strip()
        return href or None

    def _classify_document_kind(self, record: LinkRecord, title: str) -> str:
        normalized = self._normalize_text(" ".join([record.text, record.context, record.title, record.aria_label, title]))
        if "lamina" in normalized:
            return "lamina"
        if "regulamento" in normalized:
            return "regulamento"
        if "gerencial" in normalized or "relatorio" in normalized:
            return "relatorio_gerencial"
        return "documento"

    def _normalize_text(self, value: str) -> str:
        from .parsing import normalize_text

        return normalize_text(value)

    def _record_visit(self, url: str) -> None:
        if url not in self._visited_urls:
            self._visited_urls.append(url)

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .models import Action, Locator
from .policy import Policy


class Surface(ABC):
    @abstractmethod
    async def observe(self) -> dict[str, Any]: ...
    @abstractmethod
    async def act(self, action: Action, value: str | None = None) -> str | None: ...
    @abstractmethod
    async def current_url(self) -> str: ...
    @abstractmethod
    async def screenshot(self, path: Path) -> None: ...


class BrowserSurface(Surface):
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw: Any = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.policy: Policy | None = None
        self.unexpected_dialog: str | None = None

    async def configure_policy(self, policy: Policy) -> None:
        self.policy = policy
        async def guard(route):
            try:
                policy.check_url(route.request.url)
                await route.continue_()
            except Exception:
                await route.abort("blockedbyclient")
        await self.context.route("**/*", guard)
        async def dialog_handler(dialog):
            self.unexpected_dialog = dialog.type
            await dialog.dismiss()
        self._page().on("dialog", dialog_handler)

    async def __aenter__(self) -> "BrowserSurface":
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()

    def _page(self) -> Page:
        if not self.page:
            raise RuntimeError("surface is not open")
        return self.page

    def _locator(self, spec: Locator):
        page = self._page()
        if spec.strategy == "role_name":
            return page.get_by_role(spec.role or "button", name=spec.value, exact=spec.exact)
        if spec.strategy == "label":
            return page.get_by_label(spec.value, exact=spec.exact)
        if spec.strategy == "text":
            return page.get_by_text(spec.value, exact=spec.exact)
        return page.locator(spec.value)

    async def resolve(self, spec: Locator):
        errors = []
        for candidate in [spec, *spec.fallbacks]:
            locator = self._locator(candidate)
            try:
                await locator.first.wait_for(state="visible", timeout=1800)
                if await locator.count() != 1:
                    errors.append(f"{candidate.strategy}:{candidate.value} matched {await locator.count()}")
                    continue
                return locator
            except Exception as exc:
                errors.append(f"{candidate.strategy}:{candidate.value} ({type(exc).__name__})")
        raise LookupError("; ".join(errors))

    async def observe(self) -> dict[str, Any]:
        page = self._page()
        items = await page.locator("button,input,select,a,[role],textarea").evaluate_all("""els => els.filter(e => {
          const r=e.getBoundingClientRect(); return r.width>0 && r.height>0;
        }).map((e,i) => ({index:i, tag:e.tagName.toLowerCase(), role:e.getAttribute('role') || e.tagName.toLowerCase(),
          name:e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].innerText) || e.innerText || e.value || '',
          type:e.getAttribute('type'), href:e.getAttribute('href')}))""")
        body = (await page.locator("body").inner_text())[:6000]
        return {"url": page.url, "title": await page.title(), "controls": items, "visible_text": body}

    async def act(self, action: Action, value: str | None = None) -> str | None:
        page = self._page()
        if self.unexpected_dialog:
            kind = self.unexpected_dialog
            self.unexpected_dialog = None
            raise RuntimeError(f"unexpected {kind} dialog")
        if action.kind == "goto":
            await page.goto(value or action.value or "", wait_until="domcontentloaded")
        elif action.kind == "wait":
            await page.wait_for_timeout(int(value or action.value or "500"))
        else:
            locator = await self.resolve(action.target)  # type: ignore[arg-type]
            if action.kind == "fill" and await locator.get_attribute("type") == "password":
                raise PermissionError("credential entry must be performed by an operator")
            if action.kind == "click":
                await locator.click()
            elif action.kind == "fill":
                await locator.fill(value or "")
            elif action.kind == "select":
                await locator.select_option(value or "")
            elif action.kind == "extract":
                return (await locator.inner_text()).strip()
        return None

    async def current_url(self) -> str:
        return self._page().url

    async def screenshot(self, path: Path) -> None:
        await self._page().screenshot(path=str(path), full_page=True)

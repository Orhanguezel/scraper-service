from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright_stealth import stealth_async

from src.config import get_settings

logger = logging.getLogger(__name__)

_BROWSER_SEMAPHORE: asyncio.Semaphore | None = None


def browser_semaphore() -> asyncio.Semaphore:
    """Process-wide cap on concurrently launched browsers.

    Lazily created so it binds to the running event loop (arq worker loop).
    Tune via MAX_CONCURRENT_BROWSERS. This is a hard backstop independent of
    the arq ``max_jobs`` setting so a future config change cannot uncap RAM.
    """
    global _BROWSER_SEMAPHORE
    if _BROWSER_SEMAPHORE is None:
        limit = max(1, get_settings().max_concurrent_browsers)
        _BROWSER_SEMAPHORE = asyncio.Semaphore(limit)
    return _BROWSER_SEMAPHORE

UA_POOL: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

VIEWPORTS: list[tuple[int, int]] = [
    (1366, 768),
    (1536, 864),
    (1920, 1080),
    (1440, 900),
]

CHROMIUM_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-features=IsolateOrigins,site-per-process",
]


def _timezone_for_language(language: str) -> str:
    if language == "tr":
        return "Europe/Istanbul"
    return "UTC"


def _accept_language_header(language: str) -> str:
    if language == "tr":
        return "tr-TR,tr;q=0.9,en-US;q=0.5,en;q=0.4"
    upper = language.upper()
    return f"{language}-{upper},{language};q=0.9,en-US;q=0.5,en;q=0.4"


async def apply_stealth_to_page(page: Page) -> None:
    await stealth_async(page)


async def launch_stealth_context(
    language: str,
    proxy_url: str | None = None,
) -> tuple[Playwright, Browser, BrowserContext]:
    ua = random.choice(UA_POOL)
    viewport = random.choice(VIEWPORTS)
    pw = await async_playwright().start()
    launch_kwargs: dict[str, Any] = {"headless": True, "args": CHROMIUM_ARGS}
    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url}
    browser = await pw.chromium.launch(**launch_kwargs)
    locale = f"{language}-{language.upper()}"
    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": viewport[0], "height": viewport[1]},
        locale=locale,
        timezone_id=_timezone_for_language(language),
        extra_http_headers={"Accept-Language": _accept_language_header(language)},
    )
    return pw, browser, context


async def _close_with_timeout(label: str, coro: Any, timeout: float) -> None:
    try:
        await asyncio.wait_for(coro, timeout=timeout)
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
        # A hung Chrome must not block teardown of the rest of the stack.
        logger.warning("browser teardown step %s failed/timed out: %s", label, exc)


async def close_stealth_context(
    pw: Playwright | None,
    browser: Browser | None,
    context: BrowserContext | None,
    page: Page | None = None,
) -> None:
    """Tear down page -> context -> browser -> playwright driver.

    Each step is independently guarded with a timeout so that one hung step
    (common under memory pressure) cannot prevent ``pw.stop()`` from running
    and orphaning the Chromium + node driver processes.
    """
    timeout = float(get_settings().browser_close_timeout_seconds)
    if page is not None:
        await _close_with_timeout("page.close", page.close(), timeout)
    if context is not None:
        await _close_with_timeout("context.close", context.close(), timeout)
    if browser is not None:
        await _close_with_timeout("browser.close", browser.close(), timeout)
    if pw is not None:
        await _close_with_timeout("playwright.stop", pw.stop(), timeout)


async def detect_captcha(page: Page) -> bool:
    for sel in ('iframe[src*="recaptcha"]', "div#captcha-form"):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible(timeout=1_000):
                return True
        except Exception:
            continue
    try:
        body = (await page.content()).lower()
        if "unusual traffic from your computer network" in body:
            return True
        if "our systems have detected unusual traffic" in body:
            return True
        if "i'm not a robot" in body or "im not a robot" in body:
            return True
    except Exception:
        pass
    return False


async def dismiss_consent(page: Page) -> None:
    consent_selectors = (
        'button[aria-label*="Reddet"]',
        'button[aria-label*="Reject"]',
        'button:has-text("Tümünü reddet")',
        'button:has-text("Reject all")',
    )
    for sel in consent_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click(timeout=2_000)
                return
        except Exception:
            continue
